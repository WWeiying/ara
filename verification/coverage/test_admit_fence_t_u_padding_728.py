import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import admit_fence_t_u_padding_728 as tool


class AdmissionTests(unittest.TestCase):
    def test_only_three_exact_seals(self):
        seals=(tool.candidate.BASE_SHA,tool.candidate.POST_SHA,tool.CANDIDATE_SHA)
        tool.identity(*seals)
        for i in range(3):
            bad=list(seals);bad[i]='wrong'
            with self.assertRaises(ValueError):tool.identity(*bad)

    def test_complete_actual_scoped_replay_no_OS_or_UVM_clean_claim(self):
        post=json.loads(tool.candidate.POST.read_bytes());plan=json.loads(tool.old.PLAN.read_bytes())
        tool.candidate.post_contract(post);tool.replay_post(post,plan)
        self.assertIsNone(post['OS_returncode']);self.assertFalse(post['UVM_clean'])

    def test_actual_full6162_OR_and_prefix(self):
        before=json.loads((tool.candidate.BASE/'combined-bits.json').read_bytes())
        single=json.loads((tool.CANDIDATE/'single-bits.json').read_bytes())
        combined,delta,gained=tool.candidate.validate_population(before,single)
        self.assertEqual(combined['tests'][:-1],before['tests'])
        self.assertEqual(delta['metrics'],tool.EXPECTED_DELTA);self.assertEqual(len(gained),26)

    def test_qualification_promotion_rejected(self):
        post=json.loads(tool.candidate.POST.read_bytes())
        for key,value in (('UVM_clean',True),('OS_returncode',0),('cyclequalified',True),
                          ('generic_UVM_override',True),('full_ISA_reference_verified',True)):
            bad=copy.deepcopy(post);bad[key]=value
            with self.assertRaises(ValueError):tool.candidate.post_contract(bad)

    def test_reviewed_prepared_seal_and_exact_contents_required(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'prepared.json';proposal=dict(scope='exact case');p.write_bytes(tool.serialized(proposal))
            seal=tool.old.sha(p);tool.approval_gate(p,seal,proposal)
            for badseal,badproposal in ((None,proposal),('wrong',proposal),(seal,dict(scope='other'))):
                with self.assertRaises(ValueError):tool.approval_gate(p,badseal,badproposal)

    def test_prepare_creates_sidecar_only_never_formal_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);output=root/'formal';pins={}
            products={'evidence-pins.json':pins,'status.json':dict(coverage_admitted=True)}
            args=['prepare','--base-seal',tool.candidate.BASE_SHA,'--post-seal',tool.candidate.POST_SHA,
                  '--candidate-seal',tool.CANDIDATE_SHA,'--output',str(output)]
            with patch.object(tool,'OUT',root),patch.object(tool,'evaluate',return_value=(products,'inputs\n')):
                tool.main(args)
                self.assertFalse(output.exists());self.assertTrue(root.joinpath('formal.prepared.json').exists())
                with self.assertRaises(ValueError):tool.main(args)

    def test_admit_without_external_seal_rejected_before_replay(self):
        args=['admit','--base-seal',tool.candidate.BASE_SHA,'--post-seal',tool.candidate.POST_SHA,
              '--candidate-seal',tool.CANDIDATE_SHA,'--output',str(tool.OUT/'not-created-fence-test')]
        with patch.object(tool,'evaluate') as evaluate:
            with self.assertRaises(ValueError):tool.main(args)
            evaluate.assert_not_called()


if __name__=='__main__':unittest.main()
