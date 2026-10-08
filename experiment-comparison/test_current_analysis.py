"""Checks for current-corpus measurements and modern streaming provenance."""
import json
import csv
from pathlib import Path
from statistics import mean
import tempfile
import unittest
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
from analyze_current import extract,launch,text_output,command_text,extra_states

OUT=Path(__file__).resolve().parent.parent/'analysis-output'/'batch-2026-10-07'

class ProgressChartTests(unittest.TestCase):
    def test_exploration_completion_namespaced_exec_with_multiple_receipts(self):
        from analyze_current import exploration_completion
        from extract import stamp
        start=stamp('2026-10-07T10:00:00Z')
        code='text(await tools.mcp__agta__agta_explore({action:"RecordSteps"})); text(await tools.mcp__agta__agta_explore({action:"Complete",runRoot:"C:/run"}));'
        events=[(1,{'type':'response_item','timestamp':'2026-10-07T10:00:40Z',
                    'payload':{'type':'custom_tool_call','name':'exec','input':code,'call_id':'complete'}}),
                (2,{'type':'response_item','timestamp':'2026-10-07T10:01:00Z',
                    'payload':{'type':'custom_tool_call_output','call_id':'complete','output':json.dumps({'content':[{'type':'text','text':json.dumps({'ok':True,'workflow':{'explorationComplete':False}})},{'type':'text','text':json.dumps({'ok':True,'workflow':{'explorationComplete':True}})}]})}})]
        self.assertIsNone(exploration_completion(events,start,1))
        receipt=exploration_completion(events,start,2)
        self.assertEqual(receipt['minutes'],1)
        self.assertEqual((receipt['call_line'],receipt['line']),(1,2))

    def test_combined_office_means_do_not_weight_repeated_apps_more(self):
        from report_current import pooled_model_rows
        runs=[]
        for app,values in [('Excel',[10,10,10]),('PowerPoint',[40]),('Word',[70])]:
            for value in values:
                runs.append({'id':str(len(runs)),'included':True,'bucket':'native','setup':'native',
                             'model':'gpt-5.5','app':app,'minutes':value,'success':len(runs)!=0})
        for app in ['Excel','PowerPoint']:
            runs.append({'id':str(len(runs)),'included':True,'bucket':'mcp','setup':'mcp',
                         'model':'gpt-5.5','app':app,'minutes':20,'success':True})
        rows=pooled_model_rows({'runs':runs})
        native=next(c for c in rows if c['model']=='gpt-5.5' and c['setup']=='native')
        mcp=next(c for c in rows if c['model']=='gpt-5.5' and c['setup']=='mcp')
        self.assertEqual(native['mean_minutes'],40)
        self.assertEqual(native['task_weighted_mean_minutes'],28)
        self.assertEqual((native['n'],native['successes']),(5,4))
        self.assertIsNone(mcp['mean_minutes'])

    def test_exploration_completion_requires_success_and_primary_task(self):
        from analyze_current import exploration_completion
        from extract import stamp
        records=[]
        def pair(sec,tool,args,ok,complete):
            call_id=str(sec)
            timestamp=f'2026-10-07T10:{sec//60:02d}:{sec%60:02d}Z'
            records.append((len(records)+1,{'type':'response_item','timestamp':timestamp,
                           'payload':{'type':'function_call','name':tool,'arguments':json.dumps(args),'call_id':call_id}}))
            receipt={'ok':ok,'workflow':{'explorationComplete':complete}}
            records.append((len(records)+1,{'type':'response_item','timestamp':timestamp,
                           'payload':{'type':'function_call_output','call_id':call_id,
                                      'output':json.dumps([{'type':'text','text':json.dumps(receipt)}])}}))
        pair(10,'agta_help',{'action':'Complete'},True,True)
        pair(20,'agta_explore',{'action':'Complete'},False,False)
        pair(60,'agta_explore',{'action':'Complete'},True,True)
        pair(90,'agta_explore',{'action':'Complete'},True,True)
        start=stamp('2026-10-07T10:00:00Z')
        self.assertIsNone(exploration_completion(records,start,4))
        receipt=exploration_completion(records,start,8)
        self.assertEqual(receipt['minutes'],1)
        self.assertEqual((receipt['call_line'],receipt['line']),(5,6))

    def test_exact_receipts_fixed_denominator_and_held_failed_prefix(self):
        from report_current import progress_points
        sample=[{'setup':'native','minutes':5,'first_pass':{'1':{'minutes':2},'2':{'minutes':4}}},
                {'setup':'native','minutes':10,'first_pass':{str(i):{'minutes':6} for i in range(1,6)}}]
        times,means,horizon=progress_points(sample,['native'])
        self.assertEqual(times,[0,2,4,6,10]);self.assertEqual(horizon,10)
        self.assertEqual(means['native'].tolist(),[0,.5,1,3.5,3.5])

class ModernLogTests(unittest.TestCase):
    def test_nested_stdout_envelope_and_images(self):
        value=[{'type':'input_text','text':json.dumps({'output':'S1: Passed - Open Excel\nS2: Failed','session_id':123})},{'type':'input_image','image_url':'ignored'}]
        self.assertEqual(text_output(value).strip(),'S1: Passed - Open Excel\nS2: Failed')

    def test_ansi_prefix_does_not_hide_json_execution(self):
        value='\x1b[?25l\x1b[2J\x1b[m\x1b[H'+json.dumps({'executionId':'abc','ok':True,'summary':{'total':5,'passed':5,'failed':0}})
        from extract import json_values
        self.assertEqual(next(json_values(text_output(value)))['executionId'],'abc')

    def test_quoted_javascript_command_key(self):
        s='text(await tools.exec_command({"cmd":"powershell.exe -File C:/x/GuiTest.ps1"}));'
        self.assertEqual(command_text(s),'powershell.exe -File C:/x/GuiTest.ps1')

    def test_creation_then_launch_is_not_source_only(self):
        names={'guitest.ps1'}
        self.assertTrue(launch("Set-Content C:/x/GuiTest.ps1 -Value $source; powershell.exe -File C:/x/GuiTest.ps1",names))
        self.assertFalse(launch("Set-Content C:/x/GuiTest.ps1 -Value 'powershell.exe -File C:/x/GuiTest.ps1'",names))
        self.assertFalse(launch('const patch="-File C:/x/GuiTest.ps1"; await tools.apply_patch(patch)',names))

    def test_generic_custom_step_ids_and_diagnostic_exclusion(self):
        actions=['Open','Create','Save','Reopen','Print']
        self.assertEqual(extra_states(json.dumps({'steps':[{'id':'S1','status':'pass'},{'id':'S2','status':'fail'}]}),actions),{1:'PASS',2:'FAIL'})
        self.assertEqual(extra_states(json.dumps({'runKind':'Diagnostic','qualifying':False,'steps':[{'stepIndex':1,'status':'PASS'}]}),actions),{})

    def test_polled_script_result_and_followup_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'newcodex'/'6.1-sol-light'/'excel-1m';folder.mkdir(parents=True)
            rows=[{'Action':a,'Data':'','Expected Result':'x'} for a in ['Open Excel','Create Test Workbook','Save Test Workbook','Open Created Workbook','Print Test Workbook']]
            result={'executionId':'exec1','runKind':'Replay','qualifying':True,'ok':True,'summary':{'total':5,'passed':5,'failed':0},'steps':[{'stepIndex':i,'status':'PASS'} for i in range(1,6)]}
            events=[]
            def add(sec,type,payload):events.append({'timestamp':f'2026-10-07T10:{sec//60:02d}:{sec%60:02d}Z','type':type,'payload':payload})
            add(0,'event_msg',{'type':'task_started','turn_id':'task1'})
            add(1,'turn_context',{'model':'gpt-6.1-sol','effort':'low'})
            add(2,'response_item',{'type':'custom_tool_call','name':'exec','call_id':'help','input':'text(await tools.agta_help({topic:"authoring"}));'})
            add(3,'response_item',{'type':'custom_tool_call_output','call_id':'help','output':[{'type':'input_text','text':json.dumps({'steps':rows})}]})
            add(4,'response_item',{'type':'custom_tool_call','name':'exec','call_id':'launch','input':'text(await tools.exec_command({cmd:"powershell.exe -File C:/x/GuiTest.ps1"}));'})
            add(5,'response_item',{'type':'custom_tool_call_output','call_id':'launch','output':[{'type':'input_text','text':json.dumps({'session_id':123,'output':''})}]})
            add(50,'response_item',{'type':'custom_tool_call','name':'exec','call_id':'poll','input':'text(await tools.write_stdin({session_id:123}));'})
            add(55,'response_item',{'type':'custom_tool_call_output','call_id':'poll','output':[{'type':'input_text','text':json.dumps({'output':json.dumps(result)})}]})
            add(60,'event_msg',{'type':'task_complete','turn_id':'task1'})
            add(120,'event_msg',{'type':'task_started','turn_id':'followup'})
            add(180,'event_msg',{'type':'task_complete','turn_id':'followup'})
            (folder/'GuiTest.ps1').write_text('# Diagnostic only - never executed',encoding='utf-8')
            path=folder/'rollout.jsonl';path.write_text('\n'.join(json.dumps(e) for e in events),encoding='utf-8')
            r=extract(path,root)
            self.assertTrue(r['success']);self.assertAlmostEqual(r['minutes'],1);self.assertEqual(len(r['executions']),1);self.assertEqual(r['script_launches'],1)

class CurrentCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((OUT/'data'/'metrics.json').read_text(encoding='utf-8'));cls.all=cls.data['runs'];cls.runs=[r for r in cls.all if r['included']]

    def test_scope_and_inventory(self):
        self.assertEqual(len(self.all),112);self.assertEqual(len(self.runs),110)
        self.assertEqual(Counter(r['bucket'] for r in self.runs),{'native':35,'mcp':39,'aionly':9,'newcodex':27})
        self.assertFalse(any('old' in Path(r['file']).parts or Path(r['file']).parts[0]=='cli' for r in self.all))
        self.assertEqual(sum(not i['log_count'] for i in self.data['inventory']),6)
        self.assertEqual(len({r['sha256'] for r in self.all}),112);self.assertEqual(len({r['task_id'] for r in self.all}),112)

    def test_partial_failures_and_metadata_corrections(self):
        newer=[r for r in self.runs if r['bucket']=='newcodex']
        self.assertEqual(sum(not r['success'] for r in newer),7)
        for m,n,passed in [('gpt-5.6-luna',4,0),('gpt-6-luna',6,3),('gpt-6.1-sol',3,3)]:
            s=[r for r in newer if r['model']==m and r['setup']=='native'];self.assertEqual((len(s),sum(r['success'] for r in s)),(n,passed))
        corrected=[r for r in newer if 'Folder model differs from recorded model' in r['flags']]
        self.assertEqual(len(corrected),2);self.assertEqual({r['model'] for r in corrected},{'gpt-6-luna'})
        self.assertEqual(sum(r['best_passed_steps'] is None for r in newer),3)

    def test_metrics_and_success_provenance(self):
        for r in self.all:
            self.assertFalse(r['parse_errors']);self.assertFalse(r['token_reset_lines'])
            self.assertGreater(r['minutes'],0);self.assertEqual(r['total_tokens'],r['input_tokens']+r['output_tokens'])
            self.assertEqual(r['uncached_input_tokens'],r['input_tokens']-r['cached_input_tokens']);self.assertGreaterEqual(r['uncached_input_tokens'],0)
            self.assertEqual(len(r['executions']),len({e['executionId'] for e in r['executions']}))
            if r['success']:
                self.assertIsNotNone(r['first_all_pass_minutes']);self.assertLessEqual(r['first_all_pass_minutes'],r['minutes']);self.assertEqual(r['best_passed_steps'],5)
                self.assertTrue(any(len(o['states'])==5 and set(o['states'].values())=={'PASS'} for o in r['observations']))
                if r['bucket']=='newcodex' and r['setup']=='mcp':
                    self.assertTrue(any(e.get('summary',{}).get('passed')==5 for e in r['executions']))
                if r['final_replay_seconds'] is not None:
                    self.assertEqual(r['executions'][-1].get('summary',{}).get('passed'),5)
            else:self.assertIsNone(r['first_all_pass_minutes'])
        for s in self.data['summary']:
            sample=[r for r in self.runs if (r['bucket'],r['model'],r['setup'])==(s['bucket'],s['model'],s['setup'])]
            self.assertEqual(s['n'],len(sample));self.assertAlmostEqual(s['minutes']['mean'],mean(r['minutes'] for r in sample))
        baseline=[r for r in self.runs if r['bucket'] in ['native','mcp']]
        faster=sum(mean(r['minutes'] for r in baseline if r['app']==app and r['setup']=='mcp')<mean(r['minutes'] for r in baseline if r['app']==app and r['setup']=='native') for app in {r['app'] for r in baseline})
        self.assertIn(f'MCP is faster in {faster} of ten', (OUT/'report.html').read_text(encoding='utf-8'))

    def test_known_acceptance_issues_preserved(self):
        self.assertEqual(len(self.data['route_audits']),4);self.assertEqual(self.data['ai_only_without_known_bypasses']['n'],6)
        for a in self.data['route_audits']:self.assertTrue(Path(a['file']).is_file());self.assertTrue(a['excerpts'])
        paints=[r for r in self.all if r['bucket']=='native' and r['folder'] in ['paint-17m','paint-37m']]
        self.assertEqual(len({r['testcase_sha256'] for r in paints}),2)

    def test_progress_chart_cohorts_and_exports(self):
        from report_current import progress_views,progress_points,progress_sample
        baseline,office=progress_views(self.data)
        self.assertEqual(Counter(r['setup'] for r in baseline['runs']),{'native':35,'mcp':39})
        self.assertEqual(Counter(r['setup'] for r in office['runs']),{'native':16,'mcp':16,'aionly':9})
        self.assertEqual(len(baseline['apps']),10);self.assertEqual(set(office['apps']),{'Excel','PowerPoint','Word'})
        for view in [baseline,office]:
            self.assertTrue(all(r['included'] and r['bucket']!='newcodex' and r['model']=='gpt-5.5' for r in view['runs']))
            for app in [None,*view['apps']]:
                sample=progress_sample(view,app);times,means,horizon=progress_points(sample,view['groups'])
                self.assertGreaterEqual(horizon,max(r['minutes'] for r in sample))
                for values in means.values():
                    self.assertEqual(values[0],0);self.assertEqual(values[-1],5)
                    self.assertTrue(all(b>=a for a,b in zip(values,values[1:])))
        with (OUT/'data'/'progress_curves.csv').open(encoding='utf-8-sig',newline='') as f:
            exports=list(csv.DictReader(f))
        self.assertEqual(len({(r['comparison'],r['application'],r['setup']) for r in exports}),34)
        baseline_counts={(r['setup'],int(r['tasks'])) for r in exports if r['comparison']=='baseline-progress' and r['application']=='all'}
        self.assertEqual(baseline_counts,{('native',35),('mcp',39)})

    def test_office_model_comparison_keeps_baseline_and_missing_cells_distinct(self):
        from report_current import application_model_rows
        cells=application_model_rows(self.data)
        self.assertEqual(len(cells),28)
        self.assertEqual(sum(c['n'] for c in cells if c['model']=='gpt-5.5'),32)
        self.assertEqual(sum(c['n'] for c in cells if c['model']!='gpt-5.5'),27)
        run_ids=[run_id for c in cells for run_id in c['run_ids']]
        self.assertEqual(len(run_ids),len(set(run_ids)))
        self.assertTrue(all(next(r for r in self.all if r['id']==run_id)['bucket']!='aionly' for run_id in run_ids))
        word=next(c for c in cells if c['application']=='Word' and c['model']=='gpt-6-luna' and c['setup']=='mcp')
        self.assertEqual((word['n'],word['successes']),(1,1))
        self.assertAlmostEqual(word['mean_minutes'],10.14505)
        self.assertFalse(any(c['application']!='Excel' and c['model'] in ['gpt-5.6-sol','gpt-6-sol'] for c in cells))
        c=next(c for c in cells if (c['application'],c['model'],c['setup'])==('Excel','gpt-6-luna','native'))
        self.assertEqual((c['n'],c['successes']),(2,1))

    def test_combined_office_chart_matches_application_means_and_requested_models(self):
        from report_current import pooled_model_rows,POOLED_MODELS,OFFICE
        rows=pooled_model_rows(self.data)
        self.assertEqual(POOLED_MODELS,['gpt-5.5','gpt-5.6-luna','gpt-6-luna','gpt-6.1-sol'])
        self.assertEqual(len(rows),8)
        for cell in rows:
            self.assertEqual(set(cell['applications']),set(OFFICE))
            sample=[r for r in self.runs if r['id'] in cell['run_ids']]
            self.assertEqual(cell['n'],len(sample))
            self.assertTrue(all(r['bucket']!='aionly' for r in sample))
            expected=mean(mean(r['minutes'] for r in sample if r['app']==app) for app in OFFICE)
            self.assertAlmostEqual(cell['mean_minutes'],expected)
        self.assertEqual(sum(c['successes'] for c in rows if c['model']=='gpt-5.6-luna' and c['setup']=='native'),0)
        self.assertAlmostEqual(next(c['mean_minutes'] for c in rows if c['model']=='gpt-6-luna' and c['setup']=='mcp'),16.060105555555555)
        with (OUT/'data/pooled_model_comparison.csv').open(encoding='utf-8-sig',newline='') as f:
            exported=list(csv.DictReader(f))
        self.assertEqual(len(exported),8)
        self.assertTrue((OUT/'figures/office-pooled-primary-models.svg').is_file())

    def test_local_report_links(self):
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.links=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'id' in a:self.ids.append(a['id'])
                for k in ['href','src']:
                    if k in a:self.links.append(a[k])
        pages={}
        for p in OUT.glob('*.html'):
            x=Links();x.feed(p.read_text(encoding='utf-8'));pages[p.name]=x;self.assertEqual(len(x.ids),len(set(x.ids)))
        for name,x in pages.items():
            for link in x.links:
                u=urlsplit(link)
                if u.scheme=='file':
                    path=unquote(u.path).lstrip('/');self.assertTrue(Path(path).exists(),link);continue
                if u.scheme:continue
                path=OUT/unquote(u.path) if u.path else OUT/name
                self.assertTrue(path.is_file(),link)
                if u.fragment and path.name in pages:self.assertIn(u.fragment,pages[path.name].ids,link)

from collections import Counter
if __name__=='__main__':unittest.main()
