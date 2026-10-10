import copy
import unittest
import review_cva6_parent_rvfi_output as m


class CoreProbeSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=m.CORE.read_text();cls.producer=m.PRODUCER.read_text();cls.system=m.SYSTEM.read_text()
        cls.definition=next(d for d in m.frozen.xml(m.DB/'shape/tgl.verilog.shape.xml').iter('tgldef') if d.get('name')=='cva6')

    def test_actual_producer_core_monitor_guarded_fanout(self):
        proof=m.source_contract(self.core,self.producer,self.system)
        self.assertFalse(proof['hardware_feedback'])
        self.assertTrue(proof['producer_core_instance_unconditionally_declared'])

    def test_core_runtime_feedback_rejected(self):
        with self.assertRaises(ValueError):m.source_contract(self.core+'\nassign cvxif_req_o = rvfi_probes_o;\n',self.producer,self.system)

    def test_producer_readback_or_functional_port_rejected(self):
        for text in (self.producer+'\nassign func = rvfi_probes_o.csr.mip_q;\n',
                     self.producer.replace('output rvfi_probes_t','inout rvfi_probes_t')):
            with self.assertRaises(ValueError):m.source_contract(self.core,text,self.system)

    def test_monitor_reroute_or_additional_fanout_rejected(self):
        for text in (self.system.replace(') i_cva6_rvfi (',') i_functional_unit ('),
                     self.system+'\nassign acc_req = rvfi_probes;\n'):
            with self.assertRaises(ValueError):m.source_contract(self.core,self.producer,text)

    def test_changed_guard_types_empty_connection_rejected(self):
        for text in (self.system.replace('`ifdef FOR_VERIFY','`ifdef SOME_OTHER_BUILD'),
                     self.system.replace('.rvfi_probes_o    (rvfi_probes             )','.rvfi_probes_o    (acc_req                 )')):
            with self.assertRaises(ValueError):m.source_contract(self.core,self.producer,text)

    def test_comment_string_not_functional_feedback(self):
        proof=m.source_contract(self.core+'\n// rvfi_probes_o\ninitial $display("rvfi_probes_o");\n',self.producer,self.system)
        self.assertFalse(proof['hardware_feedback'])

    def test_actual457_exact_full_complement(self):
        target,protected=m.partition(self.definition,38866)
        self.assertEqual((len(target),len(protected)),(457,1315))
        self.assertEqual(sum(t['width'] for t in target),2599)
        self.assertEqual(sum(p['kind']=='arrays' for p in protected),31)

    def test_ports_control_CSR_and_prefix_lookalikes_not_targets(self):
        for name in ('rvfi_csr.mip_q','cvxif_req_o.issue_valid','noc_req_o.aw.addr',
                     'rvfi_probes_o_functional.csr.mip_q','rvfi_probes_o.instruction'):
            self.assertFalse(m.selected(name))

    def test_compiled_aux_source_type_port_exclusion_drift(self):
        for key,value in (('aux_file','595'),('aux_line_num','344'),('file','419'),
                          ('portnode','0'),('type','3'),('excluded','1')):
            d=copy.deepcopy(self.definition)
            next(n for n in d.find('tglshape') if m.selected(n.get('name','')) and n.tag!='arrays').set(key,value)
            with self.assertRaises(ValueError):m.partition(d,38866)

    def test_width_missing_duplicate_native_identity_rejected(self):
        with self.assertRaises(ValueError):m.partition(self.definition,38865)
        for action in ('missing','duplicate'):
            d=copy.deepcopy(self.definition);shape=d.find('tglshape');n=next(n for n in shape if m.selected(n.get('name','')))
            if action=='missing':shape.remove(n)
            else:shape.append(copy.deepcopy(n))
            with self.assertRaises(ValueError):m.partition(d,38866)

    def test_same_width_bounds_shift_rejected(self):
        d=copy.deepcopy(self.definition)
        n=next(n for n in d.find('tglshape') if m.selected(n.get('name','')) and n.tag=='vectornode')
        n.set('left',str(int(n.get('left'))+1));n.set('right',str(int(n.get('right'))+1))
        with self.assertRaises(ValueError):m.partition(d,38866)

    def test_parent_system_child_scope_cannot_substitute(self):
        m.scope_identity(m.SCOPE,m.DESIGN_CHECKSUM,m.CHECKSUM)
        for scope in (m.SCOPE+'.i_cva6_rvfi_probes',m.SCOPE.rsplit('.',1)[0],m.SCOPE+'.child'):
            with self.assertRaises(ValueError):m.scope_identity(scope,m.DESIGN_CHECKSUM,m.CHECKSUM)

    def test_exact_macro_and_nested_leaf_type_bindings(self):
        files={n.get('id'):m.Path(n.get('name')) for n in m.frozen.xml(m.DB/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
        targets,_=m.partition(self.definition,38866)
        records=m.bind_types(targets,files)
        self.assertEqual(len(records),457)
        self.assertTrue(all(n['source_binding']['root_port_line']==343 for n in records))
        self.assertTrue(any(n['source_binding']['root_member']=='pmpcfg_q' for n in records))


if __name__=='__main__':unittest.main()
