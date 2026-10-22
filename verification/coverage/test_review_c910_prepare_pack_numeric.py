import copy
import unittest
import review_c910_prepare_pack_numeric as m


class NativeShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=m.r.xml(m.r.DB/'shape/tgl.verilog.shape.xml')
        cls.nodes={}
        for module in m.ALLOW:
            definition=next(n for n in root.iter('tgldef') if n.get('name')==module)
            cls.nodes[module]=[dict(kind=n.tag,**n.attrib) for n in definition.find('tglshape')]

    def test_actual_whole_shape_partition(self):
        for module,nodes in self.nodes.items():
            targets,protected=m.partition(module,nodes)
            self.assertEqual(len(targets),len(m.ALLOW[module]))
            self.assertEqual(len(targets)+len(protected),len(nodes))
            self.assertTrue(all(n['portnode']=='0' for n in targets))
            self.assertTrue(all(n['kind']=='vectornode' for n in targets))

    def test_control_ports_round_flags_special_not_targets(self):
        for module,nodes in self.nodes.items():
            _,protected=m.partition(module,nodes)
            self.assertTrue(all(n in [dict(x,retention_reason=n['retention_reason'])
                for x in nodes] for n in protected))
            for n in nodes:
                if n['portnode']!='0' or n['kind']=='node' or any(s in n['name'] for s in ('qnan','_rm','_rst_','denorm')):
                    self.assertNotIn(n['name'],m.ALLOW[module])

    def test_reject_range_type_port_line_file_excluded_change(self):
        module='ct_vfdsu_pack'
        for key,value in (('left','53'),('right','1'),('type','0'),('portnode','2'),
                          ('line_num','98'),('file','371'),('excluded','1')):
            nodes=copy.deepcopy(self.nodes[module])
            next(n for n in nodes if n['name']=='ex4_frac')[key]=value
            with self.assertRaises(ValueError):m.partition(module,nodes)

    def test_no_shrink_or_wholemodule(self):
        for module,nodes in self.nodes.items():
            for names in (set(),{n['name'] for n in nodes},set(m.ALLOW[module])- {next(iter(m.ALLOW[module]))}):
                with self.assertRaises(ValueError):m.partition(module,nodes,names)

    def test_duplicate_missing_native(self):
        for module,nodes in self.nodes.items():
            target=next(n for n in nodes if n['name'] in m.ALLOW[module])
            for mutation in (nodes+[target],[n for n in nodes if n is not target]):
                with self.assertRaises(ValueError):m.partition(module,mutation)

    def test_exact_source_dataflow_spans(self):
        for module,fields in m.ALLOW.items():
            path=m.r.ROOT/('hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'+module+'.v')
            lines=path.read_text().splitlines()
            for name,(line,left,typ,first,last) in fields.items():
                self.assertIn(name,lines[line-1])
                self.assertIn(name,'\n'.join(lines[first-1:last]))
                self.assertIn('[%d:0]'%left,lines[line-1])


if __name__=='__main__':unittest.main()
