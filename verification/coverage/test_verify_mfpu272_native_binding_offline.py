import copy
import json
import unittest
from unittest.mock import patch

import verify_mfpu272_native_binding_offline as o
from test_mfpu_constants272_native_bind import node,text


class OfflineBindingTests(unittest.TestCase):
    def test_exact_internal_singleton_bare_signal_not_multi_bit_or_port(self):
        n=node('mask_slice',left='0',right='0')
        self.assertEqual(o.match_label(n,'mask_slice','signal'),('aggregate',None))
        for bad,kind in [(dict(n,left='1'),'signal'),(dict(n,portnode='2'),'signal'),
                         (dict(n,portnode='3'),'signal'),(n,'port'),(n,'register')]:
            self.assertIsNone(o.match_label(bad,'mask_slice',kind))
        self.assertIsNone(o.match_label(n,'foreign','signal'))

    def test_exact_mda_dimensions_source_role_unchanged(self):
        n=node('operands_i',kind='arrays',port='2',packedrange='2 0 63 0 ',unpackedrange='')
        row=dict(type='MDA',path='operands_i[2:0][63:0]',meta='operands_i[2:0][63:0]')
        self.assertTrue(o.native_role(n,row))
        self.assertFalse(o.native_role(node('operands_i',port='2'),row))
        self.assertFalse(o.native_role(n,dict(row,meta='foreign')))
        self.assertIsNone(o.match_label(n,'operands_i[63:0][2:0]','MDA'))
        for kind in ('register','UNKNOWN','MDA',''):
            self.assertFalse(o.native_role(node('internal'),dict(row,type=kind)))

    def test_real_first_scope_exact_source_native_bijection_preserves_all_protected(self):
        c=o.life.read_bound(o.RUN/'config.json',o.SEAL);i=c['instances'][0]
        raw=(o.RUN/'native_before_0.tsv').read_text()
        with self.assertRaises(ValueError):o.frozen.bind_inventory(i,raw)
        value=o.binder()(i,raw)
        self.assertEqual(value['compiled_object_count'],len(i['typed_objects']))
        self.assertEqual(value['actual_row_count'],len(o.frozen.pack.native.native_rows(raw)))
        self.assertEqual({s['name'] for s in value['signals']},{s['name'] for s in i['targets']})
        aliases=o.alias_proof(i,raw)
        mask=next(a for a in aliases if a['name']=='gen_parallel_slices[1].active_format.mask_slice')
        self.assertEqual(mask['compiled_attributes']['portnode'],'0')
        self.assertEqual(mask['compiled_attributes']['left'],mask['compiled_attributes']['right'])
        self.assertTrue(mask['protected'])
        self.assertTrue(any(a['reason']=='EXACT_ORDERED_ARRAY_MDA_DISPLAY' for a in aliases))

    def test_missing_extra_wrong_bounds_duplicate_native_still_rejected(self):
        n=node('mask_slice',left='0',right='0')
        i=dict(scope='root',design_module_checksum='1',toggle_checksum='2',typed_objects=[n],targets=[])
        bind=o.binder()
        self.assertEqual(bind(i,text([('mask_slice','signal')]))['signals'],[])
        for rows in [[('mask_slice','port')],[('mask_slice[1:0]','signal')],
                     [('mask_slice','signal'),('foreign','signal')],[('mask_slice','signal')]*2]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):bind(i,text(rows))
        with self.assertRaises(ValueError):bind(i,'handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\n')

    def test_terminal_timeout_nonzero_fake_wrapper_zero_wrong_command_rejected(self):
        c=o.life.read_bound(o.RUN/'config.json',o.SEAL)
        terminal=json.loads((o.RUN/'terminal.json').read_bytes())
        execution=json.loads((o.RUN/'execution.json').read_bytes())
        live=json.loads((o.RUN/'live-identity.json').read_bytes())
        log=(o.RUN/'service.log').read_text()
        fields=dict(Id=o.UNIT,LoadState='loaded',ActiveState='failed',SubState='failed',
                    ExecMainCode='1',ExecMainStatus='1',ExecStart=str(o.frozen.__file__)+' '+str(o.RUN)+' '+o.SEAL)
        self.assertEqual(o.terminal_gate(c,terminal,execution,live,log,fields)['wrapper_OS_exit_status'],1)
        for bad in [dict(terminal,returncode=1),dict(terminal,timeout=True),dict(terminal,actual_dve=[])]:
            with self.assertRaises(ValueError):o.terminal_gate(c,bad,execution,live,log,fields)
        for bad in [dict(fields,ExecMainStatus='0'),dict(fields,ActiveState='active'),dict(fields,ExecStart='foreign')]:
            with self.assertRaises(ValueError):o.terminal_gate(c,terminal,execution,live,log,bad)

    def test_adapter_anchor_and_original_source_hash_guard(self):
        digest=o.life.digest
        with patch.object(o.life,'digest',lambda p:'0'*64 if str(p)==str(o.frozen.__file__) else digest(p)):
            with self.assertRaises(ValueError):o.binder()


if __name__=='__main__':unittest.main()
