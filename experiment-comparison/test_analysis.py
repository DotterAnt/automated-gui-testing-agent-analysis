"""Checks for measurement errors that would change the report's conclusions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from extract import read_records, observed_steps, parse_steps, is_launch, extract_all, summarize
from figures import progress_curve

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'analysis-output'
ACTIONS=['Open Excel','Create Test Workbook','Save Test Workbook','Open Created Workbook','Print Test Workbook']


class ExtractionTests(unittest.TestCase):
    def test_unicode_binary_data_is_not_a_record_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'sample.jsonl'
            p.write_text(json.dumps({'output':'binary\u0085more\u2028text'},ensure_ascii=False)+'\n'+json.dumps({'output':'second'})+'\n',encoding='utf-8')
            rows,errors=read_records(p)
            self.assertEqual(len(rows),2);self.assertEqual(errors,[])
            self.assertIn('\u0085',rows[0][1]['output'])

    def test_truncated_detail_preserves_complete_summary(self):
        text='{"ok":true,"summary":{"total":5,"passed":5,"failed":0},"steps":[{"stepIndex":1,"action":"Open Excel","status":"PASS"},... truncated'
        self.assertEqual(observed_steps(text,ACTIONS),dict.fromkeys(range(1,6),'PASS'))

    def test_incomplete_summary_does_not_invent_step_identity(self):
        self.assertEqual(observed_steps('{"summary":{"total":5,"passed":4,"failed":1},"steps":[... truncated',ACTIONS),{})

    def test_timestamped_console_rows_are_recognized(self):
        text='[13:37:35] Open Excel - Passed - ready\n[13:37:45] Create Test Workbook - Failed - missing text'
        self.assertEqual(observed_steps(text,ACTIONS),{1:'PASS',2:'FAIL'})

    def test_bool_and_named_native_results(self):
        self.assertEqual(parse_steps({'results':{'Open Excel':{'status':'Passed'}}},ACTIONS),{1:'PASS'})
        self.assertEqual(parse_steps({'results':[{'action':'Open Excel','passed':True}]},ACTIONS),{1:'PASS'})

    def test_progress_is_cumulative_and_finished_runs_stay_in_mean(self):
        run={'first_pass':{'1':{'minutes':2},'2':{'minutes':4}}}
        self.assertEqual(progress_curve(run,[0,2,3,4,50]).tolist(),[0,1,1,2,2])

    def test_launch_not_validator_or_source_read(self):
        names={'mytest.ps1'}
        self.assertTrue(is_launch("powershell -File 'C:\\x\\MyTest.ps1' -RunRoot x",names))
        self.assertTrue(is_launch("& '.\\MyTest.ps1'",names))
        self.assertFalse(is_launch("Get-Content 'C:\\x\\MyTest.ps1'",names))
        self.assertFalse(is_launch("powershell -File Test-GeneratedScript.ps1 -Path MyTest.ps1",names))

    def test_old_directory_never_enters_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in ['native/a','cli/b','old/native/a']:
                (p/name).mkdir(parents=True);(p/name/'session.jsonl').write_text('{}')
            def fake(path,root):
                return {'group':path.relative_to(root).parts[0],'app':'Word','app_key':'word','start':'x','folder':str(path),'sha256':str(path)}
            with patch('extract.extract_run',side_effect=fake):
                data=extract_all(p)
            self.assertEqual(len(data['runs']),2)
            self.assertEqual({r['group'] for r in data['runs']},{'native','cli'})


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((OUT/'experiment-data/metrics.json').read_text(encoding='utf-8'))
        cls.runs=cls.data['runs']

    def test_all_sources_unique_complete_and_current(self):
        self.assertEqual(len(self.runs),49)
        self.assertEqual(sum(r['group']=='native' for r in self.runs),24)
        self.assertEqual(len({r['sha256'] for r in self.runs}),49)
        self.assertEqual(len({r['app'] for r in self.runs}),10)
        for r in self.runs:
            self.assertNotIn('old',Path(r['file']).parts)
            self.assertFalse(r['parse_errors']);self.assertFalse(r['token_reset_lines'])
            self.assertEqual(r['models'],['gpt-5.5'])
            self.assertEqual(len(r['first_pass']),5)
            self.assertLessEqual(r['first_all_pass_minutes'],r['minutes'])
            self.assertEqual(r['input_tokens']+r['output_tokens'],r['total_tokens'])
            self.assertGreaterEqual(r['uncached_input_tokens'],0)

    def test_late_settings_event_cannot_inflate_duration(self):
        r=next(r for r in self.runs if r['id']=='N-SNIPPINGTOOL-02')
        self.assertAlmostEqual(r['minutes'],47.5349666667,places=6)
        self.assertGreater(r['raw_log_span_minutes'],340)

    def test_failure_is_retained_and_exact_case_subset_is_explicit(self):
        self.assertTrue(next(r for r in self.runs if r['id']=='N-NOTEPAD-01')['folder_failed_label'])
        exact=next(s for s in self.data['sensitivity'] if s['label'].startswith('Exact'))
        self.assertEqual((exact['native_n'],exact['cli_n']),(18,25))

    def test_summary_direction(self):
        s=summarize(self.runs)
        self.assertLess(s['cli']['minutes']['mean'],s['native']['minutes']['mean'])
        self.assertGreater(s['cli']['total_tokens']['mean'],s['native']['total_tokens']['mean'])
        self.assertGreater(s['cli']['uncached_input_tokens']['mean'],s['native']['uncached_input_tokens']['mean'])
        self.assertAlmostEqual(s['native']['minutes']['mean'],37.9278118056,places=6)

    def test_framework_summary_coverage(self):
        sample=[r for r in self.runs if r['group']=='cli']
        self.assertEqual(sum(r['executions'][-1]['truncated'] for r in sample),6)
        for r in sample:
            self.assertEqual(r['executions'][-1]['summary']['passed'],5)
            self.assertEqual(r['executions'][-1]['interactionPolicy']['mode'],'GuiNavigation')

    def test_html_links_and_assets_resolve(self):
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.links=[];self.ids=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'id' in a:self.ids.append(a['id'])
                for name in ('href','src'):
                    if name in a:self.links.append(a[name])
        pages={}
        for path in OUT.glob('experiment_*.html'):
            parser=Links();parser.feed(path.read_text(encoding='utf-8'));pages[path.name]=parser
            self.assertEqual(len(parser.ids),len(set(parser.ids)))
        for name,parser in pages.items():
            for link in parser.links:
                url=urlsplit(link)
                if url.scheme:continue
                target=OUT/unquote(url.path or name)
                self.assertTrue(target.exists(),link)
                if url.fragment and target.name in pages:self.assertIn(url.fragment,pages[target.name].ids)


if __name__=='__main__':unittest.main()
