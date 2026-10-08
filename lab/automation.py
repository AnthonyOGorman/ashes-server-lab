"""Bounded, cancellable game scenarios. A passed run requires observed milestones.

The driver never launches a game, changes focus, or guesses login coordinates.
Coordinates are physical pixels relative to the game's current client rectangle.
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


KEYS = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20,
        "space": 0x39, "escape": 0x01, "enter": 0x1C, "tab": 0x0F,
        "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D}
EXTENDED_KEYS = frozenset({"up", "down", "left", "right"})
VK_KEYS = {"w":0x57,"a":0x41,"s":0x53,"d":0x44,"space":0x20,
           "escape":0x1B,"enter":0x0D,"tab":0x09,
           "up":0x26,"down":0x28,"left":0x25,"right":0x27}


def key_message_lparam(key, up=False):
    """WM_KEY scan metadata: E0 arrows, previous state and transition on release."""
    return 1 | (KEYS[key] << 16) | ((1 << 24) if key in EXTENDED_KEYS else 0) | ((3 << 30) if up else 0)


def key_input_flags(key, up=False):
    return 0x8 | (0x1 if key in EXTENDED_KEYS else 0) | (0x2 if up else 0)
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "config" / "templates"

DEFAULT_SCENARIO = {
    "name": "Login, realm, world and movement verification",
    "calibrated": False,
    "steps": [
        {"name": "Wait for authentication", "action": "wait_milestone", "milestone": "authentication", "timeout": 45},
        {"name": "Enter realm (calibrate coordinates)", "action": "click", "x": -1, "y": -1},
        {"name": "Wait for lobby", "action": "wait_milestone", "milestone": "lobby", "timeout": 20},
        {"name": "Play (calibrate coordinates)", "action": "click", "x": -1, "y": -1},
        {"name": "Wait for welcome", "action": "wait_milestone", "milestone": "welcome", "timeout": 20},
        {"name": "Wait for world load", "action": "wait_milestone", "milestone": "world_loaded", "timeout": 45},
        {"name": "Wait for player spawn", "action": "wait_milestone", "milestone": "player_spawned", "timeout": 30},
        {"name": "Walk forward", "action": "key", "key": "w", "duration": 1},
        {"name": "Verify actual movement", "action": "wait_milestone", "milestone": "movement", "timeout": 10},
    ],
}


class Blocked(RuntimeError):
    """An explicit prerequisite for operating the game is absent."""


class CaptureNotReady(Blocked):
    """A loading transition may temporarily yield an empty or flat GPU frame."""


class Cancelled(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_bbox(bbox):
    """A Pillow-style [left, top, right, bottom] box in client physical pixels."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or any(
            isinstance(value, bool) or not isinstance(value, int) for value in bbox):
        raise ValueError("bbox requires four integer physical pixels: left, top, right, bottom.")
    left, top, right, bottom = bbox
    if not 0 <= left < right <= 16384 or not 0 <= top < bottom <= 16384:
        raise ValueError("bbox must be a nonempty positive client rectangle within 16384 pixels.")
    if (right-left) * (bottom-top) > 16_777_216:
        raise ValueError("Template crop is too large.")
    return tuple(bbox)


def validate_threshold(threshold):
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 64:
        raise ValueError("Image RMS threshold must be a finite number between 0 and 64.")
    return float(threshold)


def resolve_template(name, template_dir=TEMPLATE_DIR):
    if not isinstance(name, str) or not name.strip() or len(name) > 240:
        raise ValueError("Template requires a local PNG filename.")
    directory = Path(template_dir).resolve()
    target = (directory / name).resolve()
    if not target.is_relative_to(directory) or target.suffix.lower() != ".png":
        raise Blocked("Image templates must be PNG files inside the configured templates folder.")
    return target


def compare_crop(image, template, bbox, threshold=8):
    """Compare aligned RGB pixels, preserving resolution and without image input."""
    from PIL import ImageChops, ImageStat
    bbox, threshold = validate_bbox(bbox), validate_threshold(threshold)
    left, top, right, bottom = bbox
    if right > image.width or bottom > image.height:
        raise Blocked("Visual checkpoint bbox is outside the game client area.")
    size = (right-left, bottom-top)
    if template.size != size:
        raise Blocked("Template dimensions must exactly match bbox; recalibrate after changing resolution.")
    diff = ImageChops.difference(image.crop(bbox).convert("RGB"), template.convert("RGB"))
    channels = ImageStat.Stat(diff).rms
    rms = math.sqrt(sum(value * value for value in channels) / len(channels))
    return {"matched": rms <= threshold, "rms": rms, "threshold": threshold,
            "bbox": list(bbox), "width": size[0], "height": size[1]}


def learn_template(image, name, bbox, template_dir=TEMPLATE_DIR):
    """Save a crop from an already captured client image; no screen/input actions.

    The HTTP caller must choose the source from its own saved client screenshots,
    rather than accepting an arbitrary source filesystem path from the browser.
    """
    import hashlib
    bbox = validate_bbox(bbox)
    target = resolve_template(name, template_dir)
    if bbox[2] > image.width or bbox[3] > image.height:
        raise ValueError("Template bbox is outside the saved client screenshot.")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.crop(bbox).convert("RGB").save(target, "PNG")
    return {"template": str(target.relative_to(Path(template_dir).resolve())), "bbox": list(bbox),
            "width": bbox[2]-bbox[0], "height": bbox[3]-bbox[1],
            "source_width": image.width, "source_height": image.height,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "created_at": utc_now()}


class WindowsDriver:
    def __init__(self, game_pid: int):
        if os.name != "nt":
            raise Blocked("Native game controls require Windows.")
        if isinstance(game_pid, bool) or not isinstance(game_pid, int) or game_pid <= 0:
            raise ValueError("An exact positive game process PID is required.")
        from ctypes import wintypes
        self.pid = game_pid
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        # This thread uses physical pixels, matching Pillow's screenshot coordinates.
        self.user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        self.held = set()
        self.pending_release = set()
        self.hwnd = None
        ulong_ptr = ctypes.c_size_t

        class MouseInput(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class KeyboardInput(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ulong_ptr)]

        class HardwareInput(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class InputUnion(ctypes.Union):
            _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]

        class Input(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", InputUnion)]

        self.Input, self.MouseInput, self.KeyboardInput = Input, MouseInput, KeyboardInput
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT

    def _foreground(self):
        from ctypes import wintypes
        hwnd = self.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not hwnd or pid.value != self.pid:
            raise Blocked(f"Game PID {self.pid} must remain the foreground application.")
        self.hwnd = hwnd
        return hwnd

    def _rect(self):
        from ctypes import wintypes
        self.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        hwnd = self._foreground()
        self.release_all()
        rect, point = wintypes.RECT(), wintypes.POINT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)) or not self.user32.ClientToScreen(hwnd, ctypes.byref(point)):
            raise Blocked("Cannot read the game client rectangle.")
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise Blocked("The game window is minimized or has no visible client area.")
        return point.x, point.y, width, height

    def _send(self, records):
        self._foreground()
        array = (self.Input * len(records))(*records)
        if self.user32.SendInput(len(array), array, ctypes.sizeof(self.Input)) != len(array):
            raise Blocked("Windows rejected game input (integrity level or input restrictions).")

    def _key_event(self, key, up=False):
        event = self.Input(type=1)
        event.ki = self.KeyboardInput(0, KEYS[key], key_input_flags(key, up), 0, 0)
        self._send([event])

    def screenshot(self, path):
        from PIL import ImageGrab
        left, top, width, height = self._rect()
        ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True).save(path, "PNG")
        return {"path": str(path), "width": width, "height": height, "pid": self.pid}

    def compare_image(self, template_path, bbox, threshold=8):
        from PIL import Image, ImageGrab
        left, top, width, height = self._rect()
        if not Path(template_path).is_file():
            raise Blocked("Learn the visual checkpoint template from a saved client screenshot first.")
        with Image.open(template_path) as template:
            image = ImageGrab.grab(bbox=(left, top, left+width, top+height), all_screens=True)
            self._foreground()
            result = compare_crop(image, template, bbox, threshold)
        return {**result, "template": str(template_path), "pid": self.pid}

    def click(self, x, y):
        from ctypes import wintypes
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("Click coordinates must be integer physical pixels.")
        left, top, width, height = self._rect()
        if not 0 <= x < width or not 0 <= y < height:
            raise Blocked("Click is outside the game client rectangle.")
        # SendInput moves and clicks as a single batch; no unrelated window is targeted.
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        vx, vy = self.user32.GetSystemMetrics(76), self.user32.GetSystemMetrics(77)
        vw, vh = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
        if vw <= 1 or vh <= 1:
            raise Blocked("Cannot read desktop dimensions.")
        move = self.Input(type=0)
        move.mi = self.MouseInput(round((left + x - vx) * 65535 / (vw - 1)),
                                  round((top + y - vy) * 65535 / (vh - 1)), 0, 0xC001, 0, 0)
        down, up = self.Input(type=0), self.Input(type=0)
        down.mi.dwFlags, up.mi.dwFlags = 0x2, 0x4
        self._send([move, down, up])

    def key(self, key, duration, cancel):
        if key not in KEYS:
            raise ValueError("Only WASD, space, escape, enter, tab and arrow keys are permitted.")
        self.release_all()
        self._foreground()
        # Include in cleanup before sending, even if SendInput reports an error.
        self.held.add(key)
        try:
            self._key_event(key)
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                self._foreground()
                if cancel.wait(min(0.02, max(0, deadline - time.monotonic()))):
                    raise Cancelled("Run stopped.")
        finally:
            self.release_all()

    def release_all(self):
        keys = self.held | self.pending_release
        if not keys:
            return
        try:
            self._foreground()
        except Blocked:
            # Never send global keystrokes to a different foreground application.
            # Deliver game-specific releases and defer global cleanup until it returns.
            from ctypes import wintypes
            original_pid = wintypes.DWORD()
            if self.hwnd:
                self.user32.GetWindowThreadProcessId(self.hwnd, ctypes.byref(original_pid))
            if self.hwnd and original_pid.value == self.pid:
                for key in keys:
                    self.user32.PostMessageW(self.hwnd, 0x101, VK_KEYS[key], key_message_lparam(key, up=True))
            self.pending_release = keys
            self.held.clear()
            return
        for key in list(keys):
            self._key_event(key, up=True)
            self.pending_release.discard(key)
            self.held.discard(key)


class _BackgroundWindowAPI:
    """Only HWND-scoped message delivery and window-local GDI capture APIs."""
    def __init__(self):
        if os.name != "nt":
            raise Blocked("Background game controls require Windows.")
        from ctypes import wintypes
        self.w = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user32.EnumWindows.argtypes = [self.callback,wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        for name in ("IsWindow","IsWindowVisible","IsIconic"):
            getattr(self.user32,name).argtypes = [wintypes.HWND]
            getattr(self.user32,name).restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user32.GetCursorPos.restype = wintypes.BOOL
        self.user32.GetClientRect.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.user32.GetWindowRect.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        self.user32.ClientToScreen.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
        self.user32.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.user32.PostMessageW.restype = wintypes.BOOL
        self.user32.PrintWindow.argtypes = [wintypes.HWND,wintypes.HDC,wintypes.UINT]
        self.user32.PrintWindow.restype = wintypes.BOOL
        self.user32.GetWindowDC.argtypes = [wintypes.HWND]
        self.user32.GetWindowDC.restype = wintypes.HDC
        self.user32.ReleaseDC.argtypes = [wintypes.HWND,wintypes.HDC]
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateDIBSection.argtypes = [wintypes.HDC,ctypes.c_void_p,wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),wintypes.HANDLE,wintypes.DWORD]
        self.gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi32.SelectObject.argtypes = [wintypes.HDC,wintypes.HGDIOBJ]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p

    def dpi(self):
        self.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))

    def window_pid(self, hwnd):
        pid = self.w.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        return pid.value

    def foreground_pid(self):
        hwnd = self.user32.GetForegroundWindow()
        return self.window_pid(hwnd) if hwnd else None

    def foreground_thread(self):
        hwnd=self.user32.GetForegroundWindow()
        pid=self.w.DWORD()
        return self.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid)) if hwnd else 0

    def cursor_position(self):
        point=self.w.POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            raise Blocked("Cannot verify the real desktop cursor position.")
        return [point.x,point.y]

    def is_window(self, hwnd):
        return bool(self.user32.IsWindow(hwnd))

    def minimized(self, hwnd):
        return bool(self.user32.IsIconic(hwnd))

    def client_size(self, hwnd):
        self.dpi()
        rect = self.w.RECT()
        if not self.user32.GetClientRect(hwnd,ctypes.byref(rect)):
            raise Blocked("Cannot read the targeted game client area.")
        return rect.right-rect.left, rect.bottom-rect.top

    def choose_window(self, pid):
        matches = []
        def visit(hwnd, unused):
            if self.window_pid(hwnd)==pid and self.user32.IsWindowVisible(hwnd):
                try:
                    width,height = self.client_size(hwnd)
                    if width>0 and height>0:
                        matches.append((width*height,hwnd))
                except Blocked:
                    pass
            return True
        callback = self.callback(visit)
        if not self.user32.EnumWindows(callback,0):
            raise Blocked("Cannot enumerate the launched game's windows.")
        if not matches:
            raise Blocked("The launched game has no visible client window yet.")
        return max(matches,key=lambda item:item[0])[1]

    def post(self, hwnd, message, wparam, lparam):
        if not self.user32.PostMessageW(hwnd,message,wparam,lparam):
            raise Blocked(f"Windows rejected targeted game window message: WinError {ctypes.get_last_error()}")

    def capture(self, hwnd):
        from PIL import Image
        self.dpi()
        rect,origin = self.w.RECT(),self.w.POINT()
        if not self.user32.GetWindowRect(hwnd,ctypes.byref(rect)) or not self.user32.ClientToScreen(hwnd,ctypes.byref(origin)):
            raise Blocked("Cannot read the game window capture geometry.")
        width,height = rect.right-rect.left,rect.bottom-rect.top
        cw,ch = self.client_size(hwnd)
        cl,ct = origin.x-rect.left,origin.y-rect.top
        if not 0<width<=16384 or not 0<height<=16384 or width*height>16_777_216:
            raise Blocked("Targeted game capture dimensions are invalid or excessive.")
        if cl<0 or ct<0 or cw<=0 or ch<=0 or cl+cw>width or ct+ch>height:
            raise Blocked("The game client area is outside its window capture bounds.")
        class BitmapInfoHeader(ctypes.Structure):
            _fields_ = [("size",self.w.DWORD),("width",self.w.LONG),("height",self.w.LONG),
                ("planes",self.w.WORD),("bits",self.w.WORD),("compression",self.w.DWORD),
                ("image_size",self.w.DWORD),("xppm",self.w.LONG),("yppm",self.w.LONG),
                ("colors_used",self.w.DWORD),("colors_important",self.w.DWORD)]
        class BitmapInfo(ctypes.Structure):
            _fields_ = [("header",BitmapInfoHeader),("colors",self.w.DWORD*1)]
        info = BitmapInfo()
        info.header = BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader),width,-height,1,32,0,width*height*4,0,0,0,0)
        window_dc = memory_dc = bitmap = previous = None
        try:
            window_dc = self.user32.GetWindowDC(hwnd)
            if not window_dc: raise Blocked("Cannot acquire the game window capture DC.")
            memory_dc = self.gdi32.CreateCompatibleDC(window_dc)
            if not memory_dc: raise Blocked("Cannot create the game window capture DC.")
            bits = ctypes.c_void_p()
            bitmap = self.gdi32.CreateDIBSection(memory_dc,ctypes.byref(info),0,ctypes.byref(bits),None,0)
            if not bitmap or not bits.value: raise Blocked("Cannot create the game window capture bitmap.")
            previous = self.gdi32.SelectObject(memory_dc,bitmap)
            if not previous or previous==ctypes.c_void_p(-1).value:
                previous = None
                raise Blocked("Cannot select the game window capture bitmap.")
            if not self.user32.PrintWindow(hwnd,memory_dc,2):
                raise Blocked("The game rejected PrintWindow capture; background screenshots are unavailable.")
            raw = ctypes.string_at(bits,width*height*4)
            image = Image.frombytes("RGB",(width,height),raw,"raw","BGRX")
            return image.crop((cl,ct,cl+cw,ct+ch))
        finally:
            if previous and memory_dc: self.gdi32.SelectObject(memory_dc,previous)
            if bitmap: self.gdi32.DeleteObject(bitmap)
            if memory_dc: self.gdi32.DeleteDC(memory_dc)
            if window_dc: self.user32.ReleaseDC(hwnd,window_dc)


class BackgroundWindowsDriver:
    """Game-window messages without foreground/global input or activation spoofing.

    Games may ignore these messages while inactive or return black PrintWindow
    frames. Such failures stay explicit; there is no global-input fallback.
    """
    VK = VK_KEYS

    def __init__(self, game_pid, api=None):
        if isinstance(game_pid,bool) or not isinstance(game_pid,int) or game_pid<=0:
            raise ValueError("An exact positive game process PID is required.")
        self.pid,self.api = game_pid,api or _BackgroundWindowAPI()
        self.hwnd = self.api.choose_window(game_pid)
        self.held,self.pending_release = set(),set()
        self.mouse_down = False
        self.mouse_position = (0,0)
        self.lock = threading.RLock()
        self._validate()

    def _validate(self, allow_minimized=False):
        if not self.api.is_window(self.hwnd) or self.api.window_pid(self.hwnd)!=self.pid:
            raise Blocked("The targeted game HWND no longer belongs to the launched process.")
        if not allow_minimized and self.api.minimized(self.hwnd):
            raise Blocked("Restore the game window; background tests cannot run while it is minimized.")
        return self.hwnd

    def _post(self, message, wparam, lparam, cleanup=False):
        hwnd = self._validate(allow_minimized=cleanup)
        self.api.post(hwnd,message,wparam,lparam)

    def _image(self):
        from PIL import ImageStat
        hwnd = self._validate()
        image = self.api.capture(hwnd).convert("RGB")
        self._validate()
        if image.width<=0 or image.height<=0:
            raise CaptureNotReady("The game returned an empty background screenshot.")
        stats = ImageStat.Stat(image)
        if max(stats.stddev)<1:
            raise CaptureNotReady("The game returned a black or flat PrintWindow frame; background capture is unsupported for this frame.")
        return image

    def screenshot(self, path):
        foreground_before = self.api.foreground_pid()
        image = self._image()
        image.save(path,"PNG")
        return {"path":str(path),"width":image.width,"height":image.height,"pid":self.pid,
                "hwnd":int(self.hwnd),"capture_mode":"background_printwindow",
                "foreground_pid_before":foreground_before,"foreground_pid":self.api.foreground_pid()}

    def compare_image(self, template_path, bbox, threshold=8):
        from PIL import Image
        image = self._image()
        if not Path(template_path).is_file():
            raise Blocked("Learn the visual checkpoint template from a saved client screenshot first.")
        with Image.open(template_path) as template:
            result = compare_crop(image,template,bbox,threshold)
        return {**result,"template":str(template_path),"pid":self.pid,"hwnd":int(self.hwnd),
                "capture_mode":"background_printwindow","foreground_pid":self.api.foreground_pid()}

    def click(self, x, y):
        if isinstance(x,bool) or isinstance(y,bool) or not isinstance(x,int) or not isinstance(y,int):
            raise ValueError("Click coordinates must be integer physical pixels.")
        self._validate()
        width,height = self.api.client_size(self.hwnd)
        if not 0<=x<width or not 0<=y<height or x>65535 or y>65535:
            raise Blocked("Click is outside the targeted game client rectangle.")
        position = x | (y<<16)
        with self.lock:
            self.mouse_position = (x,y)
            self._post(0x200,0,position)
            self.mouse_down = True
            try:
                self._post(0x201,1,position)
            finally:
                self._post(0x202,0,position,cleanup=True)
                self.mouse_down = False

    def key(self, key, duration, cancel):
        if key not in KEYS: raise ValueError("Only WASD, space, escape, enter, tab and arrow keys are permitted.")
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0<duration<=30:
            raise ValueError("Key duration must be greater than zero and at most 30 seconds.")
        self._validate()
        with self.lock:
            self.held.add(key)
            try:
                self._post(0x100,self.VK[key],key_message_lparam(key))
            except Exception:
                self.release_all()
                raise
        try:
            deadline = time.monotonic()+duration
            while time.monotonic()<deadline:
                self._validate()
                if cancel.wait(min(0.02,max(0,deadline-time.monotonic()))):
                    raise Cancelled("Run stopped.")
        finally:
            self.release_all()

    def release_all(self):
        with self.lock:
            # Reused/destroyed HWNDs never receive a release intended for the game.
            try: self._validate(allow_minimized=True)
            except Blocked:
                self.held.clear()
                self.mouse_down = False
                return
            for key in list(self.held):
                self._post(0x101,self.VK[key],key_message_lparam(key, up=True),cleanup=True)
                self.held.discard(key)
            if self.mouse_down:
                x,y = self.mouse_position
                self._post(0x202,0,x|(y<<16),cleanup=True)
                self.mouse_down = False


class AttachedWindowsDriver(BackgroundWindowsDriver):
    """Experimental offline process-local cursor with HWND-scoped input messages."""
    def __init__(self, game_pid, api=None, adapter=None, notify_focus=True):
        super().__init__(game_pid,api)
        try:
            if adapter is None:
                from native.input_adapter.client import NativeInputAdapter
                adapter=NativeInputAdapter(game_pid)
            self.adapter=adapter
            self.notify_focus=bool(notify_focus)
            self.focus_notified=False
            self.guard_before=None
            self.last_input_proof=None
        except Exception as error:
            raise Blocked(f"Attached input adapter unavailable: {error}") from error

    def _activate_adapter(self):
        self._validate()
        self.guard_before={"foreground_pid":self.api.foreground_pid(),"cursor":self.api.cursor_position()}
        status=self.adapter.activate()
        if status['pid']!=self.pid or status['hwnd']!=int(self.hwnd):
            self.adapter.deactivate()
            raise Blocked("Native adapter selected a different game window.")
        if self.notify_focus:
            self.focus_notified=True
            self._post(0x1C,1,self.api.foreground_thread())  # WM_ACTIVATEAPP notification only.
            self._post(0x07,0,0)  # WM_SETFOCUS notification; no SetFocus/WM_ACTIVATE.
            time.sleep(.2)
        return status

    def screenshot(self,path):
        result=super().screenshot(path)
        return {**result,"input_mode":"attached_virtual_cursor","adapter":self.adapter.status(),
                "desktop_cursor":self.api.cursor_position(),"last_input_proof":self.last_input_proof}

    def click(self,x,y):
        if isinstance(x,bool) or isinstance(y,bool) or not isinstance(x,int) or not isinstance(y,int):
            raise ValueError("Click coordinates must be integer physical pixels.")
        self._validate()
        width,height=self.api.client_size(self.hwnd)
        if not 0<=x<width or not 0<=y<height:
            raise Blocked("Click is outside the targeted game client rectangle.")
        with self.lock:
            try:
                self._activate_adapter()
                self.adapter.set_cursor(x,y)
                position=x|(y<<16)
                self.mouse_position=(x,y)
                self._post(0x200,0,position)
                self.adapter.set_key(0x01,True)
                self.mouse_down=True
                self._post(0x201,1,position)
                time.sleep(.2)  # Let the background game drain the queued button-down.
                self.adapter.set_key(0x01,False)
                self._post(0x202,0,position,cleanup=True)
                self.mouse_down=False
                time.sleep(.2)  # Retain virtual coordinates through button-up processing.
            finally:
                self.release_all()

    def key(self,key,duration,cancel):
        if key not in KEYS:raise ValueError("Unsupported scenario key.")
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0<duration<=30:
            raise ValueError("Key duration must be greater than zero and at most 30 seconds.")
        try:
            self._activate_adapter()
            self.adapter.set_key(VK_KEYS[key],True)
            self.held.add(key)
            self._post(0x100,VK_KEYS[key],key_message_lparam(key))
            deadline=time.monotonic()+duration
            heartbeat=time.monotonic()+1
            while time.monotonic()<deadline:
                self._validate()
                if time.monotonic()>=heartbeat:
                    self.adapter.status()  # Renew the five-second lease only while alive.
                    heartbeat=time.monotonic()+1
                if cancel.wait(min(.02,max(0,deadline-time.monotonic()))):raise Cancelled("Run stopped.")
        finally:
            # Cleanup must not depend on a successful key-down or connected pipe.
            try:
                self.adapter.set_key(VK_KEYS[key],False)
                super().release_all()
                cancel.wait(.2)
            finally:
                self.release_all()

    def release_all(self):
        try:
            super().release_all()
        finally:
            try:
                if self.focus_notified and self.api.foreground_pid()!=self.pid:
                    self._post(0x08,0,0,cleanup=True)  # WM_KILLFOCUS before adapter deactivation.
                    self._post(0x1C,0,self.api.foreground_thread(),cleanup=True)
                    time.sleep(.2)
            finally:
                self.focus_notified=False
                try:self.adapter.deactivate()
                except Exception:
                    # Lost IPC is still bounded by the DLL's five-second watchdog.
                    pass
                if self.guard_before is not None:
                    before=self.guard_before
                    self.guard_before=None
                    after={"foreground_pid":self.api.foreground_pid(),"cursor":self.api.cursor_position()}
                    changed_to_game=before["foreground_pid"]!=self.pid and after["foreground_pid"]==self.pid
                    self.last_input_proof={"before":before,"after":after,"unchanged":before==after,
                                           "foreground_changed_to_game":changed_to_game,"observed_at":utc_now()}
                    if changed_to_game:
                        raise Blocked("Desktop foreground changed to the game during attached input; further controls stopped.")


class Runner:
    def __init__(self, driver, emit, has_milestone, movement_evidence=None, screenshot_dir=Path("runs"), template_dir=TEMPLATE_DIR, position_sampler=None):
        self.driver, self.emit, self.has_milestone = driver, emit, has_milestone
        self.movement_evidence = movement_evidence
        self.position_sampler = position_sampler
        self.screenshot_dir = Path(screenshot_dir)
        self.template_dir = Path(template_dir).resolve()
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.state = {"status": "idle", "steps": [], "screenshots": []}

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def _event(self, kind, **data):
        event = {"type": kind, "time": utc_now(), "run_id": self.state.get("run_id"), **data}
        with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(event) + "\n")
        self.emit(kind, event)

    @staticmethod
    def validate(scenario):
        if not isinstance(scenario, dict) or not isinstance(scenario.get("steps"), list):
            raise ValueError("Scenario requires a steps array.")
        if not 1 <= len(scenario["steps"]) <= 100:
            raise ValueError("Scenario must contain between 1 and 100 steps.")
        for step in scenario["steps"]:
            if not isinstance(step, dict) or step.get("action") not in {"wait", "wait_milestone", "wait_image", "click", "key", "screenshot"}:
                raise ValueError("Unsupported scenario action.")
            if step["action"] == "key" and step.get("key") not in KEYS:
                raise ValueError("Unsupported scenario key.")
            if step["action"] == "click" and any(isinstance(step.get(k), bool) or not isinstance(step.get(k), int) for k in ("x", "y")):
                raise ValueError("Click requires integer x/y coordinates.")
            if step["action"] == "wait_milestone" and not isinstance(step.get("milestone"), str):
                raise ValueError("wait_milestone requires a milestone name.")
            if step["action"] == "wait_milestone" and type(step.get("fresh", False)) is not bool:
                raise ValueError("Milestone fresh must be a boolean.")
            if step["action"] == "wait_image":
                validate_bbox(step.get("bbox"))
                validate_threshold(step.get("threshold", 8))
                if not isinstance(step.get("template"), str) or not step["template"].strip():
                    raise ValueError("wait_image requires a learned template PNG filename.")
            for field, default, upper in (("duration", 0.1, 30), ("timeout", 30, 300)):
                number = step.get(field, default)
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 < number <= upper:
                    raise ValueError(f"{field} must be greater than zero and at most {upper} seconds.")
        return scenario

    def start(self, scenario):
        self.validate(scenario)
        for step in scenario["steps"]:
            if step["action"] == "wait_image":
                resolve_template(step["template"], self.template_dir)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise Blocked("A scenario is already running.")
            self.cancel.clear()
            run_id = uuid.uuid4().hex
            self.run_dir = self.screenshot_dir / run_id
            self.run_dir.mkdir(parents=True, exist_ok=False)
            self.started_epoch = time.time()
            self.state = {"run_id": run_id, "name": scenario.get("name", "Custom scenario"), "status": "running", "started_at": utc_now(),
                          "steps": [], "screenshots": [], "artifact_dir": str(self.run_dir)}
            (self.run_dir / "scenario.json").write_text(json.dumps(scenario, indent=2), encoding="utf-8")
            self.thread = threading.Thread(target=self._run, args=(json.loads(json.dumps(scenario)),), daemon=True)
            self.thread.start()
        return self.snapshot()

    def stop(self):
        self.cancel.set()
        # The owning runner thread releases input in its finally block.
        return self.snapshot()

    def _capture(self, index, phase):
        path = self.run_dir / f"{index:03}-{phase}.png"
        try:
            data = self.driver.screenshot(path)
            result = {"step": index, "phase": phase, "time": utc_now(), **(data or {"path": str(path)})}
        except Exception as error:
            result = {"step": index, "phase": phase, "time": utc_now(), "error": str(error)}
        with self.lock:
            self.state["screenshots"].append(result)
        self._event("screenshot", **result)

    def _wait(self, duration):
        deadline = time.monotonic() + duration
        while True:
            if self.cancel.is_set():
                raise Cancelled("Run stopped.")
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return
            if self.cancel.wait(remaining):
                raise Cancelled("Run stopped.")

    def _wait_image(self, index, step, result):
        import hashlib
        source_template = resolve_template(step["template"], self.template_dir)
        if not source_template.is_file():
            raise Blocked("Learn the visual checkpoint template from a saved client screenshot first.")
        if source_template.stat().st_size > 64*1024*1024:
            raise Blocked("Visual checkpoint template is too large.")
        # Pin the exact learned pixels into this run, preserving reproducible evidence
        # even if the dashboard learns a replacement while the scenario is running.
        pixels = source_template.read_bytes()
        template = self.run_dir / "templates" / f"{index:03}-{source_template.name}"
        template.parent.mkdir(exist_ok=True)
        template.write_bytes(pixels)
        provenance = {"source_template": str(source_template), "template_sha256": hashlib.sha256(pixels).hexdigest()}
        deadline = time.monotonic() + step.get("timeout", 30)
        last = None
        def timeout_message():
            diagnostic=last.get("error") or f"last RMS {last.get('rms')}, threshold {step.get('threshold',8)}"
            return f"Visual checkpoint not observed: {step['template']} ({diagnostic})"
        while True:
            if self.cancel.is_set():
                raise Cancelled("Run stopped.")
            if last is not None and time.monotonic() >= deadline:
                raise TimeoutError(timeout_message())
            try:
                last = {**self.driver.compare_image(template, step["bbox"], step.get("threshold", 8)), **provenance}
            except CaptureNotReady as error:
                last={"matched":False,"error":str(error),"transient_capture":True,**provenance}
                with self.lock:
                    result["transient_capture_count"]=result.get("transient_capture_count",0)+1
                    result["last_capture_blocked"]={"error":str(error),"observed_at":utc_now()}
            with self.lock:
                result["image_match"] = {**last, "observed_at": utc_now()}
            if last.get("matched"):
                self._event("visual_checkpoint", step=index, name=result["name"], **last)
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(timeout_message())
            self._wait(min(0.5, remaining))

    def _run(self, scenario):
        status, reason, movement_requested = "passed", None, False
        started = self.state["started_at"]
        try:
            self._event("run_started")
            for index, step in enumerate(scenario["steps"]):
                if self.cancel.is_set():
                    raise Cancelled("Run stopped.")
                self._capture(index, "before")
                result = {"index": index, "name": step.get("name", step["action"]),
                          "action": step["action"], "started_at": utc_now(), "status": "running"}
                with self.lock:
                    self.state["steps"].append(result)
                self._event("step_started", **result)
                try:
                    action = step["action"]
                    if action == "wait_milestone":
                        deadline = time.monotonic() + step.get("timeout", 30)
                        def observed():
                            if step.get("fresh", False):
                                return self.has_milestone(step["milestone"], since=self.started_epoch)
                            return self.has_milestone(step["milestone"])
                        if step.get("fresh", False):
                            result["milestone_observed_after_epoch"] = self.started_epoch
                        while not observed():
                            if time.monotonic() >= deadline:
                                raise TimeoutError(f"Milestone not observed: {step['milestone']}")
                            self._wait(min(0.1, max(0.001, deadline - time.monotonic())))
                    elif action == "wait_image":
                        self._wait_image(index, step, result)
                    elif action == "wait":
                        self._wait(step.get("duration", 0.1))
                    elif action == "click":
                        if scenario.get("calibrated") is not True:
                            raise Blocked("Calibrate click coordinates from a current game screenshot before running clicks.")
                        self.driver.click(step["x"], step["y"])
                    elif action == "key":
                        movement_key = step["key"] in {"w", "a", "s", "d", "space"}
                        movement_requested |= movement_key
                        position_before = None
                        if movement_key and self.position_sampler:
                            position_before = self.position_sampler()
                            (self.run_dir / f"{index:03}-position-before.json").write_text(json.dumps(position_before, indent=2), encoding="utf-8")
                            if position_before.get("status") != "sampled":
                                raise Blocked("Movement requires a valid possessed-pawn sample: " + position_before.get("error", "incomplete evidence"))
                            if self.cancel.is_set():
                                raise Cancelled("Run stopped.")
                        self.driver.key(step["key"], step.get("duration", 0.1), self.cancel)
                        if position_before is not None:
                            from tools.probe_movement import compare_snapshots
                            position_after = self.position_sampler()
                            (self.run_dir / f"{index:03}-position-after.json").write_text(json.dumps(position_after, indent=2), encoding="utf-8")
                            comparison = compare_snapshots(position_before, position_after)
                            proof_path = self.run_dir / f"{index:03}-position-comparison.json"
                            proof_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
                            observed = {key: value for key, value in comparison.items() if key not in ("before", "after")}
                            observed["path"] = str(proof_path)
                            with self.lock:
                                result["position_observation"] = observed
                            self._event("position_observation", step=index, **observed)
                    with self.lock:
                        result["status"] = "passed"
                except BaseException as error:
                    with self.lock:
                        result.update(status="cancelled" if isinstance(error, Cancelled) else "blocked" if isinstance(error, Blocked) else "failed", error=str(error))
                    raise
                finally:
                    with self.lock:
                        result["finished_at"] = utc_now()
                    self._capture(index, "after")
                    self._event("step_finished", **result)
            if movement_requested:
                evidence = self.movement_evidence(started) if self.movement_evidence else None
                if not evidence:
                    status, reason = "inconclusive", "Movement input sent; no authoritative movement evidence was observed."
                else:
                    self._event("movement_evidence", evidence=evidence)
        except Cancelled as error:
            status, reason = "cancelled", str(error)
        except Blocked as error:
            status, reason = "blocked", str(error)
        except Exception as error:
            status, reason = "failed", str(error)
        finally:
            try:
                self.driver.release_all()
            except Exception as error:
                status, reason = "failed", f"Input cleanup failed: {error}"
            with self.lock:
                self.state.update(status=status, reason=reason, finished_at=utc_now())
                pending = sorted(getattr(self.driver, "pending_release", set()))
                if pending:
                    self.state["input_cleanup"] = {"pending_keys": pending,
                        "reason": "Game lost focus. Game key releases were targeted to its original window; global releases are deferred until the next tester action with the same game PID in the foreground."}
            (self.run_dir / "result.json").write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
            self._event("run_finished", status=status, reason=reason)
