import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_ue4ss import install, target


class InstallTests(unittest.TestCase):
    def test_traversal_and_unowned_paths_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ['../ue4ss/file', 'ue4ss/../../file', '/ue4ss/file', 'ue4ss\\file',
                         'ue4ss/file:stream', 'EOSSDK-Win64-Shipping.dll']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    target(Path(temp), name)

    def fixture(self, root):
        stage, game = root / 'stage', root / 'game'
        stage.mkdir(); game.mkdir()
        files = {}
        for name in ['dwmapi.dll', 'ue4ss/UE4SS.dll']:
            p = stage / name
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(b'fixture')
            files[name] = {'size': 7, 'sha256': hashlib.sha256(b'fixture').hexdigest()}
        manifest = root / 'stage.json'
        manifest.write_text(json.dumps({'files': files}))
        return stage, game, manifest

    def test_existing_proxy_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            stage, game, manifest = self.fixture(Path(temp))
            (game / 'dwmapi.dll').write_bytes(b'existing')
            with self.assertRaises(RuntimeError):
                install(game, stage, manifest)
            self.assertEqual((game / 'dwmapi.dll').read_bytes(), b'existing')

    def test_changed_stage_refuses_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            stage, game, manifest = self.fixture(Path(temp))
            (stage / 'ue4ss/UE4SS.dll').write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                install(game, stage, manifest)
            self.assertEqual(list(game.iterdir()), [])

    def test_validated_trial_copy_records_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            stage, game, manifest = self.fixture(Path(temp))
            result = install(game, stage, manifest)
            self.assertEqual(result['mods_enabled'], [])
            self.assertEqual((game / 'ue4ss/UE4SS.dll').read_bytes(), b'fixture')

    def test_failed_copy_removes_partial_owned_files(self):
        with tempfile.TemporaryDirectory() as temp:
            stage, game, manifest = self.fixture(Path(temp))
            with patch('install_ue4ss.shutil.copyfileobj', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    install(game, stage, manifest)
            self.assertEqual(list(game.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
