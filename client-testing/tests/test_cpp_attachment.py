import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reviewed_cpp_adapter as cpp
from ashes_testing.input import adapter_contract
from ashes_testing.telemetry import Unavailable


class CppAttachmentGuards(unittest.TestCase):
    def setUp(self):
        self.native = Mock()
        self.native.proof.return_value = {'pid': 123, 'process_created_filetime': 456}
        self.gate = Mock()
        self.gate.verify.return_value = {'adapter_profile': 'cpp-release-shift-0c32ad42'}

    def test_changed_lifetime_refuses_before_modules_or_loader(self):
        with patch.object(cpp, 'NativeTelemetry', return_value=self.native), patch.object(cpp, 'loaded_adapter_paths') as modules:
            with self.assertRaises(Unavailable):
                cpp.attach(123, 457)
            modules.assert_not_called()

    def test_wrong_profile_refuses_before_modules_or_loader(self):
        self.gate.verify.return_value = {'adapter_profile': 'legacy'}
        with patch.object(cpp, 'NativeTelemetry', return_value=self.native), patch.object(cpp, 'InputGate', return_value=self.gate), patch.object(cpp, 'loaded_adapter_paths') as modules:
            with self.assertRaises(Unavailable):
                cpp.attach(123, 456)
            modules.assert_not_called()

    def test_any_existing_adapter_refuses_without_constructing_loader(self):
        with patch.object(cpp, 'NativeTelemetry', return_value=self.native), patch.object(cpp, 'InputGate', return_value=self.gate), patch.object(cpp, 'reviewed_contract'), patch.object(cpp, 'loaded_adapter_paths', return_value=[Path('legacy.dll')]):
            with self.assertRaises(Unavailable):
                cpp.attach(123, 456)

    def test_debug_or_arbitrary_path_cannot_be_pinned(self):
        for path in (cpp.CPP_DLL.parent.parent / 'shift-candidate-0c32ad42/ashes_input_adapter.dll', Path('unreviewed.dll')):
            with self.subTest(path=path), self.assertRaises(Unavailable):
                adapter_contract(path, [{'path': str(path), 'size': 1, 'sha256': 'a', 'protocol_version': 2, 'build_id': 1}])

    def test_manifest_digest_change_refuses(self):
        with patch.object(cpp, 'adapter_contract', return_value={'manifest_sha256': 'wrong'}):
            with self.assertRaises(Unavailable):
                cpp.reviewed_contract()


if __name__ == '__main__':
    unittest.main()
