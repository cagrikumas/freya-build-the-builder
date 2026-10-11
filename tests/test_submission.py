import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import package_submission


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'builder').mkdir()
        (self.root / 'builder/build.py').write_text('source at build time')
        kit = self.root / 'build-the-builder-v3/build-the-builder'
        (kit / 'docs').mkdir(parents=True)
        for relative in ('freya.py', 'docs/workflow-format.md', 'docs/tools-and-code.md'):
            (kit / relative).write_text('unchanged platform source')
        self.run = self.root / 'traces/final'; self.run.mkdir(parents=True)
        (self.run / 'documents.txt').write_text('Supplied document content')
        (self.run / 'model-01.answer.json').write_text('{}')
        (self.root / 'submission').mkdir()
        self.export = self.root / 'submission/final.workflow.json'
        self.export.write_text(json.dumps({'workflow_id': 'w'}))
        result = {'session_trace': 'traces/final/full-session.jsonl', 'workflow_id': 'w', 'trace': 'traces/final/trace.jsonl', 'export': 'submission/final.workflow.json',
                  'sha256': hashlib.sha256(self.export.read_bytes()).hexdigest()}
        self.result = self.run / 'result.json'
        self.result.write_text(json.dumps(result))
        self.patch = patch.object(package_submission, 'ROOT', self.root)
        self.patch.start()
        self.input = self.root / 'BRIEF.md'; self.input.write_text('Original input')
        session_record = {'timestamp': '2026-10-11T17:00:00Z', 'type': 'session_meta',
                          'payload': {'id': 'thread', 'cwd': str(self.run)}}
        session_file = self.run / 'model-01.session.jsonl'
        session_file.write_text(json.dumps(session_record) + '\n')
        events = [{'event': 'build_start', 'builder_files': package_submission.source_hashes(),
                   'inputs': [{'path': 'BRIEF.md', 'sha256': hashlib.sha256(self.input.read_bytes()).hexdigest()}]},
                  {'event': 'model_call_start', 'call_id': 'model-01'},
                  {'event': 'model_session_captured', 'call_id': 'model-01', 'thread_id': 'thread',
                   'file': session_file.name, 'records': 1, 'complete': True,
                   'sha256': hashlib.sha256(session_file.read_bytes()).hexdigest()},
                  {'event': 'run_completed', 'completed': True, 'result': result}]
        full_trace = [events[0], events[1],
                      {'event': 'codex_session_record', 'call_id': 'model-01', 'thread_id': 'thread',
                       'sequence': 1, 'record': session_record}, *events[2:]]
        (self.run / 'full-session.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in full_trace))
        events.append({'event': 'build_end', 'completed': True, 'seconds': 30, 'result': result,
                       'artifacts': {p.relative_to(self.run).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in self.run.rglob('*') if p.is_file()}})
        (self.run / 'trace.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        self.committed = {p.relative_to(self.root).as_posix(): p.read_bytes()
                          for p in self.root.rglob('*') if p.is_file()}
        def git_blob(command, **kwargs):
            relative = command[-1].removeprefix('HEAD:')
            if relative not in self.committed:
                raise subprocess.CalledProcessError(128, command)
            return self.committed[relative]
        self.git_patch = patch.object(package_submission.subprocess, 'check_output', side_effect=git_blob)
        self.git_patch.start()

    def tearDown(self):
        self.patch.stop()
        self.git_patch.stop()
        self.tmp.cleanup()

    def test_unchanged_build_can_be_packaged(self):
        self.assertEqual(package_submission.load_result(self.result)['workflow_id'], 'w')

    def test_hand_changed_export_is_rejected(self):
        self.export.write_text(json.dumps({'workflow_id': 'w', 'manual_edit': True}))
        with self.assertRaisesRegex(ValueError, 'Export changed'):
            package_submission.load_result(self.result)

    def test_source_edit_requires_new_build(self):
        (self.root / 'builder/build.py').write_text('new source after build')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            package_submission.load_result(self.result)

    def test_platform_client_edit_requires_new_build(self):
        (self.root / 'build-the-builder-v3/build-the-builder/freya.py').write_text('different phone model')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            package_submission.load_result(self.result)

    def test_missing_model_artifact_is_rejected(self):
        (self.run / 'model-01.answer.json').unlink()
        with self.assertRaisesRegex(ValueError, 'manifest disagrees.*missing'):
            package_submission.load_result(self.result)

    def test_changed_artifact_is_rejected(self):
        (self.run / 'documents.txt').write_text('edited input extraction')
        with self.assertRaisesRegex(ValueError, 'manifest disagrees.*changed'):
            package_submission.load_result(self.result)

    def test_extra_artifact_is_rejected(self):
        (self.run / 'extra.txt').write_text('unrecorded file')
        with self.assertRaisesRegex(ValueError, 'manifest disagrees.*added'):
            package_submission.load_result(self.result)

    def test_ignored_trace_file_is_rejected_even_when_it_exists(self):
        del self.committed['traces/final/model-01.answer.json']
        with self.assertRaisesRegex(ValueError, 'missing from HEAD'):
            package_submission.load_result(self.result)

    def test_export_must_match_head_bytes(self):
        self.committed['submission/final.workflow.json'] = b'older committed export'
        with self.assertRaisesRegex(ValueError, 'differs from HEAD'):
            package_submission.load_result(self.result)

    def test_original_input_change_is_rejected(self):
        self.input.write_text('edited case input')
        with self.assertRaisesRegex(ValueError, 'input is missing or changed'):
            package_submission.load_result(self.result)

    def test_legacy_run_without_artifact_manifest_is_rejected(self):
        trace = self.run / 'trace.jsonl'
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        del events[-1]['artifacts']
        trace.write_text('\n'.join(map(json.dumps, events)))
        with self.assertRaisesRegex(ValueError, 'lacks its trace artifact manifest'):
            package_submission.load_result(self.result)
