import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import admit_gap113_offline741 as tool


def sample(tests,bit='0x1'):
    return dict(design={'design/verilog.design.xml':'a'*64},tests=tests,input_hashes={'/tmp/raw-fixture':'b'*64},
        metrics={m:{'ara_tb.dut.i_ara_soc.i_system':dict(width=4,checksum='101',bits=bit)} for m in tool.bitmap.METRICS})


class Tests(unittest.TestCase):
    def test_complete_or_exact_prefix(self):
        before=sample(['oldA','oldB']);single=sample(['new'],'0x2')
        after,delta=tool.combine(before,single)
        self.assertEqual(after['tests'],['oldA','oldB','new'])
        self.assertTrue(all(v['ara_tb.dut.i_ara_soc.i_system']['bits']=='0x3' for v in after['metrics'].values()))
        self.assertEqual(delta['metrics'],dict.fromkeys(tool.bitmap.METRICS,1))

    def test_four_metric_zero_is_not_toggle_zero(self):
        after,delta=tool.combine(sample(['old']),sample(['new']))
        self.assertEqual(delta['metrics'],dict.fromkeys(tool.bitmap.METRICS,0))
        self.assertEqual(after['tests'],['old','new'])
        proof=json.loads(tool.QUAL.read_bytes());audit=json.loads((tool.QUAL.parent/'runtime-audit.json').read_bytes())
        gain=json.loads((tool.QUAL.parent/'toggle-gain.json').read_bytes())
        tool.qualification_contract(proof,audit,gain)
        self.assertEqual(gain['total_new_serialized_toggle_positions'],2402)
        self.assertEqual(len(gain['primary_target_hits']),74)

    def test_each_metric_checksum_shape_universe_rejected(self):
        for metric in tool.bitmap.METRICS:
            for key,value in [('checksum','102'),('width',5),('bits','0x20')]:
                broken=sample(['new']);broken['metrics'][metric]['ara_tb.dut.i_ara_soc.i_system'][key]=value
                with self.assertRaises(ValueError):tool.combine(sample(['old']),broken)
            broken=sample(['new']);broken['metrics'][metric]={}
            with self.assertRaises(ValueError):tool.combine(sample(['old']),broken)

    def test_design_duplicate_vdb_and_raw_pin_conflict(self):
        before=sample(['old'])
        for change in ('design','tests','pins','metrics'):
            broken=sample(['new'])
            if change=='design':broken['design']={'design/verilog.design.xml':'c'*64}
            elif change=='tests':broken['tests']=['old']
            elif change=='pins':broken['input_hashes']={'/tmp/raw-fixture':'c'*64}
            else:del broken['metrics']['fsm']
            with self.assertRaises(ValueError):tool.combine(before,broken)

    def test_qualification_failure_incomplete_oracle_and_no_gain(self):
        proof=json.loads(tool.QUAL.read_bytes());audit=json.loads((tool.QUAL.parent/'runtime-audit.json').read_bytes())
        gain=json.loads((tool.QUAL.parent/'toggle-gain.json').read_bytes())
        for part,key,value in [('proof','coverage_admitted',True),('proof','full_scalar_isa_verified',True),
            ('proof','spike_custom_isa_pass',True),('audit','full_vrf_bytes',4096),('audit','source_guard_bytes',0),
            ('audit','csr_values',12),('gain','total_new_serialized_toggle_positions',0),('gain','official_percentage',True)]:
            p,a,g=copy.deepcopy((proof,audit,gain));{'proof':p,'audit':a,'gain':g}[part][key]=value
            with self.assertRaises(ValueError):tool.qualification_contract(p,a,g)
        for key,value in [('exceptions',1),('protocol_errors',1),('outstanding',1),('responses',50)]:
            a=copy.deepcopy(audit);a['contract'][key]=value
            with self.assertRaises(ValueError):tool.qualification_contract(proof,a,gain)

    def test_nested_elf_ledger_and_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);elf=directory/'prior.elf';elf.write_bytes(b'old')
            ledger=directory/'evidence-pins.json';tool.life.save(ledger,{str(elf):tool.life.digest(elf)})
            pins={str(ledger):tool.life.digest(ledger)}
            self.assertEqual(tool.elf_hashes(pins),{tool.life.digest(elf)})
            elf.write_bytes(b'changed')
            with self.assertRaises(ValueError):tool.elf_hashes(pins)

    def test_missing_parent_authorization_never_writes(self):
        with patch.object(tool,'verify') as verify:
            with self.assertRaises(ValueError):tool.admit(Path('/tmp/no-admit'),'x',False)
            verify.assert_not_called()


if __name__=='__main__':unittest.main()
