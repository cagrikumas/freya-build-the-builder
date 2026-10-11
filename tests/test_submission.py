import hashlib
import io
from contextlib import redirect_stdout
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
                   'folder_mode': True, 'mock_url': 'https://mock.example',
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
        self.head = 'a' * 40
        self.tags = {}
        self.git_calls = []
        def git_blob(command, **kwargs):
            self.git_calls.append(command)
            if command[:3] == ['git', 'cat-file', 'blob']:
                commit, relative = command[-1].split(':', 1)
                if commit not in ('HEAD', self.head) or relative not in self.committed:
                    raise subprocess.CalledProcessError(128, command)
                return self.committed[relative]
            if command[:3] == ['git', 'rev-parse', '--verify']:
                reference = command[-1].removesuffix('^{commit}')
                if reference in ('HEAD', self.head): value = self.head
                elif reference.startswith('refs/tags/') and reference[10:] in self.tags:
                    value = self.tags[reference[10:]]
                    if value is None: raise subprocess.CalledProcessError(128, command)
                else: raise subprocess.CalledProcessError(128, command)
                return value + '\n' if kwargs.get('text') else (value + '\n').encode()
            if command[:2] == ['git', 'check-ref-format']:
                if command[-1].endswith('.lock') or '..' in command[-1]:
                    raise subprocess.CalledProcessError(1, command)
                return b''
            if command[:3] == ['git', 'show-ref', '--verify']:
                if command[-1].removeprefix('refs/tags/') not in self.tags:
                    raise subprocess.CalledProcessError(1, command)
                return b''
            if command == ['git', 'status', '--porcelain']: return ''
            raise AssertionError('Unexpected Git command: ' + repr(command))
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

    # Reuse the complete synthetic run without making any Git mutations.
    def manifest(self, reference='final-release'):
        path = self.root / 'submission/submission.json'
        value = {'commit': reference, 'workflow': 'submission/final.workflow.json',
                 'trace': 'traces/final/full-session.jsonl', 'mock_url': 'https://mock.example'}
        path.write_text(json.dumps(value) + '\n')
        self.committed[path.relative_to(self.root).as_posix()] = path.read_bytes()
        return path

    def test_planned_tag_allowed_only_during_generation(self):
        self.assertEqual(package_submission.submission_reference('final-release', allow_planned=True),
                         ('final-release', None))
        with self.assertRaisesRegex(ValueError, 'does not exist yet'):
            package_submission.submission_reference('final-release')

    def test_existing_tag_and_full_sha_must_resolve_to_current_head(self):
        self.tags['final-release'] = self.head
        self.assertEqual(package_submission.submission_reference('final-release'), ('final-release', self.head))
        self.assertEqual(package_submission.submission_reference(self.head), (self.head, self.head))
        self.tags['old-release'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'must resolve to current HEAD'):
            package_submission.submission_reference('old-release', allow_planned=True)
        with self.assertRaisesRegex(ValueError, 'does not resolve to a commit'):
            package_submission.submission_reference('c' * 40, allow_planned=True)
        self.tags['blob-tag'] = None
        with self.assertRaisesRegex(ValueError, 'does not resolve to a commit'):
            package_submission.submission_reference('blob-tag', allow_planned=True)

    def test_branch_expressions_unsafe_or_invalid_tag_names_are_rejected(self):
        for value in ('HEAD', 'HEAD~1', 'main^{commit}', 'refs/heads/main', 'refs/tags/final',
                      '-option', 'bad:name', 'two names', 'bad..tag', 'bad.lock', '', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                package_submission.submission_reference(value, allow_planned=True)
        package_submission.submission_reference('release/nested-name', allow_planned=True)
        self.assertIn(['git', 'show-ref', '--verify', '--quiet', 'refs/tags/release/nested-name'], self.git_calls)

    def test_verify_requires_manifest_and_all_run_files_identical_at_tag(self):
        path = self.manifest()
        self.tags['final-release'] = self.head
        result = package_submission.verify_submission(path)
        self.assertEqual(result['commit'], self.head)
        self.assertEqual(result['files'], ['submission/submission.json', 'submission/final.workflow.json',
                                         'traces/final/full-session.jsonl'])
        for relative in result['files']:
            self.assertIn(['git', 'cat-file', 'blob', self.head + ':' + relative], self.git_calls)
        for relative in package_submission.source_hashes():
            self.assertIn(['git', 'cat-file', 'blob', self.head + ':' + relative], self.git_calls)

    def test_verifier_rejects_manifest_not_in_named_commit(self):
        path = self.manifest(); self.tags['final-release'] = self.head
        del self.committed['submission/submission.json']
        with self.assertRaisesRegex(ValueError, 'missing from ' + self.head):
            package_submission.verify_submission(path)

    def test_verifier_rejects_changed_manifest_and_source_bytes(self):
        path = self.manifest(); self.tags['final-release'] = self.head
        original = path.read_text(); path.write_text(original + ' ')
        with self.assertRaisesRegex(ValueError, 'differs from ' + self.head):
            package_submission.verify_submission(path)
        path.write_text(original)
        self.committed['builder/build.py'] = b'different committed source'
        with self.assertRaisesRegex(ValueError, 'differs from ' + self.head + ': builder/build.py'):
            package_submission.verify_submission(path)

    def test_generation_uses_planned_tag_without_claiming_prior_sha(self):
        args = ['package_submission.py', '--team', 'example', '--repo', 'https://github.com/example/repo',
                '--final', str(self.run), '--mock-url', 'https://mock.example', '--name', 'Example',
                '--email', 'example@example.com', '--commit-ref', 'planned-release']
        output = io.StringIO()
        with patch.object(sys, 'argv', args), redirect_stdout(output): package_submission.main()
        self.assertEqual(json.loads(output.getvalue())['commit'], 'planned-release')
        self.assertNotIn('planned-release', self.tags)

    def test_verify_cli_needs_no_generation_arguments(self):
        path = self.manifest(); self.tags['final-release'] = self.head
        output = io.StringIO()
        with patch.object(sys, 'argv', ['package_submission.py', '--verify', str(path)]), redirect_stdout(output):
            package_submission.main()
        self.assertEqual(json.loads(output.getvalue())['commit'], self.head)
