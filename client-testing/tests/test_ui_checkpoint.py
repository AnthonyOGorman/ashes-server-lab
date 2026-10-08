import json
import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui_action import referenced_capture
from enter_world import load_calibration
from ashes_testing.telemetry import Unavailable


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'runs').mkdir()
        self.proof = {'pid': 42, 'exe': 'game', 'sha256': 'verified', 'process_created_filetime': 100}
        self.record = self.home / 'runs/capture-test.json'
        self.png = self.home / 'runs/screen-test.png'
        self.value = {'client_proof': dict(self.proof), 'observed_at': time.time(), 'path': str(self.png)}

    def read(self):
        self.record.write_text(json.dumps(self.value))
        with patch('ui_action.HOME', self.home):
            return referenced_capture(self.record, self.proof)

    def test_reused_pid_does_not_reuse_old_ui(self):
        self.value['client_proof']['process_created_filetime'] = 99
        with self.assertRaises(Unavailable):
            self.read()

    def test_old_or_future_checkpoint_refused(self):
        for observed in (time.time() - 181, time.time() + 10):
            self.value['observed_at'] = observed
            with self.assertRaises(Unavailable):
                self.read()

    def test_external_screenshot_refused(self):
        self.value['path'] = str(self.home / 'outside.png')
        with self.assertRaises(Unavailable):
            self.read()

    def test_current_bound_checkpoint_accepted(self):
        record, png = self.read()
        self.assertEqual(record['client_proof'], self.proof)
        self.assertEqual(png, self.png)


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'runs').mkdir()
        self.png = self.home / 'runs/reviewed.png'
        Image.new('RGB', (20, 20), 'blue').save(self.png)
        self.calibration = {'client_size': [20, 20], 'steps': [
            {'source_png': self.png.name, 'bbox': [1, 1, 10, 10],
             'sha256': hashlib.sha256(self.png.read_bytes()).hexdigest()}]}

    def load(self):
        (self.home / 'ui-calibration.json').write_text(json.dumps(self.calibration))
        with patch('enter_world.HOME', self.home):
            return load_calibration()

    def test_changed_reviewed_pixels_refused(self):
        from PIL import Image
        Image.new('RGB', (20, 20), 'red').save(self.png)
        with self.assertRaises(Unavailable):
            self.load()

    def test_wrong_client_dimensions_refused(self):
        self.calibration['client_size'] = [40, 40]
        with self.assertRaises(Unavailable):
            self.load()
