"""Checks for measurement, scope, and evidence errors in the refreshed batch."""
import json
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean
import unittest
from urllib.parse import unquote, urlsplit

from extract import testcase_from_outputs, execution_headers

OUT = Path(__file__).resolve().parent.parent/'analysis-output'/'batch-2026-10-04'


class TestcaseCaptureTests(unittest.TestCase):
    def test_successful_state_does_not_mask_failed_truncated_replay(self):
        text = '{"ok":true,"command":"state","interactionPolicy":{"mode":"GuiNavigation"}}\n'
        text += '{"ok":false,"summary":{"total":5,"passed":4,"failed":1},"interactionPolicy":{"compliant":true},"executionId":"replay-1","steps":[... truncated'
        records = list(execution_headers(text))
        self.assertEqual(len(records), 1)
        self.assertIs(records[0]['ok'], False)
        self.assertEqual(records[0]['interactionPolicy'], {'compliant': True})

    def test_mcp_only_authoring_read_preserves_all_csv_fields(self):
        rows = [{'Action': f'Action {i}', 'Data': 'literal "text", and commas',
                 'Expected Result': f'Expected {i}'} for i in range(5)]
        output = {'guide': 'source instructions are not executed', 'steps': rows}
        text = json.dumps([{'type': 'text', 'text': json.dumps(output)}])
        case = testcase_from_outputs([{'command': '', 'tool': 'agta_help', 'text': text, 'line': 16}])
        self.assertEqual(case['rows'], rows)
        self.assertEqual(case['line'], 16)

    def test_malformed_trailing_field_recovery_is_explicit(self):
        lines = ['Action,Data,Expected Result,',
                 'Open,launch,Image visible, dimensions recorded.',
                 'Edit,"rotate, keep canvas",Rotated,',
                 'Save,save path,Exists,', 'Reopen,open path,Visible,',
                 'Print,print PDF,PDF exists,']
        case = testcase_from_outputs([{'command': 'Get-Content testcase.csv', 'tool': 'shell_command',
                                      'text': '\n'.join(lines), 'line': 13}])
        self.assertEqual(case['rows'][0]['Expected Result'], 'Image visible, dimensions recorded.')
        self.assertEqual(case['rows'][1]['Data'], 'rotate, keep canvas')
        self.assertIn('normalization_note', case)


class BatchReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((OUT/'data'/'metrics.json').read_text(encoding='utf-8'))
        cls.runs = cls.data['runs']

    def test_scope_replacement_and_new_runs(self):
        self.assertEqual(len(self.runs), 70)
        self.assertEqual({g: sum(r['group']==g for r in self.runs) for g in ['native','mcp']}, {'native':35,'mcp':35})
        self.assertFalse(any(r['folder']=='paint-37m' for r in self.runs))
        self.assertTrue(any(r['folder']=='paint-17m' and r['group']=='native' for r in self.runs))
        self.assertTrue({'notepad-11m-2','paint-11m','word-9m-4'} <= {r['folder'] for r in self.runs if r['group']=='mcp'})
        self.assertTrue(all('old' not in Path(r['file']).parts for r in self.runs))
        self.assertEqual(sum(i['status']=='no session log' for i in self.data['inventory']),4)

    def test_paint_now_matches_but_other_variants_are_retained(self):
        paints=[r for r in self.runs if r['app']=='Paint']
        self.assertEqual(len(paints),3)
        self.assertEqual(len({r['testcase']['sha256'] for r in paints}),1)
        self.assertEqual({v['app'] for v in self.data['testcase_variants']}, {'Word','PowerPoint','Photos'})
        exact=next(s for s in self.data['sensitivity'] if s['label'].startswith('Identical'))
        self.assertEqual((exact['native_n'],exact['mcp_n']),(27,35))

    def test_counter_arithmetic_and_pass_provenance(self):
        self.assertEqual(len({r['sha256'] for r in self.runs}),70)
        for r in self.runs:
            self.assertEqual(r['parse_errors'],[])
            self.assertEqual(r['token_reset_lines'],[])
            self.assertEqual(r['total_tokens'],r['input_tokens']+r['output_tokens'])
            self.assertEqual(r['uncached_input_tokens'],r['input_tokens']-r['cached_input_tokens'])
            self.assertGreaterEqual(r['uncached_input_tokens'],0)
            self.assertEqual(r['models'],['gpt-5.5'])
            self.assertEqual(len(r['first_pass']),5)
            self.assertLessEqual(r['first_all_pass_minutes'],r['minutes'])
            self.assertTrue(r['last_all_pass_line'])
        failed=next(r for r in self.runs if r['folder_failed_label'])
        self.assertTrue(any('Writing a simple PDF' in h['text'] for h in failed['review_hits']))

    def test_summaries_match_included_logs(self):
        for g in ['native','mcp']:
            sample=[r for r in self.runs if r['group']==g]
            self.assertAlmostEqual(self.data['summary'][g]['minutes']['mean'],mean(r['minutes'] for r in sample))
            self.assertEqual(self.data['summary'][g]['token_sums']['total_tokens'],sum(r['total_tokens'] for r in sample))

    def test_reused_export_metadata_does_not_duplicate_a_task(self):
        self.assertEqual(len(self.data['reused_session_ids']),1)
        ids=next(iter(self.data['reused_session_ids'].values()))
        reused=[r for r in self.runs if r['id'] in ids]
        self.assertEqual(len(reused),4)
        self.assertEqual(len({r['task_ids'][0] for r in reused}),4)
        reused.sort(key=lambda r:r['start'])
        self.assertTrue(all(a['end']<b['start'] for a,b in zip(reused,reused[1:])))

    def test_replays_are_deduplicated(self):
        for r in self.runs:
            self.assertEqual(len(r['executions']),len({e['executionId'] for e in r['executions']}))
        m=[r for r in self.runs if r['group']=='mcp']
        self.assertEqual(sum(len(r['executions']) for r in m),130)
        self.assertEqual(sum(r['replay_successes'] for r in m),35)
        self.assertEqual(sum(r['replay_failures'] for r in m),95)

    def test_html_and_source_links_resolve(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__();self.links=[];self.ids=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'id' in a:self.ids.append(a['id'])
                self.links.extend(a[name] for name in ['href','src'] if name in a)
        pages={}
        for path in OUT.glob('session_*.html'):
            p=Links();p.feed(path.read_text(encoding='utf-8'));pages[path.name]=p
            self.assertEqual(len(p.ids),len(set(p.ids)))
        for name,p in pages.items():
            for link in p.links:
                u=urlsplit(link)
                if u.scheme=='file':
                    self.assertTrue(Path(unquote(u.path).lstrip('/')).exists(),link)
                    continue
                if u.scheme:continue
                target=OUT/unquote(u.path or name)
                self.assertTrue(target.exists(),link)
                if u.fragment and target.name in pages:
                    self.assertIn(u.fragment,pages[target.name].ids)


if __name__=='__main__':
    unittest.main()
