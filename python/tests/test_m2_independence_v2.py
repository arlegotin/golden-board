"""The ninth predicate counts failed families without erasing their witnesses."""
import unittest

from golden_board.m2_independence_v2 import damage_binding_predicate


class CompleteIndependenceV2(unittest.TestCase):
    def fixture(self):
        counts=(16,4,256,128,1908,21,7632,415)
        return dict(physical_units=1908,accidental_case_count=sum(counts),
            family_rows=[dict(family_id=f'D{i}',case_count=count,
                             wrong_accept_count=0,result='pass') for i,count in enumerate(counts)])

    def test_exact_positive_witness_count_excludes_boundary_diagnostics(self):
        value=self.fixture();value['reauthored_boundary']=dict(case_count=21,wrong_accept_count=9)
        value['boundary_kats']=dict(rows=[0]*4)
        self.assertEqual(damage_binding_predicate(value,1908),dict(
            predicate_id='damage-promise-binding',witness_count=10380,
            minimum_surviving_count=1,violation_count=0,result='pass'))

    def test_failed_family_contributes_every_owned_witness(self):
        value=self.fixture()
        value['family_rows'][7]['result']='fail'
        row=damage_binding_predicate(value,1908)
        self.assertEqual((row['witness_count'],row['violation_count'],row['result']),(10380,415,'fail'))
        value['family_rows'][4]['result']='fail'
        self.assertEqual(damage_binding_predicate(value,1908)['violation_count'],2323)

    def test_missing_reordered_boolean_or_shrunk_witnesses_reject(self):
        mutations=[]
        value=self.fixture();value['family_rows'].pop();mutations.append(value)
        value=self.fixture();value['family_rows'].reverse();mutations.append(value)
        value=self.fixture();value['family_rows'][7]['case_count']=414;mutations.append(value)
        value=self.fixture();value['family_rows'][0]['case_count']=True;mutations.append(value)
        value=self.fixture();value['family_rows'][0]['wrong_accept_count']=1;mutations.append(value)
        value=self.fixture();value['physical_units']=1907;mutations.append(value)
        for value in mutations:
            with self.subTest(value=value),self.assertRaises(ValueError):damage_binding_predicate(value,1908)


if __name__=='__main__':unittest.main()
