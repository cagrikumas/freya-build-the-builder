import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from compile_resume import import_failed_compile
from session_trace import append_record, records, validate_full_session


class CompileResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'failed'; self.source.mkdir()
        self.destination = self.root / 'resumed'; self.destination.mkdir()
        self.prompt = 'Exact compiler prompt: preserve every source value.\n'
        self.raw = '{"workflow": {"code": "unterminated'
        self.inputs = [{'path': 'private/case/input.json', 'sha256': 'a' * 64}]
        self.thread = '0199a213-81c0-7800-8aa1-bbab2a035a53'
        self.original_records = [
            {'timestamp': '2026-10-11T18:00:00Z', 'type': 'session_meta',
             'payload': {'id': self.thread, 'cwd': str(self.source)}},
            {'timestamp': '2026-10-11T18:01:00Z', 'type': 'response_item',
             'payload': {'role': 'assistant', 'content': self.raw}}]
        (self.source / 'model-01.prompt.txt').write_text(self.prompt)
        (self.source / 'model-01.answer.json').write_text(self.raw)
        (self.source / 'model-01.events.jsonl').write_text(json.dumps({'type': 'thread.started', 'thread_id': self.thread}) + '\n')
        (self.source / 'model-01.stderr.txt').write_text('')
        self.session = self.source / 'model-01.session.jsonl'
        self.session.write_text(''.join(json.dumps(row) + '\n' for row in self.original_records))
        self.source_events = [
            {'at': '2026-10-11T18:00:00Z', 'event': 'build_start', 'inputs': self.inputs,
             'builder_files': {'builder/build.py': 'b' * 64}},
            {'at': '2026-10-11T18:00:01Z', 'event': 'model_call_start', 'call_id': 'model-01', 'purpose': 'Compile'},
            {'at': '2026-10-11T18:01:01Z', 'event': 'model_session_captured', 'call_id': 'model-01',
             'thread_id': self.thread, 'file': self.session.name, 'complete': True, 'records': 2,
             'sha256': self.digest(self.session)},
            {'at': '2026-10-11T18:01:02Z', 'event': 'model_call_end', 'call_id': 'model-01', 'error': False}]
        aggregate = self.source / 'full-session.jsonl'
        for row in self.source_events[:2]: append_record(aggregate, row)
        for sequence, row in enumerate(self.original_records, 1):
            append_record(aggregate, {'at': row['timestamp'], 'event': 'codex_session_record',
                          'call_id': 'model-01', 'thread_id': self.thread, 'sequence': sequence, 'record': row})
        for row in self.source_events[2:]: append_record(aggregate, row)
        self.refresh_manifest()
        self.events = []
        self.trace('build_start', inputs=self.inputs, builder_files={'builder/build.py': 'c' * 64})

    def tearDown(self): self.tmp.cleanup()

    def digest(self, path): return hashlib.sha256(path.read_bytes()).hexdigest()

    def refresh_manifest(self):
        manifest = {p.relative_to(self.source).as_posix(): self.digest(p)
                    for p in self.source.rglob('*') if p.is_file() and p != self.source / 'trace.jsonl'}
        ending = {'at': '2026-10-11T18:01:03Z', 'event': 'build_end', 'completed': False, 'artifacts': manifest}
        (self.source / 'trace.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in [*self.source_events, ending]))

    def trace(self, event, **values):
        row = {'at': '2026-10-11T18:02:%02dZ' % len(self.events), 'event': event, **values}
        self.events.append(row)
        append_record(self.destination / 'trace.jsonl', row)
        if event != 'build_end': append_record(self.destination / 'full-session.jsonl', row)

    def resume(self, **values):
        return import_failed_compile(self.source, self.destination, values.get('prompt', self.prompt),
                                     values.get('inputs', self.inputs), self.trace)

    def test_import_preserves_exact_evidence_provenance_and_complete_session(self):
        before = {p.name: p.read_bytes() for p in self.source.glob('*') if p.is_file()}
        self.assertEqual(self.resume(), self.raw)
        for suffix in ('.prompt.txt', '.answer.json', '.events.jsonl', '.stderr.txt', '.session.jsonl'):
            name = 'model-01' + suffix
            self.assertEqual((self.destination / name).read_bytes(), before[name])
        imported = next(row for row in self.events if row['event'] == 'compilation_imported')
        self.assertEqual(imported['source_trace_sha256'], self.digest(self.source / 'trace.jsonl'))
        self.assertEqual(imported['raw_answer_sha256'], self.digest(self.source / 'model-01.answer.json'))
        self.assertEqual(imported['original_input_hashes'], self.inputs)
        self.assertEqual(imported['original_builder_files'], self.source_events[0]['builder_files'])
        for row in self.events:
            if row['event'] in ('model_call_start', 'model_session_captured', 'model_call_end'):
                self.assertTrue(row['imported']); self.assertEqual(row['source'], str(self.source))
                self.assertTrue(row['original_at'].startswith('2026-10-11T18:0'))
        result = {'session_trace': 'traces/resumed/full-session.jsonl'}
        self.trace('run_completed', completed=True, result=result)
        self.trace('build_end', completed=True, result=result)
        self.assertEqual(validate_full_session(self.destination, self.events, result), self.destination / 'full-session.jsonl')
        self.assertEqual({p.name: p.read_bytes() for p in self.source.glob('*') if p.is_file()}, before)

    def test_changed_input_path_or_hash_is_rejected(self):
        for inputs in ([{'path': 'different.json', 'sha256': 'a' * 64}],
                       [{'path': self.inputs[0]['path'], 'sha256': 'd' * 64}]):
            with self.subTest(inputs=inputs), self.assertRaisesRegex(ValueError, 'input paths or hashes differ'):
                self.resume(inputs=inputs)
        self.assertFalse((self.destination / 'model-01.answer.json').exists())

    def test_changed_current_prompt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'compiler prompt differs'):
            self.resume(prompt=self.prompt + 'Changed instruction.')

    def test_changed_or_missing_artifact_is_rejected(self):
        path = self.source / 'model-01.answer.json'; original = path.read_bytes()
        path.write_bytes(original + b' edited')
        with self.assertRaisesRegex(ValueError, 'artifact hashes changed'): self.resume()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'artifact hashes changed'): self.resume()

    def test_session_hash_change_rejected_even_with_refreshed_artifact_manifest(self):
        self.session.write_text(self.session.read_text() + json.dumps({'type': 'unexpected'}) + '\n')
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'session capture disagrees'): self.resume()

    def test_aggregate_session_record_change_rejected_even_with_refreshed_manifest(self):
        aggregate = self.source / 'full-session.jsonl'
        rows = list(records(aggregate)); next(row for row in rows if row.get('event') == 'codex_session_record')['sequence'] = 99
        aggregate.write_text(''.join(json.dumps(row) + '\n' for row in rows)); self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'lost or changed compiler session records'): self.resume()

    def test_valid_json_answer_cannot_reuse_syntax_recovery(self):
        (self.source / 'model-01.answer.json').write_text('{"policy": "already valid"}')
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'only for malformed JSON'): self.resume()

    def test_existing_destination_evidence_is_not_overwritten(self):
        target = self.destination / 'model-01.prompt.txt'; target.write_text('Existing evidence')
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'): self.resume()
        self.assertEqual(target.read_text(), 'Existing evidence')
