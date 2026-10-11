import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from assemble import assemble
from resume_refine import import_completed_run
from session_trace import append_record, records, validate_full_session


class ResumeRefineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'completed'; self.source.mkdir()
        self.destination = self.root / 'refined'; self.destination.mkdir()
        self.prompt = 'Exact original compiler prompt\n'
        self.inputs = [{'path': 'private/case/source.md', 'sha256': 'a' * 64}]
        self.artifact = {'policy': {'rule': 'source-derived'}, 'workflow': {
            'initial_node': 'finish', 'nodes': {'finish': {'node_type': 'end_call'}}},
            'checks': [{'name': 'original-check'}], 'scenarios': [{'name': 'original-example'}]}
        self.api = {'openapi': '3.0.0', 'servers': [{'url': 'https://mock.example'}], 'paths': {}}
        self.result = {'session_trace': 'traces/completed/full-session.jsonl', 'export': 'submission/final.json'}
        self.thread = '0199a213-81c0-7800-8aa1-bbab2a035a53'
        self.raw_records = [{'type': 'session_meta', 'payload': {'id': self.thread, 'cwd': str(self.source)}},
                            {'type': 'response_item', 'payload': {'role': 'assistant', 'content': 'Full original reasoning record'}}]
        self.write_json('candidate-0.json', self.artifact)
        self.write_json('workflow.json', assemble(self.artifact, self.api))
        self.write_json('tool-api.json', self.api)
        self.write_json('result.json', self.result)
        (self.source / 'model-01.prompt.txt').write_text(self.prompt)
        self.write_json('model-01.answer.json', self.artifact)
        (self.source / 'model-01.events.jsonl').write_text(json.dumps({'type': 'thread.started', 'thread_id': self.thread}) + '\n')
        (self.source / 'model-01.stderr.txt').write_text('')
        self.session = self.source / 'model-01.session.jsonl'
        self.session.write_text(''.join(json.dumps(row) + '\n' for row in self.raw_records))
        self.events = [
            {'at': '2026-10-11T18:00:00Z', 'event': 'build_start', 'inputs': self.inputs, 'builder_files': {'builder/build.py': 'b' * 64}},
            {'at': '2026-10-11T18:00:01Z', 'event': 'model_call_start', 'call_id': 'model-01'},
            {'at': '2026-10-11T18:00:02Z', 'event': 'model_session_captured', 'call_id': 'model-01', 'thread_id': self.thread,
             'file': self.session.name, 'complete': True, 'records': len(self.raw_records), 'sha256': self.digest(self.session)},
            {'at': '2026-10-11T18:00:03Z', 'event': 'model_call_end', 'call_id': 'model-01'},
            {'at': '2026-10-11T18:00:04Z', 'event': 'run_completed', 'completed': True, 'result': self.result}]
        for event in self.events[:2]: append_record(self.source / 'full-session.jsonl', event)
        for sequence, record in enumerate(self.raw_records, 1):
            append_record(self.source / 'full-session.jsonl', {'event': 'codex_session_record', 'call_id': 'model-01',
                          'thread_id': self.thread, 'sequence': sequence, 'record': record})
        for event in self.events[2:]: append_record(self.source / 'full-session.jsonl', event)
        self.refresh_manifest()
        self.imported_events = []
        self.trace('build_start', inputs=self.inputs, builder_files={'builder/build.py': 'c' * 64})

    def tearDown(self): self.tmp.cleanup()

    def digest(self, path): return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_json(self, name, value): (self.source / name).write_text(json.dumps(value))

    def refresh_manifest(self, completed=True):
        manifest = {p.relative_to(self.source).as_posix(): self.digest(p) for p in self.source.rglob('*')
                    if p.is_file() and p != self.source / 'trace.jsonl'}
        end = {'at': '2026-10-11T18:00:05Z', 'event': 'build_end', 'completed': completed, 'artifacts': manifest}
        (self.source / 'trace.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in [*self.events, end]))

    def trace(self, event, **values):
        row = {'at': '2026-10-11T18:10:00Z', 'event': event, **values}
        self.imported_events.append(row)
        append_record(self.destination / 'trace.jsonl', row)
        if event != 'build_end': append_record(self.destination / 'full-session.jsonl', row)

    def run_import(self, **values):
        return import_completed_run(self.source, self.destination, values.get('prompt', self.prompt),
                                    values.get('inputs', self.inputs), self.trace)

    def finish_and_validate(self):
        result = {'session_trace': 'traces/refined/full-session.jsonl'}
        self.trace('run_completed', completed=True, result=result)
        self.trace('build_end', completed=True, result=result)
        self.assertEqual(validate_full_session(self.destination, self.imported_events, result), self.destination / 'full-session.jsonl')

    def test_import_preserves_original_artifact_tests_evidence_and_provenance(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir() if p.is_file()}
        artifact, api = self.run_import()
        self.assertEqual((artifact, api), (self.artifact, self.api))
        self.assertEqual((self.destination / 'resumed-artifact.json').read_bytes(), before['candidate-0.json'])
        for name, data in before.items():
            if name.startswith('model-'): self.assertEqual((self.destination / name).read_bytes(), data)
        provenance = next(row for row in self.imported_events if row['event'] == 'completed_run_imported')
        self.assertEqual(provenance['source_trace_sha256'], self.digest(self.source / 'trace.jsonl'))
        self.assertEqual(provenance['original_builder_files'], self.events[0]['builder_files'])
        self.assertEqual(provenance['source_result'], self.result)
        self.finish_and_validate()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir() if p.is_file()})

    def test_changed_inputs_and_prompt_rejected_before_copying(self):
        for values in [dict(inputs=[{'path': 'different', 'sha256': 'a' * 64}]),
                       dict(inputs=[{'path': self.inputs[0]['path'], 'sha256': 'd' * 64}]),
                       dict(prompt=self.prompt + 'changed')]:
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, 'input paths or hashes differ|compiler prompt changed'):
                self.run_import(**values)
        self.assertFalse((self.destination / 'model-01.prompt.txt').exists())

    def test_artifact_tampering_or_missing_evidence_rejected(self):
        path = self.source / 'candidate-0.json'; path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'artifact hashes changed'): self.run_import()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'artifact hashes changed'): self.run_import()

    def test_session_tampering_rejected_even_with_new_manifest(self):
        self.session.write_text(self.session.read_text() + '{"type":"tampered"}\n')
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'session disagrees'): self.run_import()

    def test_full_session_tampering_rejected_even_with_new_manifest(self):
        path = self.source / 'full-session.jsonl'; rows = list(records(path))
        next(row for row in rows if row.get('event') == 'codex_session_record')['sequence'] = 99
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows)); self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'changed or omitted'): self.run_import()

    def test_export_not_matching_any_candidate_rejected(self):
        self.write_json('workflow.json', {'nodes': {}}); self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'No unambiguous artifact'): self.run_import()

    def test_failed_source_and_existing_evidence_rejected(self):
        self.refresh_manifest(completed=False)
        with self.assertRaisesRegex(ValueError, 'completed exported run'): self.run_import()
        self.refresh_manifest()
        path = self.destination / 'model-01.prompt.txt'; path.write_text('do not overwrite')
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'): self.run_import()
        self.assertEqual(path.read_text(), 'do not overwrite')

    def test_real_completed_run_import_preserves_all_full_sessions(self):
        actual = Path(__file__).resolve().parents[1] / 'traces/20261011T183700Z-final'
        if not (actual / 'result.json').exists(): self.skipTest('Local immutable completed run is unavailable')
        self.source = actual
        start = next(records(actual / 'trace.jsonl'))
        self.inputs = start['inputs']; self.prompt = (actual / 'model-01.prompt.txt').read_text()
        artifact, api = self.run_import()
        self.assertEqual(assemble(artifact, api), json.loads((actual / 'workflow.json').read_text()))
        for path in actual.glob('model-*'):
            if path.is_file(): self.assertEqual((self.destination / path.name).read_bytes(), path.read_bytes())
        captures = [e for e in self.imported_events if e['event'] == 'model_session_captured']
        self.assertGreaterEqual(len(captures), 3)
        self.assertTrue(all(e['imported'] and e['source'] == str(actual) for e in captures))
        self.finish_and_validate()
