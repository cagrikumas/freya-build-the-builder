import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import build


class FolderBuildTests(unittest.TestCase):
    def test_documents_are_compiled_without_case_rules_in_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); case=root/'case';case.mkdir()
            (case/'BRIEF.md').write_text('Speak in the language of these documents. İptal işlemini açıkla.')
            code=root/'builder';code.mkdir()
            for name in ['compile_prompt.md','audit_prompt.md']:
                (code/name).write_text((build.ROOT/'builder'/name).read_text())
            kit=root/'kit';(kit/'docs').mkdir(parents=True)
            for name in ['workflow-format.md','tools-and-code.md']:(kit/'docs'/name).write_text('Platform reference.')
            artifact={'policy':{},'workflow':{'initial_node':'start','nodes':{'start':{
                'name':'start','node_type':'conversation','task_message':'Follow the supplied policy.','transitions':[]}}},
                'checks':[],'openapi':{'openapi':'3.0.3','servers':[{'url':'https://original.example'}],
                'paths':{'/cancel':{'post':{'operationId':'cancel'}}}}}
            with patch.object(build,'ROOT',root),patch.object(build,'KIT',kit),patch.object(build,'load_env'),\
                 patch.object(build,'call',side_effect=[artifact,{'approved':True,'issues':[],'patches':[]}]) as model,\
                 patch.object(sys,'argv',['build.py',str(case),'https://personal-mock.example','--offline']):
                build.main()
            first=model.call_args_list[0]
            self.assertIn('İptal işlemini açıkla.',first.args[0])
            self.assertIn('https://personal-mock.example',first.args[0])
            run=next((root/'traces').iterdir())
            schema=json.loads((run/'tool-api.json').read_text())
            self.assertEqual(schema['servers'],[{'url':'https://personal-mock.example'}])
            events=[json.loads(line) for line in (run/'trace.jsonl').read_text().splitlines()]
            self.assertTrue(events[-1]['completed'])
            self.assertTrue(events[0]['folder_mode'])
            self.assertEqual(events[0]['mock_url'],'https://personal-mock.example')
