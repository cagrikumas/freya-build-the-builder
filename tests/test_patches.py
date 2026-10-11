import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from patches import apply_patches


class PatchTests(unittest.TestCase):
    def test_correction_and_new_check_preserve_original(self):
        source = {'tool_config': {'a/b': {'post_process_code': 'old'}}, 'checks': []}
        result = apply_patches(source, [
            {'op': 'replace', 'path': '/tool_config/a~1b/post_process_code', 'value': 'corrected'},
            {'op': 'add', 'path': '/checks/-', 'value': {'name': 'regression'}}])
        self.assertEqual(result['tool_config']['a/b']['post_process_code'], 'corrected')
        self.assertEqual(result['checks'], [{'name': 'regression'}])
        self.assertEqual(source['tool_config']['a/b']['post_process_code'], 'old')
        self.assertEqual(source['checks'], [])

    def test_mistyped_target_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_patches({'checks': []}, [{'op': 'replace', 'path': '/cheks', 'value': []}])

    def test_array_bounds_are_not_silently_coerced(self):
        with self.assertRaises(ValueError):
            apply_patches({'checks': []}, [{'op': 'add', 'path': '/checks/9', 'value': 1}])
