import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from lab.automation import AttachedWindowsDriver, BackgroundWindowsDriver, Blocked, Cancelled, CaptureNotReady, Runner, WindowsDriver, compare_crop, learn_template, resolve_template
from tools.import_capture import normalize_fields
from native.input_adapter.client import AdapterBuildMismatch, AdapterError, MAGIC, RESPONSE, decode_response


class FakeDriver:
    def __init__(self):
        self.actions = []
        self.release_count = 0

    def screenshot(self, path):
        path.write_bytes(b"test screenshot")
        return {"path": str(path), "width": 800, "height": 600}

    def click(self, x, y):
        self.actions.append(("click", x, y))

    def key(self, key, duration, cancel):
        self.actions.append(("key", key))
        if cancel.wait(duration):
            raise Cancelled("Run stopped.")

    def release_all(self):
        self.release_count += 1


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.driver = FakeDriver()
        self.events = []
        self.templates = Path(self.temp.name)/"templates"

    def runner(self, milestone=lambda _: False, movement=None):
        return Runner(self.driver, lambda kind, detail: self.events.append((kind, detail)),
                      milestone, movement, Path(self.temp.name), self.templates)

    def finish(self, runner):
        runner.thread.join(3)
        self.assertFalse(runner.thread.is_alive())
        return runner.snapshot()

    def test_unobserved_login_gate_prevents_click(self):
        runner = self.runner()
        runner.start({"calibrated": True, "steps": [
            {"action": "wait_milestone", "milestone": "authentication", "timeout": 0.03},
            {"action": "click", "x": 400, "y": 300}]})
        result = self.finish(runner)
        self.assertEqual(result["status"], "failed")
        self.assertIn("authentication", result["reason"])
        self.assertEqual(self.driver.actions, [])
        self.assertEqual(len(result["screenshots"]), 2)

    def test_click_requires_explicit_calibration(self):
        runner = self.runner()
        runner.start({"steps": [{"action": "click", "x": 10, "y": 20}]})
        self.assertEqual(self.finish(runner)["status"], "blocked")
        self.assertEqual(self.driver.actions, [])

    def test_fresh_world_gate_rejects_previous_world_load(self):
        old_observation = time.time()-60
        runner = self.runner(lambda name, since=None: since is None or old_observation >= since)
        runner.start({"calibrated": True, "steps": [
            {"action":"wait_milestone", "milestone":"world_loaded", "fresh":True, "timeout":0.03},
            {"action":"click", "x":400, "y":300}]})
        self.assertEqual(self.finish(runner)["status"], "failed")
        self.assertEqual(self.driver.actions, [])

    def test_fresh_world_gate_accepts_observation_after_play(self):
        observed_at = {"world_loaded":time.time()-60}
        def click(x, y):
            self.driver.actions.append(("click",x,y))
            observed_at["world_loaded"] = time.time()
        self.driver.click = click
        runner = self.runner(lambda name, since=None: name in observed_at and (since is None or observed_at[name] >= since))
        runner.start({"calibrated":True, "steps":[
            {"action":"click", "x":640, "y":692},
            {"action":"wait_milestone", "milestone":"world_loaded", "fresh":True, "timeout":0.03}]})
        self.assertEqual(self.finish(runner)["status"], "passed")

    def test_movement_without_authoritative_evidence_is_inconclusive(self):
        runner = self.runner()
        runner.start({"steps": [{"action": "key", "key": "w", "duration": 0.01}]})
        result = self.finish(runner)
        self.assertEqual(result["status"], "inconclusive")
        self.assertGreater(self.driver.release_count, 0)
        report = json.loads((Path(result["artifact_dir"]) / "result.json").read_text())
        self.assertEqual(report["status"], "inconclusive")

    def test_position_change_is_saved_without_passing_walking(self):
        from tests.test_movement_probe import sample
        samples = iter([sample(), sample((103., 204., 300.), 2_000_000_000)])
        runner = self.runner()
        runner.position_sampler = lambda: next(samples)
        runner.start({"steps": [{"action": "key", "key": "w", "duration": 0.01}]})
        result = self.finish(runner)
        self.assertEqual(result["status"], "inconclusive")
        observation = result["steps"][0]["position_observation"]
        self.assertEqual(observation["delta_cm"], [3., 4., 0.])
        self.assertFalse(observation["server_authoritative_walking_verified"])
        self.assertTrue(Path(observation["path"]).is_file())

    def test_missing_possession_prevents_movement_input(self):
        runner = self.runner()
        runner.position_sampler = lambda: {"status":"blocked", "error":"Missing possessed pawn"}
        runner.start({"steps": [{"action": "key", "key": "w", "duration": 0.01}]})
        self.assertEqual(self.finish(runner)["status"], "blocked")
        self.assertEqual(self.driver.actions, [])

    def test_milestones_and_position_evidence_pass(self):
        runner = self.runner(lambda name: name == "player_spawned", lambda since: {"position_delta": [1, 0, 0]})
        runner.start({"steps": [{"action": "wait_milestone", "milestone": "player_spawned"},
                                 {"action": "key", "key": "w", "duration": 0.01}]})
        self.assertEqual(self.finish(runner)["status"], "passed")
        self.assertTrue(any(kind == "movement_evidence" for kind, _ in self.events))

    def test_stop_interrupts_long_key_and_releases(self):
        entered = threading.Event()
        original = self.driver.key

        def key(*args):
            entered.set()
            original(*args)
        self.driver.key = key
        runner = self.runner()
        runner.start({"steps": [{"action": "key", "key": "w", "duration": 30},
                                 {"action": "click", "x": 1, "y": 1}]})
        self.assertTrue(entered.wait(1))
        runner.stop()
        self.assertEqual(self.finish(runner)["status"], "cancelled")
        self.assertEqual(self.driver.actions, [("key", "w")])
        self.assertGreater(self.driver.release_count, 0)

    def test_only_allowlisted_keys_and_bounded_durations(self):
        runner = self.runner()
        for step in ({"action": "key", "key": "alt"}, {"action": "wait", "duration": 31},
                     {"action": "wait", "duration": float("nan")}, {"action": "click", "x": True, "y": 0}):
            with self.assertRaises(ValueError):
                runner.start({"steps": [step]})

    def test_lost_foreground_blocks_later_inputs_and_cleans_up(self):
        def click(x, y):
            raise Blocked("Game PID must remain the foreground application.")
        self.driver.click = click
        runner = self.runner()
        runner.start({"calibrated": True, "steps": [
            {"action": "click", "x": 20, "y": 30}, {"action": "key", "key": "w"}]})
        result = self.finish(runner)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.driver.actions, [])
        self.assertEqual(self.driver.release_count, 1)
        self.assertEqual(len(result["screenshots"]), 2)

    def visual_driver(self, image):
        from PIL import Image
        self.driver.comparisons = 0

        def compare_image(path, bbox, threshold):
            self.driver.comparisons += 1
            with Image.open(path) as template:
                return compare_crop(image, template, bbox, threshold)
        self.driver.compare_image = compare_image

    def image_step(self, timeout=0.04):
        return {"action":"wait_image", "template":"realm.png", "bbox":[10,10,30,30],
                "threshold":8, "timeout":timeout}

    def test_learned_visual_gate_checks_real_crop_before_click(self):
        from PIL import Image
        image = Image.new("RGB", (100,100), (20,30,40))
        metadata = learn_template(image, "realm.png", [10,10,30,30], self.templates)
        self.assertEqual(metadata["width"], 20)
        self.assertEqual(metadata["source_width"], 100)
        self.assertEqual(len(metadata["sha256"]), 64)
        self.visual_driver(image)
        runner = self.runner()
        runner.start({"calibrated":True, "steps":[self.image_step(), {"action":"click", "x":15,"y":15}]})
        result = self.finish(runner)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["steps"][0]["image_match"]["rms"], 0)
        self.assertEqual(result["steps"][0]["image_match"]["template_sha256"], metadata["sha256"])
        self.assertTrue((Path(result["artifact_dir"])/"templates"/"000-realm.png").is_file())
        self.assertEqual(self.driver.actions, [("click",15,15)])
        self.assertTrue(any(kind == "visual_checkpoint" for kind, _ in self.events))
        self.assertFalse(any(kind in ("world_loaded", "player_spawned", "movement") for kind, _ in self.events))

    def test_wrong_screen_times_out_without_input_or_fast_polling(self):
        from PIL import Image
        expected = Image.new("RGB", (100,100), (20,30,40))
        learn_template(expected, "realm.png", [10,10,30,30], self.templates)
        self.visual_driver(Image.new("RGB", (100,100), "white"))
        runner = self.runner()
        runner.start({"calibrated":True, "steps":[self.image_step(), {"action":"click", "x":15,"y":15}]})
        result = self.finish(runner)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Visual checkpoint not observed", result["reason"])
        self.assertGreater(result["steps"][0]["image_match"]["rms"], 8)
        self.assertEqual(self.driver.comparisons, 1)
        self.assertEqual(self.driver.actions, [])

    def test_visual_gate_cancel_stops_polling_and_future_keys(self):
        from PIL import Image
        learn_template(Image.new("RGB", (100,100), "black"), "realm.png", [10,10,30,30], self.templates)
        self.visual_driver(Image.new("RGB", (100,100), "white"))
        entered = threading.Event()
        original = self.driver.compare_image

        def compare(*args):
            result = original(*args)
            entered.set()
            return result
        self.driver.compare_image = compare
        runner = self.runner()
        runner.start({"steps":[self.image_step(30), {"action":"key", "key":"w"}]})
        self.assertTrue(entered.wait(1))
        runner.stop()
        self.assertEqual(self.finish(runner)["status"], "cancelled")
        self.assertEqual(self.driver.actions, [])
        self.assertGreater(self.driver.release_count, 0)

    def test_visual_template_paths_cannot_escape_configured_directory(self):
        runner = self.runner()
        step = self.image_step()
        step["template"] = "../outside.png"
        with self.assertRaises(Blocked):
            runner.start({"steps":[step]})
        with self.assertRaises(Blocked):
            resolve_template(str(Path(self.temp.name)/"outside.png"), self.templates)
        with self.assertRaises(Blocked):
            resolve_template("capture.json", self.templates)

    def test_visual_gate_missing_template_blocks_instead_of_clicking(self):
        runner = self.runner()
        runner.start({"calibrated":True, "steps":[self.image_step(), {"action":"click", "x":15,"y":15}]})
        self.assertEqual(self.finish(runner)["status"], "blocked")
        self.assertEqual(self.driver.actions, [])

    def test_visual_gate_retries_transient_black_frame_then_preserves_diagnostic(self):
        from PIL import Image
        image=Image.new("RGB",(100,100),(20,30,40))
        learn_template(image,"realm.png",[10,10,30,30],self.templates)
        self.visual_driver(image)
        compare=self.driver.compare_image
        attempts=[]
        def transient(*args):
            attempts.append(1)
            if len(attempts)==1:raise CaptureNotReady("Black loading frame")
            return compare(*args)
        self.driver.compare_image=transient
        runner=self.runner()
        runner.start({"calibrated":True,"steps":[self.image_step(1),{"action":"click","x":15,"y":15}]})
        result=self.finish(runner)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['steps'][0]['transient_capture_count'],1)
        self.assertEqual(result['steps'][0]['last_capture_blocked']['error'],'Black loading frame')
        self.assertTrue(result['steps'][0]['image_match']['matched'])
        self.assertEqual(self.driver.actions,[("click",15,15)])

    def test_permanent_flat_frame_times_out_without_following_input(self):
        from PIL import Image
        learn_template(Image.new("RGB",(100,100)),"realm.png",[10,10,30,30],self.templates)
        def flat(*args):raise CaptureNotReady("Flat frame remains")
        self.driver.compare_image=flat
        runner=self.runner()
        runner.start({"calibrated":True,"steps":[self.image_step(),{"action":"click","x":15,"y":15}]})
        result=self.finish(runner)
        self.assertEqual(result['status'],'failed')
        self.assertIn('Flat frame remains',result['reason'])
        self.assertEqual(self.driver.actions,[])

    def test_flat_frame_retry_is_cancellable(self):
        from PIL import Image
        learn_template(Image.new("RGB",(100,100)),"realm.png",[10,10,30,30],self.templates)
        entered=threading.Event()
        def flat(*args):entered.set();raise CaptureNotReady("Black loading frame")
        self.driver.compare_image=flat
        runner=self.runner()
        runner.start({"steps":[self.image_step(30),{"action":"key","key":"w"}]})
        self.assertTrue(entered.wait(1));runner.stop()
        self.assertEqual(self.finish(runner)['status'],'cancelled')
        self.assertEqual(self.driver.actions,[])

    def test_visual_validation_rejects_nonfinite_threshold_and_bad_bbox(self):
        runner = self.runner()
        for patch in ({"threshold":float("nan")}, {"threshold":float("inf")}, {"threshold":65},
                      {"threshold":True}, {"bbox":[0,0,0,3]}, {"bbox":[-1,0,5,5]},
                      {"bbox":[0,True,5,5]}, {"bbox":[0,0,5]}, {"bbox":[0,0,17000,5]}):
            step = {**self.image_step(), **patch}
            with self.assertRaises(ValueError):
                runner.start({"steps":[step]})


class VisualComparisonTests(unittest.TestCase):
    def test_pixel_rms_uses_all_color_channels_and_threshold(self):
        from PIL import Image
        black = Image.new("RGB", (20,20), "black")
        near = Image.new("RGB", (10,10), (3,6,9))
        result = compare_crop(black, near, [5,5,15,15], threshold=6)
        self.assertAlmostEqual(result["rms"], (42)**.5)
        self.assertFalse(result["matched"])
        self.assertTrue(compare_crop(black, near, [5,5,15,15], threshold=7)["matched"])

    def test_resolution_and_client_bounds_are_never_silently_scaled(self):
        from PIL import Image
        image = Image.new("RGB", (20,20), "black")
        with self.assertRaises(Blocked):
            compare_crop(image, Image.new("RGB", (11,10)), [0,0,10,10])
        with self.assertRaises(Blocked):
            compare_crop(image, Image.new("RGB", (10,10)), [15,15,25,25])


class FakeWindowAPI:
    """Deliberately has no global cursor, focus or keyboard APIs."""
    def __init__(self, pid=123):
        from PIL import Image, ImageDraw
        self.pid,self.hwnd,self.exists,self.iconic = pid,99,True,False
        self.messages,self.captures = [],[]
        self.image = Image.new("RGB",(100,80),"black")
        ImageDraw.Draw(self.image).rectangle((10,10,80,50),fill="white")
        self.foreground = "unrelated user application"
        self.real_foreground_pid=456
        self.real_cursor=[400,500]

    def choose_window(self,pid):
        if pid!=self.pid: raise Blocked("No game window")
        return self.hwnd

    def is_window(self,hwnd): return self.exists and hwnd==self.hwnd
    def window_pid(self,hwnd): return self.pid
    def foreground_pid(self): return self.real_foreground_pid
    def foreground_thread(self): return 789
    def cursor_position(self): return list(self.real_cursor)
    def minimized(self,hwnd): return self.iconic
    def client_size(self,hwnd): return self.image.size
    def capture(self,hwnd):
        self.captures.append(hwnd)
        return self.image.copy()
    def post(self,hwnd,message,wparam,lparam):
        self.messages.append((hwnd,message,wparam,lparam))


class BackgroundDriverTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeWindowAPI()
        self.driver = BackgroundWindowsDriver(123,self.api)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_click_posts_only_to_game_with_user_focus_unchanged(self):
        self.driver.click(25,30)
        self.assertEqual(self.api.messages,[(99,0x200,0,25|(30<<16)),
            (99,0x201,1,25|(30<<16)),(99,0x202,0,25|(30<<16))])
        self.assertEqual(self.api.foreground,"unrelated user application")
        self.assertFalse(self.driver.mouse_down)

    def test_key_hold_cancel_releases_to_game_after_focus_change(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.driver.key("w",30,cancel)
        self.assertEqual(self.api.messages,[(99,0x100,0x57,1|(0x11<<16)),
            (99,0x101,0x57,1|(0x11<<16)|(3<<30))])
        self.assertEqual(self.driver.held,set())
        self.assertEqual(self.api.foreground,"unrelated user application")

    def test_reused_window_for_other_process_never_receives_input(self):
        self.api.pid = 999
        with self.assertRaises(Blocked): self.driver.click(25,30)
        with self.assertRaises(Blocked): self.driver.key("w",.01,threading.Event())
        self.driver.held.add("w")
        self.driver.release_all()
        self.assertEqual(self.api.messages,[])

    def test_minimized_game_blocks_capture_and_click_but_can_receive_cleanup(self):
        self.api.iconic = True
        with self.assertRaises(Blocked): self.driver.screenshot(Path(self.temp.name)/"screen.png")
        with self.assertRaises(Blocked): self.driver.click(25,30)
        self.driver.held.add("w")
        self.driver.release_all()
        self.assertEqual(self.api.captures,[])
        self.assertEqual([item[1] for item in self.api.messages],[0x101])

    def test_background_capture_uses_only_target_and_flat_frames_fail(self):
        from PIL import Image
        output = Path(self.temp.name)/"screen.png"
        result = self.driver.screenshot(output)
        self.assertTrue(output.is_file())
        self.assertEqual(result["capture_mode"],"background_printwindow")
        self.assertEqual(result["hwnd"],99)
        self.assertEqual(result["foreground_pid"],456)
        self.assertEqual(result["foreground_pid_before"],456)
        self.assertEqual(self.api.captures,[99])
        for color in ("black","white","red"):
            self.api.image = Image.new("RGB",(100,80),color)
            with self.assertRaises(Blocked): self.driver.screenshot(Path(self.temp.name)/"flat.png")
        self.assertFalse((Path(self.temp.name)/"flat.png").exists())

    def test_background_checkpoint_matches_same_crop_without_input(self):
        metadata = learn_template(self.api.image,"ready.png",[10,10,50,40],Path(self.temp.name))
        result = self.driver.compare_image(Path(self.temp.name)/metadata["template"],[10,10,50,40],0)
        self.assertTrue(result["matched"])
        self.assertEqual(result["capture_mode"],"background_printwindow")
        self.assertEqual(self.api.messages,[])

    def test_invalid_coordinate_or_key_never_posts(self):
        for point in ((-1,2),(100,20),(1,80),(True,2)):
            with self.assertRaises((Blocked,ValueError)): self.driver.click(*point)
        with self.assertRaises(ValueError): self.driver.key("alt",.1,threading.Event())
        for duration in (0,-1,True,float("nan"),float("inf"),31):
            with self.assertRaises(ValueError): self.driver.key("w",duration,threading.Event())
        self.assertEqual(self.api.messages,[])

    def test_navigation_keys_use_exact_virtual_keys_and_extended_scan_metadata(self):
        cancel = threading.Event()
        cancel.set()
        for key,vk,scan,extended in (("tab",0x09,0x0F,False),("up",0x26,0x48,True),
                                    ("down",0x28,0x50,True),("left",0x25,0x4B,True),
                                    ("right",0x27,0x4D,True)):
            with self.subTest(key=key):
                self.api.messages.clear()
                Runner.validate({"steps":[{"action":"key","key":key,"duration":.05}]})
                with self.assertRaises(Cancelled): self.driver.key(key,.05,cancel)
                metadata = 1|(scan<<16)|((1<<24) if extended else 0)
                self.assertEqual(self.api.messages,[(99,0x100,vk,metadata),
                    (99,0x101,vk,metadata|(3<<30))])
                self.assertEqual(self.driver.held,set())
                self.assertEqual(self.api.foreground,"unrelated user application")


class ForegroundKeyEncodingTests(unittest.TestCase):
    def test_sendinput_arrows_are_extended_and_tab_is_not(self):
        # Exercise real driver encoding while replacing delivery with a pure recorder.
        from types import SimpleNamespace
        driver = WindowsDriver.__new__(WindowsDriver)
        driver.Input = lambda **values: SimpleNamespace(**values)
        driver.KeyboardInput = lambda vk,scan,flags,when,extra: SimpleNamespace(vk=vk,scan=scan,flags=flags)
        records = []
        driver._send = lambda events: records.extend(events)
        for key,scan in (("up",0x48),("down",0x50),("left",0x4B),("right",0x4D)):
            driver._key_event(key)
            driver._key_event(key,up=True)
            self.assertEqual((records[-2].ki.scan,records[-2].ki.flags),(scan,0x9))
            self.assertEqual((records[-1].ki.scan,records[-1].ki.flags),(scan,0xB))
        driver._key_event("tab")
        driver._key_event("tab",up=True)
        self.assertEqual((records[-2].ki.scan,records[-2].ki.flags),(0x0F,0x8))
        self.assertEqual((records[-1].ki.scan,records[-1].ki.flags),(0x0F,0xA))


class FakeAdapter:
    def __init__(self):self.actions=[];self.active=False;self.hwnd=99;self.fail_cursor=False
    def status(self):return {"pid":123,"hwnd":self.hwnd,"active":self.active,"foreground_pid":456}
    def activate(self):self.active=True;self.actions.append(("activate",));return self.status()
    def set_cursor(self,x,y):
        self.actions.append(("cursor",x,y))
        if self.fail_cursor:raise RuntimeError("Pipe lost")
    def set_key(self,key,down):self.actions.append(("key",key,down))
    def deactivate(self):self.active=False;self.actions.append(("deactivate",));return self.status()


class AttachedDriverTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeWindowAPI();self.adapter=FakeAdapter()
        self.driver=AttachedWindowsDriver(123,api=self.api,adapter=self.adapter)
    def test_click_virtualizes_cursor_before_messages_and_deactivates(self):
        self.driver.click(25,30)
        self.assertEqual(self.adapter.actions,[("activate",),("cursor",25,30),("key",1,True),("key",1,False),("deactivate",)])
        self.assertEqual([row[1] for row in self.api.messages],[0x1C,0x07,0x200,0x201,0x202,0x08,0x1C])
        self.assertFalse(self.adapter.active)
        self.assertEqual(self.api.foreground,"unrelated user application")
    def test_cancel_releases_virtual_and_window_key_then_deactivates(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):self.driver.key("right",1,cancel)
        self.assertEqual(self.adapter.actions,[("activate",),("key",0x27,True),("key",0x27,False),("deactivate",)])
        self.assertEqual([row[1] for row in self.api.messages],[0x1C,0x07,0x100,0x101,0x08,0x1C])
        self.assertFalse(self.adapter.active)
        self.assertEqual(self.driver.held,set())
    def test_failed_cursor_command_deactivates_without_click(self):
        self.adapter.fail_cursor=True
        with self.assertRaises(RuntimeError):self.driver.click(25,30)
        self.assertFalse(self.adapter.active)
        self.assertEqual([row[1] for row in self.api.messages],[0x1C,0x07,0x08,0x1C])
    def test_mismatched_native_window_cannot_receive_input(self):
        self.adapter.hwnd=999
        with self.assertRaises(Blocked):self.driver.click(25,30)
        self.assertFalse(self.adapter.active)
        self.assertEqual(self.api.messages,[])
    def test_reused_window_blocks_adapter_activation(self):
        self.api.pid=999
        with self.assertRaises(Blocked):self.driver.click(25,30)
        self.assertEqual(self.adapter.actions,[])

    def test_focus_notifications_are_scoped_inside_active_adapter(self):
        post=self.api.post
        active_states=[]
        def check(*args):active_states.append(self.adapter.active);post(*args)
        self.api.post=check
        self.driver.click(25,30)
        self.assertTrue(all(active_states))
        self.assertEqual(self.api.messages[0],(99,0x1C,1,789))
        self.assertEqual(self.api.messages[-1],(99,0x1C,0,789))
        self.assertTrue(self.driver.last_input_proof['unchanged'])

    def test_user_cursor_motion_in_other_application_is_recorded_without_blocking(self):
        post=self.api.post
        def move(*args):self.api.real_cursor=[600,700];post(*args)
        self.api.post=move
        self.driver.click(25,30)
        self.assertFalse(self.driver.last_input_proof['unchanged'])
        self.assertEqual(self.driver.last_input_proof['after']['cursor'],[600,700])
        self.assertFalse(self.adapter.active)

    def test_transition_to_real_game_foreground_stops_after_cleanup(self):
        post=self.api.post
        def activated(*args):self.api.real_foreground_pid=123;post(*args)
        self.api.post=activated
        with self.assertRaises(Blocked):self.driver.click(25,30)
        self.assertTrue(self.driver.last_input_proof['foreground_changed_to_game'])
        self.assertFalse(self.adapter.active)


class AdapterProtocolTests(unittest.TestCase):
    def response(self,pid=123,build_id=456,status=0):
        return RESPONSE.pack(MAGIC,status,pid,0,23,0,200,300,99,789,build_id)
    def test_status_verifies_resident_build_and_real_foreground(self):
        value=decode_response(self.response(),123,456)
        self.assertEqual(value['build_id'],456)
        self.assertEqual(value['foreground_pid'],789)
        self.assertEqual(decode_response(self.response(build_id=0),123,0)['build_id'],0)
    def test_stale_resident_build_rejected_even_when_it_reports_command_error(self):
        with self.assertRaises(AdapterBuildMismatch):decode_response(self.response(build_id=1,status=13),123,456)
    def test_wrong_process_or_short_response_rejected(self):
        with self.assertRaises(AdapterError):decode_response(self.response(pid=999),123,456)
        with self.assertRaises(AdapterError):decode_response(b'bad',123,456)


class CaptureTests(unittest.TestCase):
    def row(self, payload, source="10.0.0.1", dest="10.0.0.2", sp="1234", dp="5678"):
        return "\t".join(["42", "123.5", source, "", dest, "", sp, dp, "", "", payload, ""])

    def test_unrelated_network_payload_is_omitted(self):
        self.assertIsNone(normalize_fields(self.row("de:ad:be:ef")))
        self.assertIsNone(normalize_fields(self.row("de:ad:a5:5a:02:ef")))

    def test_game_signature_is_observation_without_invented_direction(self):
        row = normalize_fields(self.row("96:76:0c:50:00:01"))
        self.assertEqual(row["direction"], "unknown")
        self.assertEqual(row["kind"], "game_96760c50")
        self.assertEqual(row["size"], 6)
        self.assertEqual(row["hex"], "96760c500001")

    def test_explicit_loopback_port_has_known_direction(self):
        row = normalize_fields(self.row("de:ad:be:ef", "127.0.0.1", "127.0.0.1", "44444", "17089"))
        self.assertEqual(row["direction"], "client_to_server")
        self.assertEqual(row["kind"], "local_lab_payload")

    def test_tls_record_and_malformed_rows_are_omitted(self):
        self.assertIsNone(normalize_fields(self.row("16:03:01:ff", "127.0.0.1", "127.0.0.1", "44444", "17089")))
        self.assertIsNone(normalize_fields("invalid"))
        self.assertIsNone(normalize_fields(self.row("not hex")))


if __name__ == "__main__":
    unittest.main()
