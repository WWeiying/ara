import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_btb_bit0_132_v4 as c
import test_capture_btb_bit0_132_v3 as prior_tests


class Pipeline(prior_tests.Pipeline):
    def fixture(self,out):
        config,_,names=super().fixture(out)
        config.update(native_parser_semantics=c.SEMANTICS,native_export_origin_seal=c.ORIGIN_SHA,
                      native_export_first_sha=c.FIRST_SHA)
        config['pins']=dict(config['pins'],**c.prior.read_config(c.ORIGIN,c.ORIGIN_SHA)['pins'])
        (out/'config.json').write_text(json.dumps(config))
        text=(out/'selection.tcl').read_text().replace(str(Path(c.prior.__file__).resolve()),
                                                     str(Path(c.__file__).resolve()))
        (out/'selection.tcl').write_text(text)
        return config,c.digest(out/'config.json'),names

    def pipeline(self,out,mutation='generated'):
        real_run=subprocess.run
        actual=str(c.ORIGIN/'first.el')
        def execute(args,**kwargs):
            script=kwargs['input'];position=script.index('# Source through an actual proc')
            mock='''
rename gui_exclusion_file before_native_serialization
proc gui_exclusion_file {args} {
    if {[lindex $args 0] eq "-save" && [string first "Toggle " $::state] >= 0 &&
        [string first { [1] } $::state] < 0} {
        set stream [open {%s} r];set ::state [read $stream];close $stream
    }
    return [eval before_native_serialization $args]
}
'''%actual
            kwargs['input']=script[:position]+mock+script[position:]
            return real_run(args,**kwargs)
        with patch.object(prior_tests.subprocess,'run',execute):return super().pipeline(out,mutation)


class GrammarTests(unittest.TestCase):
    def first(self):return (c.ORIGIN/'first.el').read_text()

    def test_actual_first_native_full_132_and_complement(self):
        evidence=c.mapping()
        self.assertEqual(evidence['directives'],66)
        self.assertEqual(evidence['direction_identities'],132)
        self.assertEqual(evidence['protected_direction_intersection'],0)
        self.assertFalse(evidence['second_export_exists'])
        self.assertEqual(c.native_records(self.first()),c.plan.records(c.plan.el_text()))

    def test_annotation_position_only_and_direction_pairs(self):
        lines=self.first().splitlines();annotation=next(s for s in lines if s.startswith('ANNOTATION:'))
        bare=[s for s in lines if s!=annotation]
        for index in (0,2,len(bare)):
            moved=list(bare);moved.insert(index,annotation)
            self.assertEqual(c.native_records('\n'.join(moved)),c.native_records(self.first()))
        pairs=[]
        for s in lines:
            if s.startswith('Toggle '):pairs.extend(s.replace('Toggle ','Toggle '+d+' ',1) for d in ('0to1','1to0'))
            else:pairs.append(s)
        self.assertEqual(c.native_records('\n'.join(pairs)),c.native_records(self.first()))
        with self.assertRaises(ValueError):c.native_records('\n'.join(pairs[:-1]))

    def test_annotation_and_all_physical_extras_rejected(self):
        text=self.first();annotation=next(s for s in text.splitlines() if s.startswith('ANNOTATION:'))
        mutations=[text+'\n'+annotation,text.replace(annotation,''),text.replace(c.plan.NOTE,'foreign'),
            text.replace(' [0] ',' [1] ',1),text.replace(' [0] ',' ',1),
            text.replace(' [0] ',' [0:1] ',1),text.replace('[63:0]','[63:1]',1),
            text+text.splitlines()[2]+'\n',text+'\nINSTANCE: '+c.plan.SCOPE,
            text+'\nCHECKSUM: "'+c.plan.CHECKSUM+'"',
            text+'\nToggle btb_update_i.valid "logic btb_update_i.valid"',
            text.replace(c.plan.CHECKSUM,'1 1574888635'),
            text.replace(c.plan.SCOPE,c.plan.SCOPE+'.foreign')]
        for changed in mutations:
            with self.subTest(tail=changed[-100:]),self.assertRaises(ValueError):c.native_records(changed)

    def test_actual_native_serialization_in_full_standalone_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);_,_,result=Pipeline().pipeline(out)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout.splitlines().count('BTB132_NATIVE_DONE'),1)
            self.assertEqual((out/'first.el').read_bytes(),(c.ORIGIN/'first.el').read_bytes())
            self.assertEqual(c.native_records((out/'first.el').read_text()),
                             c.native_records((out/'second.el').read_text()))
            for stage in c.original.STAGES:c.prior.metrics(out,stage)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_bad_physical_reload_remains_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);_,_,result=Pipeline().pipeline(out,'reload')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue((out/'error.txt').exists())
            self.assertNotIn('BTB132_NATIVE_DONE',result.stdout)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_actual_prepare_pins_measured_first_and_unchanged_Tcl_candidate(self):
        with tempfile.TemporaryDirectory(dir=c.plan.OUT,prefix='btb132-v4-host-') as temp:
            out=Path(temp);out.rmdir()
            seal=c.prepare(out);config=c.read_config(out,seal)
            self.assertEqual(config['pins'][str(c.ORIGIN/'first.el')],c.FIRST_SHA)
            self.assertEqual((out/'candidate.el').read_bytes(),(c.ORIGIN/'candidate.el').read_bytes())
            evidence=json.loads((out/'native-grammar-mapping.json').read_bytes())
            self.assertEqual(evidence['direction_identities'],132)
            self.assertEqual(len(c.original.complement(config['inventory'])),8860)
            self.assertFalse((out/'execution.json').exists())


def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(GrammarTests)
if __name__=='__main__':unittest.main()
