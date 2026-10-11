import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import model


class ModelJsonRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name)
        self.events = []
        self.trace = lambda event, **data: self.events.append((event, data))

    def invoke_outputs(self, outputs):
        answers = iter(outputs)
        def invoke(*args, **kwargs):
            stem = self.run / ('model-%02d' % (len(list(self.run.glob('*.answer.json'))) + 1))
            text = next(answers)
            stem.with_suffix('.answer.json').write_text(text)
            return text, stem
        return invoke

    def test_successful_syntax_repair_preserves_original_and_candidate(self):
        raw = '{"workflow":{"name":"keep this code: } ,"}},}'
        repair = json.dumps({'edits': [{'old': '}},}', 'new': '}}'}]})
        with patch.object(model, '_invoke', side_effect=self.invoke_outputs([raw, repair])) as invoke:
            value = model.call('input', 'compile', self.trace, self.run)
        self.assertEqual(value, {'workflow': {'name': 'keep this code: } ,'}})
        self.assertEqual(invoke.call_count, 2)
        self.assertEqual((self.run / 'model-01.answer.json').read_text(), raw)
        candidate = self.run / 'model-02.repaired-candidate.json'
        self.assertEqual(json.loads(candidate.read_text()), value)
        self.assertEqual(invoke.call_args.args[1], 'compile JSON syntax repair')

    def test_invalid_repair_output_does_not_recurse_and_second_can_succeed(self):
        raw = '{"x":1,}'
        repair = json.dumps({'edits': [{'old': '1,}', 'new': '1}'}]})
        with patch.object(model, '_invoke', side_effect=self.invoke_outputs([raw, 'not JSON', repair])) as invoke:
            self.assertEqual(model.call('input', 'audit', self.trace, self.run), {'x': 1})
        self.assertEqual(invoke.call_count, 3)

    def test_two_failures_stop_without_recursion(self):
        with patch.object(model, '_invoke', side_effect=self.invoke_outputs(['{"x":1,}', '{}', '{}'])) as invoke:
            with self.assertRaisesRegex(ValueError, 'JSON syntax repair failed'):
                model.call('input', 'compile', self.trace, self.run)
        self.assertEqual(invoke.call_count, 3)

    def test_shared_deadline_includes_repair(self):
        clock = [0]
        timeouts = []
        def invoke(*args, **kwargs):
            timeouts.append(kwargs['timeout'])
            clock[0] += 8 if len(timeouts) == 1 else 3
            text = '{"x":1,}' if len(timeouts) == 1 else json.dumps({'edits': [{'old': '1,}', 'new': '1}'}]})
            return text, self.run / ('model-%02d' % len(timeouts))
        with patch.object(model.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(model, '_invoke', side_effect=invoke):
            with self.assertRaisesRegex(TimeoutError, 'budget exhausted'):
                model.call('input', 'compile', self.trace, self.run, timeout=10)
        self.assertEqual(timeouts, [10, 2])

    def test_expired_budget_never_starts_transport(self):
        with patch.object(model, '_invoke') as invoke:
            with self.assertRaises(TimeoutError):
                model.call('input', 'compile', self.trace, self.run, timeout=0)
        invoke.assert_not_called()

    def test_verified_prior_answer_needs_only_repair_transport(self):
        repair = json.dumps({'edits': [{'old': '1,}', 'new': '1}'}]})
        with patch.object(model, '_invoke', side_effect=self.invoke_outputs([repair])) as invoke:
            self.assertEqual(model.recover_answer('{"x":1,}', 'compile', self.trace, self.run,
                                                 original_call_id='imported-model-01'), {'x': 1})
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(self.events[0][1]['original_call_id'], 'imported-model-01')

    def test_edit_bounds_unique_matches_overlap_and_semantic_changes_rejected(self):
        invalid = [
            {'edits': [{'old': 'a', 'new': ''}] * 33},
            {'edits': [{'old': 'a' * 4097, 'new': ''}]},
            {'edits': [{'old': 'aa', 'new': ''}]},
            {'edits': [{'old': 'aaa', 'new': ''}, {'old': 'aaab', 'new': ''}]},
            {'edits': [{'old': 'missing', 'new': ''}]},
            {'edits': [{'old': 'aaa', 'new': 'new policy'}]},
            {'edits': [], 'other': True},
        ]
        for edits in invalid:
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                model._apply_syntax_edits('aaab', edits)
        for raw, old, new in [('{"code":"keep"}', 'keep', 'change'),
                              ('{"amount":123}', '123', '124'),
                              ('{"allowed":false}', 'false', 'true')]:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'string token or literal'):
                model._apply_syntax_edits(raw, {'edits': [{'old': old, 'new': new}]})
        chunks = ['%02d:' % i + 'a' * 2050 for i in range(16)]
        with self.assertRaisesRegex(ValueError, 'total bytes'):
            model._apply_syntax_edits(' '.join(chunks), {'edits': [
                {'old': chunk, 'new': chunk + ' '} for chunk in chunks]})

    def test_strict_parse_rejects_trailing_text_non_json_constants_and_non_object(self):
        for raw in ['{"x":1} trailing', '{"x":NaN}', '[]']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                model._strict_object(raw)


if __name__ == '__main__':
    unittest.main()
