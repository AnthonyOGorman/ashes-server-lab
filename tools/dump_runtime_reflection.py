"""Read bounded Unreal reflection from the exact installed client, without injection.

OpenProcess requests PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION only.
No remote functions are called; no writes, process control or game input occurs.
Object member memory offsets are explicitly not interpreted as wire handles.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time

ROOT = Path(__file__).resolve().parent.parent
SDK = Path(r"E:\Ashes Of Creation\AOC-SDK\SDK")
GOBJECTS = 0xD6D20F0
GNAMES = 0xD5B4F90
OFFSETS = {"UObject": {"flags":8,"index":12,"class":16,"name":24,"outer":32},
           "UStruct": {"super":0x60,"children":0x68,"child_properties":0x70,"size":0x78},
           "UClass": {"cast_flags":0xF8,"default_object":0x150},
           "UField": {"next":0x48},
           "FField": {"class":8,"owner":0x10,"next":0x18,"name":0x20},
           "FProperty": {"array_dim":0x30,"element_size":0x34,"flags":0x38,"offset":0x44},
           "UFunction": {"flags":0xD0,"exec_function":0xF8}}
TARGET_RPCS = {"ClientRestart","ClientRetryClientRestart","ClientSetHUD","ServerAcknowledgePossession"}
FUNCTION_FLAGS = {"Net":0x40,"NetReliable":0x80,"Native":0x400,"NetMulticast":0x4000,
                  "NetServer":0x200000,"NetClient":0x1000000,"NetValidate":0x80000000}
PROPERTY_FLAGS = {"Net":0x20,"Parm":0x80,"OutParm":0x100,"ReturnParm":0x400,
                  "RepSkip":0x80000000,"RepNotify":0x100000000}


def pointer(value):
    return isinstance(value, int) and 0x10000 <= value < 0x0000800000000000 and value % 8 == 0


class ReadError(RuntimeError):
    pass


class Reader:
    def __init__(self, pid, expected_exe, budget=256*1024*1024):
        if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise ReadError("This tool requires 64-bit Windows Python.")
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.k32.OpenProcess.restype = wintypes.HANDLE
        self.k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k32.ReadProcessMemory.argtypes = [wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.k32.ReadProcessMemory.restype = wintypes.BOOL
        self.k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        self.k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.handle = self.k32.OpenProcess(0x10 | 0x1000, False, pid)
        if not self.handle:
            raise ReadError(f"Cannot open PID {pid} for read-only diagnostics: WinError {ctypes.get_last_error()}")
        self.pid, self.bytes_read, self.budget = pid, 0, budget
        try:
            buffer, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            if not self.k32.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(length)):
                raise ReadError("Cannot verify target process executable path.")
            self.exe = Path(buffer.value).resolve()
            if os.path.normcase(str(self.exe)) != os.path.normcase(str(expected_exe.resolve())):
                raise ReadError("PID does not belong to the exact expected game executable.")
            self.base, self.image_size = self.module()
            if self.read(self.base, 2) != b"MZ":
                raise ReadError("Module image header validation failed.")
        except Exception:
            self.close()
            raise

    def module(self):
        class ModuleEntry(ctypes.Structure):
            _fields_ = [("dwSize",wintypes.DWORD),("th32ModuleID",wintypes.DWORD),("th32ProcessID",wintypes.DWORD),
                        ("GlblcntUsage",wintypes.DWORD),("ProccntUsage",wintypes.DWORD),
                        ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wintypes.DWORD),
                        ("hModule",wintypes.HMODULE),("szModule",wintypes.WCHAR*256),("szExePath",wintypes.WCHAR*260)]
        self.k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD,wintypes.DWORD]
        self.k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.k32.Module32FirstW.argtypes = [wintypes.HANDLE,ctypes.POINTER(ModuleEntry)]
        self.k32.Module32NextW.argtypes = [wintypes.HANDLE,ctypes.POINTER(ModuleEntry)]
        snap = self.k32.CreateToolhelp32Snapshot(0x8 | 0x10,self.pid)
        if snap == ctypes.c_void_p(-1).value:
            raise ReadError(f"Cannot enumerate process modules: WinError {ctypes.get_last_error()}")
        try:
            entry = ModuleEntry()
            entry.dwSize = ctypes.sizeof(entry)
            more = self.k32.Module32FirstW(snap,ctypes.byref(entry))
            while more:
                if os.path.normcase(entry.szExePath) == os.path.normcase(str(self.exe)):
                    return ctypes.cast(entry.modBaseAddr,ctypes.c_void_p).value,entry.modBaseSize
                more = self.k32.Module32NextW(snap,ctypes.byref(entry))
            raise ReadError("Expected executable module was not found.")
        finally:
            self.k32.CloseHandle(snap)

    def read(self, address, size):
        if not 0x10000 <= address < 0x0000800000000000 or not 0 < size <= 2*1024*1024:
            raise ReadError("Invalid or excessive memory read.")
        if self.bytes_read + size > self.budget:
            raise ReadError("Read budget exhausted.")
        self.bytes_read += size
        buffer, count = ctypes.create_string_buffer(size), ctypes.c_size_t()
        if not self.k32.ReadProcessMemory(self.handle,ctypes.c_void_p(address),buffer,size,ctypes.byref(count)) or count.value != size:
            raise ReadError(f"Unreadable memory at {address:#x}, size {size}")
        return buffer.raw

    def unpack(self, address, fmt):
        return struct.unpack(fmt,self.read(address,struct.calcsize(fmt)))

    def close(self):
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None


class Names:
    """Validate a read-only compact FNamePool layout before decoding object names."""
    def __init__(self, reader):
        self.r, self.cache = reader, {}
        errors = []
        original = reader.base + GNAMES
        candidates = [original]
        # SDK declares GNames an unused fallback. Derive the actual pool from the
        # exact client's AppendString RIP-relative LEA; only read its instructions.
        instruction = reader.read(reader.base+0x1503A90,7)
        if instruction[:3] == b"\x4c\x8d\x05":
            live_pool = reader.base+0x1503A90+7+struct.unpack_from("<i",instruction,3)[0]
            if pointer(live_pool): candidates.append(live_pool)
        try:
            indirect = reader.unpack(original,"<Q")[0]
            if pointer(indirect): candidates.append(indirect)
        except ReadError:
            pass
        for base in candidates:
            for blocks_offset in (0x10,0x18):
                try:
                    block = reader.unpack(base + blocks_offset,"<Q")[0]
                    if not pointer(block): continue
                    header = reader.unpack(block,"<H")[0]
                    length = header >> 6
                    if length != 4 or header & 1: continue
                    if reader.read(block+2,4) != b"None": continue
                    self.base, self.blocks_offset = base, blocks_offset
                    self.block0 = block
                    return
                except ReadError as error:
                    errors.append(str(error))
        raise ReadError("FNamePool could not be validated against the None sentinel. SDK offsets may not match this build; no remote AppendString is called.")

    def get(self, index, number=0):
        if not isinstance(index,int) or index < 0 or index>>16 >= 8192:
            raise ReadError("Invalid FName index.")
        if index not in self.cache:
            block = self.r.unpack(self.base+self.blocks_offset+8*(index>>16),"<Q")[0]
            if not pointer(block): raise ReadError("Invalid FName block pointer.")
            address = block+2*(index & 0xffff)
            header = self.r.unpack(address,"<H")[0]
            length, wide = header >> 6, bool(header & 1)
            if not 1 <= length <= 1024: raise ReadError("Invalid FName entry length.")
            raw = self.r.read(address+2,length*(2 if wide else 1))
            name = raw.decode("utf-16le" if wide else "utf-8",errors="strict")
            if any(ord(char)<32 for char in name): raise ReadError("Invalid FName characters.")
            self.cache[index] = name
        return self.cache[index] + (f"_{number-1}" if number else "")


class Reflection:
    def __init__(self, reader, max_objects=500000):
        self.r, self.names = reader, Names(reader)
        self.cache, self.class_names = {}, {}
        data = reader.read(reader.base+GOBJECTS,32)
        self.chunks, self.max_count, self.count, self.max_chunks, self.num_chunks = struct.unpack_from("<Q8xiiii",data)
        if not pointer(self.chunks) or not 0 < self.count <= self.max_count <= 8_000_000 or not 0 < self.num_chunks <= self.max_chunks <= 256:
            raise ReadError("GObjects layout validation failed.")
        if (self.count+65535)//65536 > self.num_chunks:
            raise ReadError("GObjects count exceeds allocated chunks.")
        self.scan_limit = min(self.count,max_objects)
        self.validation = {"name_pool_sentinel":"None","names_rva":hex(GNAMES),
            "name_pool_address":hex(self.names.base),"actual_name_pool_rva":hex(self.names.base-reader.base),
            "name_pool_derivation":"Read-only RIP-relative LEA in SDK AppendString at RVA0x1503a90; no code invoked",
            "name_blocks_offset":self.names.blocks_offset,
            "gobjects_rva":hex(GOBJECTS),"object_count":self.count,"scan_limit":self.scan_limit,
            "chunk_count":self.num_chunks,"validated_object_indices":0,"invalid_object_reads":0}

    def obj(self, address):
        if address not in self.cache:
            if not pointer(address): raise ReadError("Invalid UObject pointer.")
            data = self.r.read(address,0x48)
            vtable,flags,index,cls,name,number,outer = struct.unpack_from("<QIiQIIQ",data)
            if not self.r.base <= vtable < self.r.base+self.r.image_size or index < 0 or not pointer(cls):
                raise ReadError("UObject vtable/index/class validation failed.")
            self.cache[address] = {"address":hex(address),"flags":hex(flags),"index":index,
                "class_address":cls,"name":self.names.get(name,number),"outer_address":outer}
        return self.cache[address]

    def class_name(self, address):
        if address not in self.class_names:
            self.class_names[address] = self.obj(address)["name"]
        return self.class_names[address]

    def objects(self):
        blocks = self.r.read(self.chunks,self.num_chunks*8)
        for chunk_index in range((self.scan_limit+65535)//65536):
            block = struct.unpack_from("<Q",blocks,chunk_index*8)[0]
            if not pointer(block): raise ReadError("Invalid GObjects chunk pointer.")
            count = min(65536,self.scan_limit-chunk_index*65536)
            entries = self.r.read(block,count*24)
            for local_index in range(count):
                address = struct.unpack_from("<Q",entries,local_index*24)[0]
                if not address: continue
                try:
                    obj = self.obj(address)
                    if obj["index"] != chunk_index*65536+local_index:
                        raise ReadError("UObject index disagrees with chunk position.")
                    self.validation["validated_object_indices"] += 1
                    yield address,obj
                except (ReadError,UnicodeError):
                    self.validation["invalid_object_reads"] += 1
                    if self.validation["invalid_object_reads"] > 1000 and self.validation["validated_object_indices"] < 100:
                        raise ReadError("Too many layout/name failures; refusing guessed reflection offsets.")

    def properties(self, head, owner_size=None):
        result, seen = [], set()
        while head and len(result)<512:
            if not pointer(head) or head in seen: raise ReadError("Invalid/cyclic FProperty chain.")
            seen.add(head)
            data = self.r.read(head,0x70)
            fieldclass,owner,next_field = struct.unpack_from("<QQQ",data,8)
            name,number = struct.unpack_from("<II",data,0x20)
            arraydim,elementsize,flags = struct.unpack_from("<iiQ",data,0x30)
            offset = struct.unpack_from("<i",data,0x44)[0]
            if not pointer(fieldclass) or not 1 <= arraydim <= 65536 or not 0 < elementsize <= 1_048_576 or offset < 0:
                raise ReadError("FProperty layout validation failed.")
            if owner_size and offset+arraydim*elementsize > owner_size:
                raise ReadError("FProperty member lies outside the reflected struct size.")
            typeindex,typenumber = self.r.unpack(fieldclass,"<II")
            property_type = self.names.get(typeindex,typenumber)
            entry = {"name":self.names.get(name,number),"address":hex(head),"type":property_type,
                "owner_pointer_tagged":hex(owner),"offset_in_object":offset,"array_dim":arraydim,
                "element_size":elementsize,"flags":hex(flags),"flag_names":[k for k,v in PROPERTY_FLAGS.items() if flags&v],
                "rep_index":None,"rep_index_reason":"Not labeled in supplied SDK; field 0x40 is padding.",
                "uninterpreted_sdk_padding_0x40":data[0x40:0x44].hex()}
            if property_type in ("ObjectProperty","ObjectPropertyBase","ClassProperty","StructProperty"):
                target = self.r.unpack(head+0x70,"<Q")[0]
                if pointer(target):
                    try: entry["referenced_type"] = self.obj(target)["name"]
                    except (ReadError,UnicodeError): pass
            if property_type=="BoolProperty":
                entry["bool_layout"] = dict(zip(("field_size","byte_offset","byte_mask","field_mask"),self.r.read(head+0x70,4)))
            result.append(entry)
            head = next_field
        if head: raise ReadError("FProperty list exceeded the bounded member limit.")
        return result

    def functions(self, head):
        result,seen = [],set()
        while head and len(seen)<2048:
            if not pointer(head) or head in seen: raise ReadError("Invalid/cyclic UField chain.")
            seen.add(head)
            obj = self.obj(head)
            clsname = self.class_name(obj["class_address"])
            if clsname in ("Function","DelegateFunction","SparseDelegateFunction"):
                data = self.r.read(head,0x100)
                flags = struct.unpack_from("<I",data,0xD0)[0]
                if flags&0x40 or obj["name"] in TARGET_RPCS:
                    props = struct.unpack_from("<Q",data,0x70)[0]
                    entry = {"name":obj["name"],"address":hex(head),"flags":hex(flags),
                        "flag_names":[k for k,v in FUNCTION_FLAGS.items() if flags&v],
                        "struct_size":struct.unpack_from("<i",data,0x78)[0],
                        "parameters":self.properties(props),"exec_address":hex(struct.unpack_from("<Q",data,0xF8)[0]),
                        "uninterpreted_sdk_padding_0xd4":data[0xD4:0xF8].hex(),"wire_handle":None}
                    result.append(entry)
            head = self.r.unpack(head+0x48,"<Q")[0]
        if head: raise ReadError("UField list exceeded the bounded function limit.")
        return result

    def dump_class(self, address):
        obj = self.obj(address)
        data = self.r.read(address,0x158)
        parent,children,properties = struct.unpack_from("<QQQ",data,0x60)
        size = struct.unpack_from("<i",data,0x78)[0]
        if not 0x48 <= size <= 16*1024*1024: raise ReadError("UClass reflected size invalid.")
        result = {"name":obj["name"],"address":hex(address),"object_index":obj["index"],
                  "metaclass":self.class_name(obj["class_address"]),"size":size,
                  "cast_flags":hex(struct.unpack_from("<Q",data,0xF8)[0]),
                  "default_object":hex(struct.unpack_from("<Q",data,0x150)[0]),
                  "super":self.obj(parent)["name"] if parent else None,
                  "properties":self.properties(properties,size),"net_functions":self.functions(children)}
        return result,parent


def validate_sdk(path):
    basic = (path/"Basic.hpp").read_text(encoding="utf-8")
    core = (path/"CoreUObject_classes.hpp").read_text(encoding="utf-8")
    for marker in ("0x0D6D20F0","0x0D5B4F90","FProperty","0x0044"):
        if marker not in basic: raise ReadError("SDK layout markers differ from the implemented read-only layout.")
    for marker in ("0x0060","0x0068","0x0070","0x00D0","0x00F8"):
        if marker not in core: raise ReadError("CoreUObject SDK layout markers differ.")
    return {"source":str(path),"basic_sha256":hashlib.sha256(basic.encode()).hexdigest(),
            "core_sha256":hashlib.sha256(core.encode()).hexdigest(),"offsets":OFFSETS,
            "rep_index":"Unknown: supplied SDK marks 0x40 as padding; no padding interpreted as a wire handle."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid",type=int)
    parser.add_argument("--output",type=Path,default=ROOT/"evidence/runtime_reflection.json")
    parser.add_argument("--sdk",type=Path,default=SDK)
    parser.add_argument("--class",dest="classes",action="append")
    parser.add_argument("--max-objects",type=int,default=500000)
    args = parser.parse_args()
    if args.pid <= 0 or not 1 <= args.max_objects <= 1_000_000: parser.error("Invalid PID or object bound")
    inventory = json.loads((ROOT/"evidence/client_inventory.json").read_text(encoding="utf-8"))
    exe = Path(inventory["exe"])
    digest = hashlib.file_digest(exe.open("rb"),"sha256").hexdigest() if hasattr(hashlib,"file_digest") else hashlib.sha256(exe.read_bytes()).hexdigest()
    if digest != inventory["sha256"]: raise ReadError("Installed executable does not match the extracted contract inventory.")
    report = {"pid":args.pid,"time":datetime.now(timezone.utc).isoformat(),"access":"PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION",
              "exe":str(exe),"sha256":digest,"sdk":validate_sdk(args.sdk),"classes":[],
              "wire_handle_claims":"None. Runtime member offsets and Net flags are reflection evidence, not network field handles."}
    reader = Reader(args.pid,exe)
    started = time.monotonic()
    try:
        reflection = Reflection(reader,args.max_objects)
        selected,found = [],set()
        explicit = set(args.classes or ())
        default_targets = {"Actor","Pawn","Character","Controller","PlayerController","PlayerState","HUD"}
        for address,obj in reflection.objects():
            name = obj["name"]
            wanted = name in explicit if explicit else name in default_targets or bool(re.search(r"(?:Intrepid|AOC|BasePlayer|PlayerCharacter).*(?:Controller|Pawn|Character)",name))
            if not wanted or name.startswith("Default__"): continue
            if reflection.class_name(obj["class_address"]) not in ("Class","BlueprintGeneratedClass","WidgetBlueprintGeneratedClass"): continue
            if len(selected)>=80: raise ReadError("Too many matching classes; specify --class targets.")
            selected.append(address)
        for address in selected:
            current = address
            for depth in range(16):
                if not current or current in found: break
                found.add(current)
                try:
                    dumped,parent = reflection.dump_class(current)
                    report["classes"].append(dumped)
                except (ReadError,UnicodeError) as error:
                    report["classes"].append({"address":hex(current),"name":reflection.obj(current)["name"],"error":str(error)})
                    break
                current = parent
        report["validation"] = reflection.validation
        report["target_rpcs_found"] = sorted({f["name"] for cls in report["classes"] for f in cls.get("net_functions",[]) if f["name"] in TARGET_RPCS})
        report["module_base"] = hex(reader.base)
        report["bytes_read"] = reader.bytes_read
        report["elapsed_seconds"] = time.monotonic()-started
        report["status"] = "complete" if selected else "no_matching_classes"
    except Exception as error:
        report.update(status="validation_failed",error=str(error),bytes_read=reader.bytes_read)
        raise
    finally:
        reader.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(args.output),"status":report["status"],"classes":len(report["classes"]),
                      "target_rpcs_found":report.get("target_rpcs_found",[]),"validation":report.get("validation"),
                      "bytes_read":reader.bytes_read,"elapsed_seconds":report.get("elapsed_seconds")},indent=2))


if __name__=="__main__":
    main()
