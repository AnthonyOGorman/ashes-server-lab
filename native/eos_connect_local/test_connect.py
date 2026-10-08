"""Exercise the isolated x64 Connect ABI, never load it into the game."""
import ctypes as C
from pathlib import Path
import unittest
import json

class Credentials(C.Structure):
    _fields_=[('version',C.c_int32),('token',C.c_char_p),('type',C.c_int32)]
class Options(C.Structure):
    _fields_=[('version',C.c_int32),('credentials',C.POINTER(Credentials)),('user_info',C.c_void_p)]
class CallbackInfo(C.Structure):
    _fields_=[('result',C.c_int32),('data',C.c_void_p),('user',C.c_void_p),('continuance',C.c_void_p)]
Callback=C.CFUNCTYPE(None,C.POINTER(CallbackInfo))

class LocalConnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dll=C.CDLL(str(Path(__file__).with_name('LocalEOSConnect.dll')))
        signatures={
            'LocalEOS_CreateConnect':([],C.c_void_p),
            'LocalEOS_DestroyConnect':([C.c_void_p],None),
            'EOS_Connect_Login':([C.c_void_p,C.POINTER(Options),C.c_void_p,Callback],None),
            'EOS_Platform_Tick':([C.c_void_p],None),
            'EOS_Connect_GetLoginStatus':([C.c_void_p,C.c_void_p],C.c_int32),
            'EOS_Connect_GetLoggedInUsersCount':([C.c_void_p],C.c_int32),
            'EOS_Connect_GetLoggedInUserByIndex':([C.c_void_p,C.c_int32],C.c_void_p),
            'EOS_ProductUserId_IsValid':([C.c_void_p],C.c_int32),
            'EOS_ProductUserId_FromString':([C.c_char_p],C.c_void_p),
            'EOS_ProductUserId_ToString':([C.c_void_p,C.c_void_p,C.POINTER(C.c_int32)],C.c_int32),
            'EOS_Initialize':([C.POINTER(C.c_int32)],C.c_int32),
            'EOS_Platform_Create':([C.c_void_p],C.c_void_p),
            'EOS_Platform_Release':([C.c_void_p],None),
            'EOS_Platform_GetConnectInterface':([C.c_void_p],C.c_void_p),
            'EOS_Platform_GetAntiCheatClientInterface':([C.c_void_p],C.c_void_p),
        }
        for name,(args,result) in signatures.items():
            f=getattr(cls.dll,name);f.argtypes=args;f.restype=result
    def setUp(self):
        self.handle=self.dll.LocalEOS_CreateConnect();self.callbacks=[];self.events=[]
    def tearDown(self):
        self.dll.LocalEOS_DestroyConnect(self.handle)
    def login(self,token=b'lab-local-account',version=2,callback=None):
        credentials=Credentials(1,token,9);options=Options(version,C.pointer(credentials),None)
        if callback is None:
            def callback(info):
                i=info.contents;self.events.append((i.result,i.data,i.user,i.continuance))
        cb=Callback(callback);self.callbacks.append(cb)
        self.dll.EOS_Connect_Login(self.handle,C.byref(options),0x1234567887654321,cb)
    def test_abi_matches_native_callback_offsets(self):
        self.assertEqual(C.sizeof(Options),24)
        self.assertEqual(C.sizeof(CallbackInfo),32)
        self.assertEqual(CallbackInfo.user.offset,16)
        self.assertEqual(CallbackInfo.continuance.offset,24)
    def test_login_is_delivered_on_tick_with_original_context(self):
        self.login();self.assertEqual(self.events,[])
        self.assertEqual(self.dll.EOS_Connect_GetLoggedInUsersCount(self.handle),0)
        self.dll.EOS_Platform_Tick(self.handle)
        result,data,user,continuance=self.events[0]
        self.assertEqual((result,data,continuance),(0,0x1234567887654321,None))
        self.assertEqual(self.dll.EOS_ProductUserId_IsValid(user),1)
        self.assertEqual(self.dll.EOS_Connect_GetLoginStatus(self.handle,user),2)
        self.assertEqual(self.dll.EOS_Connect_GetLoggedInUserByIndex(self.handle,0),user)
        self.assertIsNone(self.dll.EOS_Connect_GetLoggedInUserByIndex(self.handle,1))
    def test_external_credentials_are_not_accepted(self):
        self.login(b'an-external-token');self.dll.EOS_Platform_Tick(self.handle)
        self.assertEqual(self.events[0][0],2)
        self.assertIsNone(self.events[0][2])
        self.assertEqual(self.dll.EOS_Connect_GetLoggedInUsersCount(self.handle),0)
    def test_wrong_api_version_fails(self):
        self.login(version=99);self.dll.EOS_Platform_Tick(self.handle)
        self.assertEqual(self.events[0][0],10)
    def test_id_round_trip_checks_buffer_and_handle(self):
        self.login();self.dll.EOS_Platform_Tick(self.handle);user=self.events[0][2]
        size=C.c_int32(0)
        self.assertEqual(self.dll.EOS_ProductUserId_ToString(user,None,C.byref(size)),22)
        self.assertEqual(size.value,33)
        buffer=C.create_string_buffer(size.value)
        self.assertEqual(self.dll.EOS_ProductUserId_ToString(user,buffer,C.byref(size)),0)
        self.assertEqual(self.dll.EOS_ProductUserId_FromString(buffer.value),user)
        self.assertEqual(self.dll.EOS_ProductUserId_IsValid(0x1234),0)
        self.assertIsNone(self.dll.EOS_ProductUserId_FromString(b'not-a-local-user'))
    def test_reentrant_login_waits_for_next_tick(self):
        def first(info):
            self.events.append(('first',info.contents.result));self.login()
        self.login(callback=first);self.dll.EOS_Platform_Tick(self.handle)
        self.assertEqual(self.events,[('first',0)])
        self.dll.EOS_Platform_Tick(self.handle)
        self.assertEqual(len(self.events),2)
    def test_destroy_cancels_queued_callbacks(self):
        self.login();self.dll.LocalEOS_DestroyConnect(self.handle)
        self.dll.EOS_Platform_Tick(self.handle);self.assertEqual(self.events,[])
    def test_all_exact_client_delay_imports_are_exported(self):
        root=Path(__file__).resolve().parents[2]
        imported=json.loads((root/'evidence/client_eos_imports.json').read_text())
        names=imported['EOSSDK-Win64-Shipping.dll']
        self.assertEqual(len(names),25)
        for name in names:self.assertTrue(getattr(self.dll,name))
    def test_platform_interfaces_share_the_local_context(self):
        version=C.c_int32(4)
        self.assertEqual(self.dll.EOS_Initialize(C.byref(version)),0)
        platform=self.dll.EOS_Platform_Create(C.byref(version))
        self.assertEqual(self.dll.EOS_Platform_GetConnectInterface(platform),platform)
        self.assertEqual(self.dll.EOS_Platform_GetAntiCheatClientInterface(platform),platform)
        self.dll.EOS_Platform_Release(platform)
        self.assertIsNone(self.dll.EOS_Platform_GetConnectInterface(platform))

if __name__=='__main__':unittest.main(verbosity=2)
