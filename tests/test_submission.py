import hashlib
import json
from pathlib import Path
import sys
import tempfile
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
        self.export = self.root / 'workflow.json'
        self.export.write_text(json.dumps({'workflow_id': 'w'}))
        result = {'workflow_id': 'w', 'trace': 'trace.jsonl', 'export': 'workflow.json',
                  'sha256': hashlib.sha256(self.export.read_bytes()).hexdigest()}
        self.result = self.root / 'result.json'
        self.result.write_text(json.dumps(result))
        events = [{'event': 'build_start', 'builder_files': {'builder/build.py': hashlib.sha256((self.root / 'builder/build.py').read_bytes()).hexdigest()}},
                  {'event': 'build_end', 'completed': True, 'seconds': 30, 'result': result}]
        (self.root / 'trace.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        self.patch = patch.object(package_submission, 'ROOT', self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
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
