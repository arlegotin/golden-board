"""Current teaching coverage and absence of recovery-only data/dependencies."""
from pathlib import Path
import json,subprocess,tomllib,unittest
from golden_board.course_generic import build_generic,generic_groups,OPS
from golden_board.course_foundation import build_foundation

ROOT=Path(__file__).resolve().parents[1]

class CleanContentTests(unittest.TestCase):
    def test_recovery_operations_and_queries_absent_but_updates_records_retained(self):
        self.assertEqual(list(OPS),['count','equal','less','row','col','at','roles','updates','record'])
        queries=[q for g in generic_groups() for q in g['queries']]
        self.assertTrue({'updates','records'}<={q['id'] for q in queries})
        self.assertFalse({'bits','agreed','conflicting','unchecked','dependencies','transitive'}&{q['id'] for q in queries})
        p=build_generic()
        from golden_board.document import decode_document
        self.assertFalse(any(r['kind']==5 for r in decode_document(p['document'])['records'].values()))

    def test_current_coverage_exact_and_actual_player(self):
        a,b=build_generic(),build_foundation(ROOT)
        coverage=tomllib.loads((ROOT/'content/coverage.toml').read_text())
        required={s for f in coverage['family'] if f['id'] in ('T0','T1','T2','T3') for s in f['critical_strata']}
        self.assertEqual(len(required),32)
        self.assertEqual(set(a['bindings'])|set(b['bindings']),required)
        self.assertFalse(set(a['bindings'])&set(b['bindings']))
        request={'documents':{'1':a['document'].hex(),'3':b['document'].hex()},'cases':a['cases']+b['cases']}
        run=subprocess.run(['node',str(ROOT/'tools/audit-course.mjs')],input=json.dumps(request),capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        result=json.loads(run.stdout)
        self.assertTrue(result['all_frames_exact'] and result['all_actions_exact'] and result['passive_without_response'])

    def test_new_build_has_no_legacy_recovery_import(self):
        command="import sys;sys.path.insert(0,"+repr(str(ROOT/'src'))+");import golden_board.clean_build;assert not {'golden_board.carrier','golden_board.bootstrap','golden_board.placement','golden_board.bootstrap_fields','golden_board.bootstrap_selective'} & set(sys.modules)"
        run=subprocess.run([str(ROOT/'.venv/bin/python'),'-c',command],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)

class RetainedChessTests(unittest.TestCase):
    def test_pseudo_valid_failed_evasions_keep_prior_closure_distinct(self):
        from tests.test_composed_closure_repair import ComposedClosureRepairTests
        case=ComposedClosureRepairTests('test_active_pseudo_valid_failed_evasions_separate_prior_from_diagnostic')
        case.foundation=build_foundation(ROOT)
        case.test_active_pseudo_valid_failed_evasions_separate_prior_from_diagnostic()

    def test_king_retention_query_is_exact_and_terminal_flags_remain_distinct(self):
        from tests.test_composed_closure_repair import query
        from golden_board.course_foundation import foundation_result
        product=build_foundation(ROOT)
        old=json.loads((ROOT/'tests/fixtures/foundation-groups.json').read_bytes())
        expected=next(q for g in old for q in g['queries'] if q['id']=='king-retention')
        self.assertEqual(query(product,'king-retention'),expected)
        variants=[expected['worked_input'],expected['input'],*expected['worked_variants']]
        flags=[(foundation_result(v)['closed_before'],foundation_result(v)['closed_after']) for v in variants]
        self.assertIn((False,True),flags)
        self.assertIn((True,True),flags)

if __name__=='__main__':unittest.main()

class ClosureTargetFactorizationTests(unittest.TestCase):
    def test_matched_worked_examples_make_closure_independent_of_target(self):
        from tests.test_composed_closure_repair import query,frames
        from golden_board.course_foundation import foundation_result
        p=build_foundation(ROOT);q=query(p,'prior-closure')
        self.assertEqual(q['worked_variants'],[
            {'op':'termination','prefix':'f2f3 e7e5 g2g4 d8h4','move':'a2a3'},
            {'op':'termination','prefix':'e2e4 e7e5 f2f3 d8h4','move':'h4e1'}])
        work=frames(p,'prior-closure','worked')
        self.assertEqual(len(work),6)
        self.assertEqual(work[3][197:200],[22,13,13])
        self.assertEqual(work[5][197:200],[22,22,22])
        self.assertEqual(work[0][:90],work[4][:90])
        king=frames(p,'king-retention','worked')
        self.assertEqual(king[2][:90],work[2][:90])
        combinations=set()
        for f in king[1::2]+work[1::2]:
            if f[197]!=22:continue
            number=lambda t:0 if t==22 else t-12
            row,col=number(f[94]),number(f[95])
            target=f[(1+row)*10+1+col]
            combinations.add((f[198]==13,target in (37,43)))
        self.assertEqual(combinations,{(False,False),(False,True),(True,False),(True,True)})
        for spec in q['worked_variants']:
            result=foundation_result(spec)
            self.assertFalse(result['accepted'])
            self.assertEqual(result['after_side'],0)
            self.assertEqual(result['closed_before'],result['closed_after'])
