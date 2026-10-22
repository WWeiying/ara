"""Offline60 config/partial-bit/full-complement negatives, never native evidence."""
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import unittest

import scoreboard_cause60_native796 as m


def table(rows, fields):
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t')
    writer.writeheader(); writer.writerows(rows); return stream.getvalue()


def bits(group, stage='before'):
    rows = []
    for t in group['targets']:
        for b in range(64):
            label = t['name'] + '[%d]' % b
            state = '1' if stage in ('selected','reloaded') and 6 <= b <= 62 else '0'
            rows.append(dict(signal=t['name'],bit=str(b),path=label,meta=label,name=label,
                coverage='0.00%',**{'0to1':state,'1to0':state}))
    return rows


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = m.read_bound(m.source.REPORT, m.SOURCE_SHA)
        cls.groups = m.groups(cls.report)
        cls.config = dict(groups=cls.groups)
        cls.el = m.source.candidate_el(cls.config)

    def test_exact60_57_6840(self):
        self.assertEqual(sum(len(g['targets']) for g in self.groups),60)
        self.assertEqual(m.semantic(self.el,self.config),6840)
        self.assertEqual(sum(len(t['selected_bits']) for g in self.groups for t in g['targets']),3420)
        for g in self.groups:
            for t in g['targets']:
                self.assertEqual(t['bits_count'],57)
                self.assertEqual(t['protected_bits'],[0,1,2,3,4,5,63])

    def test_source_archive_all450_and_writers(self):
        r, bindings, pins = m.source_packet()
        self.assertEqual(r,self.report);self.assertEqual(len(bindings),450)
        self.assertEqual(sum(b['original'] != b['evidence'] for b in bindings),3)
        dispatch = next(b for b in bindings if b['original'].endswith('/ara_dispatcher.sv'))
        self.assertEqual(dispatch['sha256'],'9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43')
        self.assertEqual(len(r['complete_ACC_whole_cause_writer_contracts'][m.source.DISPATCH]),13)
        m.source.check_pins(pins)

    def test_real_help_and60_historical_full_paths_not_bit_evidence(self):
        h = m.history(self.groups)
        self.assertEqual(len(h['compressed_cause_paths']),60)
        self.assertFalse(h['serialized_bitmap_direction_ID_mapping'])
        self.assertFalse(h['native_qualified'])
        self.assertTrue(all(r['old_handle_not_reused'] for r in h['compressed_cause_paths']))
        m.source.check_pins(h['pins'])

    def test_config_negative_full_source_pins_all_writers_range_and_direction_IDs(self):
        bindings=json.loads((m.source.PREP/'verification.json').read_bytes())['original_compiled_HDL_bindings']
        pins=dict(self.report['input_pins'],**{b['evidence']:b['sha256'] for b in bindings})
        pins[str(m.source.REPORT)]=m.SOURCE_SHA
        c=dict(schema=m.SCHEMA,groups=self.groups,source_closure=self.report,
            selected_bits=list(range(6,63)),protected_bits=[0,1,2,3,4,5,63],copies=60,
            physical_bits_per_copy=57,physical_bits=3420,directions=6840,timeout_seconds=900,
            population_application=False,automatic_retry=False,native_qualified=False,
            initial_X_qualified=False,serialized_native_direction_ID_mapping=False,
            original_compiled_HDL_bindings=bindings,pins=pins)
        m.contract(c,self.report)
        archive=str(m.source.ARCHIVE/'ara_dispatcher.sv')
        edits=[lambda c:c['pins'].pop(archive),lambda c:c['original_compiled_HDL_bindings'].pop(),
            lambda c:c['source_closure']['complete_ACC_whole_cause_writer_contracts'][m.source.DISPATCH].pop(),
            lambda c:c['groups'][0]['complete_typed_scope_inventory'].pop(),
            lambda c:c['groups'][0]['targets'][0].__setitem__('selected_bits',list(range(6,64))),
            lambda c:c['groups'][0]['targets'][0].__setitem__('directions',['0to1']),
            lambda c:c['groups'][0]['targets'][0].__setitem__('bits_count',59),
            lambda c:c['groups'][0]['targets'][0].__setitem__('port_native_binding_required',False),
            lambda c:c['groups'][0].__setitem__('toggle_checksum','0'),
            lambda c:c.__setitem__('serialized_native_direction_ID_mapping',True),
            lambda c:c.__setitem__('native_direction_ids',{'0to1':0,'1to0':1}),
            lambda c:c.__setitem__('timeout_seconds',900.0)]
        for edit in edits:
            bad=copy.deepcopy(c);edit(bad)
            with self.subTest(edit=edit),self.assertRaises(ValueError):m.contract(bad,self.report)

    def test_EL_low6_interrupt_whole_CSR_direction_orphan_negative(self):
        bad = [self.el.replace(' [6] ',' [5] ',1),self.el.replace(' [6] ',' [63] ',1),
               self.el.replace(' [6] ',' ',1),self.el.replace('Toggle ','Toggle 0to1 ',1),
               self.el.replace('ex_i.cause','mcause_q'),self.el.replace('ex_i.cause','scause_q'),
               self.el.replace('[63:0]"','[62:6]"',1),self.el + 'CHECKSUM: "1 2"\n',
               self.el + 'WHOLE_SCOPE\n',self.el.replace('INSTANCE: ara_tb.','INSTANCE: wrong.',1)]
        for text in bad:
            with self.subTest(text=text[:80]),self.assertRaises(ValueError):m.semantic(text,self.config)

    def test_five_phase_actual_flags_and_full64(self):
        for group in self.groups:
            before_rows = bits(group); fields = list(before_rows[0])
            before = m.bit_gate(table(before_rows,fields),group,'before')
            for stage in m.STAGES:
                self.assertEqual(len(m.bit_gate(table(bits(group,stage),fields),group,stage,before)),
                                 len(group['targets']) * 64)

    def test_missing_duplicate_single_direction_protected_bit_IDs(self):
        group = self.groups[0]; rows = bits(group,'selected'); fields = list(rows[0])
        mutations = [lambda rs: rs.pop(), lambda rs: rs.append(dict(rs[0])),
            lambda rs: rs[6].__setitem__('1to0','0'),lambda rs: rs[5].__setitem__('0to1','1'),
            lambda rs: rs[63].__setitem__('1to0','1'),lambda rs: rs[6].__setitem__('bit','serialized:12'),
            lambda rs: rs[6].__setitem__('path',rs[7]['path']),
            lambda rs: rs[6].__setitem__('name','cause[6]')]
        for edit in mutations:
            bad = copy.deepcopy(rows);edit(bad)
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                m.bit_gate(table(bad,fields),group,'selected')

    def test_coverage_and_identity_change_HOLD(self):
        group = self.groups[0]; rows = bits(group);fields=list(rows[0])
        before = m.bit_gate(table(rows,fields),group,'before')
        for bit,field,value,stage in [(6,'coverage','100.00%','before'),(5,'coverage','50.00%','selected'),
                                      (63,'coverage','50.00%','selected'),(6,'path','new','reset')]:
            bad=bits(group,stage);bad[bit][field]=value
            with self.subTest(bit=bit,field=field),self.assertRaises(ValueError):
                m.bit_gate(table(bad,fields),group,stage,before)

    def test_full_scope_historical_inventory_aliases_and_complement_negatives(self):
        soc=m.u.OUT/'soc-constants61-native-parent-20261008-03'
        dec=m.u.OUT/'cva6-fixed120-native768-agent-20261007-01'
        for g in self.groups:
            directory=dec if g['module']=='decoder' else soc
            old=json.loads((directory/'config.json').read_bytes())
            index=next(i for i,v in enumerate(old['instances']) if v['scope']==g['scope'])
            rs=list(csv.DictReader(io.StringIO((directory/('native_before_%d.tsv'%index)).read_text()),delimiter='\t'))
            for row in rs:row.update({'0to1':'0','1to0':'0'})
            fields=list(rs[0]);before=m.object_gate(table(rs,fields),g,'before')
            self.assertEqual(len(before),len(g['complete_typed_scope_inventory']))
            targets={t['name']+'[63:0]' for t in g['targets']}
            protected=next(i for i,row in enumerate(rs) if row['name'] not in targets)
            for edit in (lambda bad:bad.pop(),lambda bad:bad[protected].__setitem__('1to0','1'),
                         lambda bad:bad[protected].__setitem__('coverage','CHANGED'),
                         lambda bad:bad[protected].__setitem__('meta','flattened')):
                bad=copy.deepcopy(rs);edit(bad)
                with self.subTest(module=g['module'],edit=edit),self.assertRaises(ValueError):
                    m.object_gate(table(bad,fields),g,'selected',before)

    def test_Tcl_parse_only_no_GUI_entrypoint(self):
        script='set ::s60_test_only 1\nsource {%s}\nputs [info complete [read [set f [open {%s} r]]]]\nclose $f\n'%(m.ENTRY,m.ENTRY)
        r=subprocess.run(['/usr/bin/tclsh'],input=script,text=True,capture_output=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'1')
        t=m.ENTRY.read_text()
        self.assertIn('-tgl_transition 0to1',t);self.assertIn('-tgl_transition 1to0',t)
        self.assertNotIn('serialized',t)


if __name__=='__main__':unittest.main()
