import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import model
import session_trace

THREAD = '0199a213-81c0-7800-8aa1-bbab2a035a53'
OTHER = '0199a213-81c0-7800-8aa1-bbab2a035a54'


class SessionTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run = self.root / 'run'; self.run.mkdir()
        self.home = self.root / 'codex'; self.home.mkdir()
        self.folder = self.home / 'sessions/2026/10/11'; self.folder.mkdir(parents=True)
        self.source = self.folder / ('rollout-2026-10-11T17-00-00-' + THREAD + '.jsonl')
        self.events = self.run / 'model-01.events.jsonl'
        self.events.write_text(json.dumps({'type': 'thread.started', 'thread_id': THREAD}) + '\n')
        self.stem = self.run / 'model-01'
        self.rows = [
            {'timestamp': '2026-10-11T17:00:00Z', 'type': 'session_meta',
             'payload': {'id': THREAD, 'cwd': str(self.run)}},
            {'timestamp': '2026-10-11T17:00:01Z', 'type': 'response_item',
             'payload': {'role': 'user', 'content': 'The complete input'}},
            {'timestamp': '2026-10-11T17:00:02Z', 'type': 'future_unknown',
             'payload': {'large': 'x' * 10000, 'nested': [1, {'answer': 'kept'}]}}
        ]
        self.write_source()

    def tearDown(self):
        self.tmp.cleanup()

    def write_source(self):
        self.source.write_text(''.join(json.dumps(row) + '\n' for row in self.rows))

    def capture(self):
        return session_trace.capture_session(self.events, self.stem, self.run, self.home)

    def test_copies_only_own_session_and_keeps_all_records(self):
        unrelated = self.folder / ('rollout-unrelated-' + OTHER + '.jsonl')
        unrelated.write_text('invalid JSON: must never be opened')
        info = self.capture()
        self.assertEqual(info['records'], len(self.rows))
        self.assertEqual(list(session_trace.records(self.run / info['file'])), self.rows)
        aggregate = list(session_trace.records(self.run / 'full-session.jsonl'))
        self.assertEqual([row['record'] for row in aggregate], self.rows)
        self.assertEqual([row['sequence'] for row in aggregate], [1, 2, 3])
        self.assertTrue(all(row['call_id'] == 'model-01' and row['thread_id'] == THREAD for row in aggregate))
        self.assertEqual([row['at'] for row in aggregate], [row['timestamp'] for row in self.rows])

    def test_missing_session_rejected_without_reading_another(self):
        self.source.rename(self.folder / ('rollout-unrelated-' + OTHER + '.jsonl'))
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            self.capture()

    def test_ambiguous_session_rejected(self):
        (self.folder / ('rollout-another-' + THREAD + '.jsonl')).write_text(self.source.read_text())
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            self.capture()

    def test_metadata_id_mismatch_rejected(self):
        self.rows[0]['payload']['id'] = OTHER; self.write_source()
        with self.assertRaisesRegex(ValueError, 'metadata ID'):
            self.capture()

    def test_other_working_directory_rejected(self):
        self.rows[0]['payload']['cwd'] = str(self.root); self.write_source()
        with self.assertRaisesRegex(ValueError, 'different working directory'):
            self.capture()

    def test_symlinked_session_rejected(self):
        elsewhere = self.root / 'elsewhere.jsonl'; self.source.rename(elsewhere)
        self.source.symlink_to(elsewhere)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.capture()

    def test_invalid_thread_id_rejected(self):
        self.events.write_text(json.dumps({'type': 'thread.started', 'thread_id': '../other'}))
        with self.assertRaisesRegex(ValueError, 'session UUID'):
            self.capture()

    def test_secrets_redacted_but_full_business_evidence_retained(self):
        self.rows[1]['payload'].update({
            'content': 'Input sensitive-runtime-key and fak_examplelongkey plus Bearer live-token',
            'headers': {'Authorization': 'Basic Zm9vOmJhcg==', 'X-Team-Key': 'another-secret'},
            'api_key': 'unknown-credential', 'input_tokens': 123,
            'promise': {'amount': 1250, 'date': '2026-10-16'}})
        self.write_source()
        with patch.dict(os.environ, {'FREYA_API_KEY': 'sensitive-runtime-key'}, clear=True):
            info = self.capture()
        saved = (self.run / info['file']).read_text()
        for value in ('sensitive-runtime-key', 'fak_examplelongkey', 'live-token', 'Zm9vOmJhcg==', 'another-secret', 'unknown-credential'):
            self.assertNotIn(value, saved)
        payload = list(session_trace.records(self.run / info['file']))[1]['payload']
        self.assertEqual(payload['input_tokens'], 123)
        self.assertEqual(payload['promise'], {'amount': 1250, 'date': '2026-10-16'})
        self.assertEqual(list(session_trace.records(self.run / info['file']))[-1], self.rows[-1])

    def test_source_size_limits_raise_without_shortened_success(self):
        with self.assertRaisesRegex(ValueError, 'oversized'):
            list(session_trace.records(self.source, limit=10))
        with patch.object(session_trace, 'MAX_RECORD_BYTES', 64):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                self.capture()
        self.assertFalse(self.stem.with_suffix('.session.jsonl').exists())

    def test_malformed_records_fail_explicitly(self):
        with self.source.open('a') as out: out.write('{broken\n')
        with self.assertRaises(json.JSONDecodeError):
            self.capture()

    def complete_trace(self):
        events = [{'event': 'build_start'}, {'event': 'model_call_start', 'call_id': 'model-01'}]
        aggregate = self.run / 'full-session.jsonl'
        for row in events: session_trace.append_record(aggregate, row)
        info = self.capture()
        result = {'session_trace': 'traces/final/full-session.jsonl', 'workflow_id': 'w'}
        events += [{'event': 'model_session_captured', **info},
                   {'event': 'run_completed', 'completed': True, 'result': result}]
        for row in events[2:]: session_trace.append_record(aggregate, row)
        events.append({'event': 'build_end'})
        return events, result

    def test_complete_attachment_validated_and_omission_rejected(self):
        events, result = self.complete_trace()
        self.assertEqual(session_trace.validate_full_session(self.run, events, result), self.run / 'full-session.jsonl')
        path = self.run / 'full-session.jsonl'
        rows = list(session_trace.records(path))
        rows = [row for row in rows if row.get('sequence') != 2]
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        with self.assertRaisesRegex(ValueError, 'changed or omitted'):
            session_trace.validate_full_session(self.run, events, result)

    def test_missing_model_capture_rejected(self):
        events, result = self.complete_trace()
        events = [row for row in events if row.get('event') != 'model_session_captured']
        with self.assertRaisesRegex(ValueError, 'every model call'):
            session_trace.validate_full_session(self.run, events, result)


class ModelCaptureTests(unittest.TestCase):
    setUp = SessionTraceTests.setUp
    tearDown = SessionTraceTests.tearDown
    write_source = SessionTraceTests.write_source

    def test_success_requires_and_records_full_session(self):
        self.events.unlink()
        def invoke(command, **kwargs):
            self.assertNotIn('--ephemeral', command)
            kwargs['stdout'].write(json.dumps({'type': 'thread.started', 'thread_id': THREAD}) + '\n')
            kwargs['stdout'].write(json.dumps({'type': 'turn.completed', 'usage': {}}) + '\n')
            Path(command[command.index('--output-last-message') + 1]).write_text('{"compiled": true}')
            return subprocess.CompletedProcess(command, 0)
        events = []
        with patch.dict(os.environ, {'CODEX_HOME': str(self.home)}, clear=True), patch.object(model.subprocess, 'run', side_effect=invoke):
            self.assertEqual(model.call('input', 'compile', lambda event, **data: events.append({'event': event, **data}), self.run), {'compiled': True})
        self.assertTrue(any(row['event'] == 'model_session_captured' for row in events))
        self.assertEqual(list(session_trace.records(self.stem.with_suffix('.session.jsonl'))), self.rows)

    def test_timeout_still_archives_available_full_records(self):
        self.events.unlink()
        def timeout(command, **kwargs):
            kwargs['stdout'].write(json.dumps({'type': 'thread.started', 'thread_id': THREAD}) + '\n')
            raise subprocess.TimeoutExpired(command, 1)
        events = []
        with patch.dict(os.environ, {'CODEX_HOME': str(self.home)}, clear=True), patch.object(model.subprocess, 'run', side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired):
                model.call('input', 'compile', lambda event, **data: events.append({'event': event, **data}), self.run)
        self.assertTrue(any(row['event'] == 'model_session_captured' for row in events))
        self.assertEqual(events[-1]['event'], 'model_call_end')
        self.assertEqual(list(session_trace.records(self.stem.with_suffix('.session.jsonl'))), self.rows)


if __name__ == '__main__':
    unittest.main()
