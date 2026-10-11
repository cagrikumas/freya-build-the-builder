import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from patches import apply_patches, apply_with_path_repair, PatchError


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

    def test_invalid_parent_reports_index_and_does_not_mutate_input(self):
        source = {'checks': [{'vars': {'state': {'items': []}}}, {'vars': {}}]}
        patches = [{'op': 'add', 'path': '/new', 'value': 1},
                   {'op': 'replace', 'path': '/checks/1/vars/state/items', 'value': ['a']}]
        with self.assertRaises(PatchError) as caught:
            apply_patches(source, patches)
        self.assertEqual(caught.exception.index, 1)
        self.assertNotIn('new', source)
        self.assertIn('/checks/1/vars/state/items', str(caught.exception))

    def test_model_can_correct_pointer_without_dropping_audit_edits(self):
        source = {'checks': [{'vars': {'state': {'items': []}}}, {'vars': {}}]}
        patches = [{'op': 'add', 'path': '/new', 'value': 1},
                   {'op': 'replace', 'path': '/checks/1/vars/state/items', 'value': ['a']}]
        seen = []
        def repair(original, edits, error):
            seen.append(error.index)
            self.assertEqual(original, source)
            self.assertEqual(edits, patches)
            return {'path': '/checks/0/vars/state/items'}
        result = apply_with_path_repair(source, patches, repair)
        self.assertEqual(seen, [1])
        self.assertEqual(result['new'], 1)
        self.assertEqual(result['checks'][0]['vars']['state']['items'], ['a'])
        self.assertEqual(patches[1]['path'], '/checks/1/vars/state/items')

    def test_pointer_repair_cannot_replace_value_or_suppress_edit(self):
        for answer in ({'path': '/good', 'value': 'weakened'}, {'error': 'ambiguous'},
                       {'path': '/missing/child'}, {'path': 'relative'}, None):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                apply_with_path_repair({'good': 1},
                    [{'op': 'replace', 'path': '/missing/child', 'value': 2}],
                    lambda *args: answer)

    def test_pointer_repair_is_bounded(self):
        seen = []
        def repair(*args):
            seen.append(1)
            return {'path': '/absent' + str(len(seen)) + '/child'}
        with self.assertRaises(PatchError):
            apply_with_path_repair({}, [{'op': 'replace', 'path': '/missing/child', 'value': 1}], repair, limit=2)
        self.assertEqual(len(seen), 2)
