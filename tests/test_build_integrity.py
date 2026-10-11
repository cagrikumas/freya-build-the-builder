import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import build


class BuildIntegrityTests(unittest.TestCase):
    def test_repairs_cannot_remove_or_redefine_existing_evidence(self):
        original = {'checks': [{'name': 'required', 'expect': 'policy'}],
                    'smoke': {'expected_fragments': ['required']},
                    'scenarios': [{'success_criteria': 'policy'}]}
        for key in original:
            candidate = copy.deepcopy(original)
            candidate.pop(key)
            with self.assertRaisesRegex(ValueError, 'preserve the original tests'):
                build.preserve_tests(original, candidate)
        candidate = copy.deepcopy(original)
        candidate['checks'][0]['expect'] = 'always pass'
        with self.assertRaises(ValueError): build.preserve_tests(original, candidate)
        candidate = copy.deepcopy(original)
        candidate['checks'].append({'name': 'new coverage'})
        self.assertEqual(build.preserve_tests(original, candidate), candidate)

    def test_unsafe_repair_code_never_reaches_execution_checks(self):
        with patch.object(build, 'validate', return_value=['Forbidden code']), \
             patch.object(build, 'check_examples') as execute:
            errors = build.validate_and_check({'nodes': {}}, {'checks': [{}]}, {})
        execute.assert_not_called()
        self.assertEqual(errors, ['Forbidden code'])
