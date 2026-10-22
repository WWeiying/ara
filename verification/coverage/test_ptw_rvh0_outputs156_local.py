"""Source mutation, exact typed EL and full sourced host capture; no EDA."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ptw_rvh0_outputs156_local as m


class PTW156(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = m.evidence()
        cls.i = cls.proof['instance']
        cls.c = dict(instances=[cls.i], design='host-design', vdb='host-vdb', test='host-test')
        cls.el = m.candidate([cls.i])
        paths = [p for p in cls.proof['pins'] if p.endswith('.sv')]
        cls.texts = {Path(p).name: Path(p).read_text() for p in paths}

    def test_actual_frozen_source_compiled_binding(self):
        self.assertEqual((self.proof['fields'], self.proof['bits'], self.proof['directions']), (12, 78, 156))
        self.assertEqual(len(self.i['typed_objects']), 149)
        self.assertEqual(sum(len(x['missing_coordinates']) for x in self.i['signals']), 156)
        self.assertEqual(sum(x['kind']=='node' for x in self.i['signals']), 8)
        self.assertFalse(self.proof['EDA_started'])

    def test_source_enable_or_config_override_rejected(self):
        for file, old, new in [
            ('cv64a6_imafdcv_sv39_config_pkg.sv', 'CVA6ConfigHExtEn = 0;', 'CVA6ConfigHExtEn = 1;'),
            ('build_config_pkg.sv', 'cfg.RVH = CVA6Cfg.RVH;', 'cfg.RVH = 1;'),
            ('ara_soc.sv', 'return cfg;', 'cfg.RVH = 1; return cfg;')]:
            t = dict(self.texts)
            self.assertIn(old, t[file]); t[file] = t[file].replace(old, new)
            with self.assertRaises(ValueError): m.source_guard(t)

    def test_all_writer_mutations_rejected(self):
        for change in ["shared_tlb_update_o.g_content = pte;",
                       "shared_tlb_update_o.g_content.ppn = '0;",
                       "shared_tlb_update_o.vmid = vmid_i;", "shared_tlb_update_o = '0;"]:
            t = dict(self.texts); t['cva6_ptw.sv'] += '\n' + change
            with self.assertRaises(ValueError): m.source_guard(t)

    def test_wrong_zero_or_guard_rejected(self):
        for old, new in [("shared_tlb_update_o.g_content = '0;", 'shared_tlb_update_o.g_content = pte;'),
                         ('&& CVA6Cfg.RVH) begin', '|| CVA6Cfg.RVH) begin'),
                         ("CVA6Cfg.RVH ? tlb_update_vmid_q : '0", "CVA6Cfg.RVH ? '0 : tlb_update_vmid_q")]:
            t = dict(self.texts); self.assertIn(old, t['cva6_ptw.sv'])
            t['cva6_ptw.sv'] = t['cva6_ptw.sv'].replace(old, new)
            with self.assertRaises(ValueError): m.source_guard(t)

    def test_exact_whole_and_both_direction_el(self):
        wanted = m.el_gate(self.el, self.c)
        lines = self.el.splitlines()
        split = '\n'.join(lines[:3] + [line.replace('Toggle ', 'Toggle '+d+' ', 1)
                                     for line in lines[3:] for d in ('0to1','1to0')]) + '\n'
        self.assertEqual(m.el_gate(split, self.c), wanted)
        for bad in [split.replace('Toggle 1to0 shared_tlb_update_o.g_content.v ',
                                  'Toggle 0to1 shared_tlb_update_o.g_content.v '),
                    '\n'.join(lines[:-1])+'\n', self.el+lines[-1]+'\n']:
            with self.assertRaises(ValueError): m.el_gate(bad, self.c)

    def test_foreign_checksum_scope_range_annotation_rejected(self):
        for old, new in [('4218964517', '4218964518'), ('313685876','313685877'),
                         (m.SCOPE, m.SCOPE+'foreign'), ('ppn[43:0]', 'ppn[44:0]'),
                         (m.ANNOTATION, 'unknown')]:
            with self.assertRaises(ValueError): m.el_gate(self.el.replace(old,new), self.c)

    def test_unknown_internal_h_state_and_parent_extra_rejected(self):
        for name in ['gpte_q', 'gpaddr_q', 'ptw_stage_q', 'shared_tlb_update_o.g_content']:
            with self.assertRaises(ValueError):
                m.el_gate(self.el+'Toggle '+name+' "logic '+name+'"\n', self.c)

    def test_existing_parent_partial_whole_collision_rejected(self):
        for name in ['shared_tlb_update_o', 'shared_tlb_update_o.g_content',
                     'shared_tlb_update_o.g_content.ppn']:
            with patch.object(m.soc.source.native, 'semantic', return_value=([], [(m.SCOPE,'313685876',name,'vector',(),(),())])):
                with self.assertRaises(ValueError): m.collision_gate('fixture')
        with patch.object(m.soc.source.native, 'semantic', return_value=([(m.SCOPE,'0','tgl','WHOLE_SCOPE')], [])):
            with self.assertRaises(ValueError): m.collision_gate('fixture')

    def test_actual_sourced_tcl_five_stages_no_eda(self):
        result = m.host_hook(self.c, m.selection(self.c), self.el)
        self.assertFalse(result['EDA_started'])
        self.assertEqual(result['scope_inventories'], 5)

    def model_rows(self):
        rows=['handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay']
        for j,n in enumerate(self.i['typed_objects']):
            dims=m.primitive.indexed.previous.frozen.dimensions(n)
            label=n['name']+''.join('[%d:%d]'%d for d in dims)
            role='MDA' if n['kind']=='arrays' else 'port' if n['portnode'] in ('2','3') else 'signal'
            rows.append('\t'.join([str(j),'Item%d'%j,'Item%d'%j,label,role,'0.00%','0.00%']))
        return '\n'.join(rows)+'\n'

    def test_full_actual_typed_complement_and_missing_foreign_rows(self):
        text=self.model_rows(); rows=m.bind(self.i,text)
        for bad in ['\n'.join(text.splitlines()[:-1])+'\n',
                    text.replace('gpaddr_q[40:0]', 'foreign_q[40:0]')]:
            self.assertNotEqual(bad,text)
            with self.assertRaises(ValueError): m.bind(self.i,bad)
        for label in ['gpaddr_q[40:0]', 'ptw_stage_q[1:0]']:
            changed=copy.deepcopy(rows); changed[label]['display']='Excluded'
            with self.assertRaises(ValueError): m.soc.stage_gate(self.i, rows, changed,'applied')
        changed=copy.deepcopy(rows); changed[m.labels(self.i)[0]]['display']='Excluded'
        with self.assertRaises(ValueError): m.soc.stage_gate(self.i, rows, changed,'reset')

    def test_hash_drift_rejected(self):
        with patch.object(m.life, 'digest', return_value='0'*64):
            with self.assertRaises(ValueError): m.evidence()

    def test_prepare_requires_fresh_local_output(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): m.prepare(Path(d))

    def test_run_requires_exact_review_before_eda(self):
        with self.assertRaises(ValueError): m.run(m.life.OUT/'unused', 'a'*64, 'b'*64)

    def test_terminal_execution_foreign_or_timeout_rejected(self):
        out=m.life.OUT/'host-only'
        c=dict(output=str(out), identity=dict(executable='/sealed/dve.exe',
               roles=dict(launcher='/sealed/dve', xvfb_run='/usr/bin/xvfb-run')))
        live=[dict(pid=123, exe='/sealed/dve.exe', cwd=str(out))]
        t=dict(returncode=0, timeout=False, actual_dve=live)
        e=dict(config_seal='seal', cwd=str(out), timeout_seconds=900, command=m.command(c,out))
        m.terminal_gate(c,'seal',out,t,live,e)
        for change in [dict(returncode=False), dict(returncode=1), dict(timeout=True), dict(actual_dve=[])]:
            with self.assertRaises(ValueError): m.terminal_gate(c,'seal',out,dict(t,**change),live,e)
        bad=copy.deepcopy(e); bad['command'][0]='/foreign/xvfb-run'
        with self.assertRaises(ValueError): m.terminal_gate(c,'seal',out,t,live,bad)


if __name__ == '__main__': unittest.main()
