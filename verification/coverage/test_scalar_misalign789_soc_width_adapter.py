import unittest
import scalar_misalign789_soc_width_adapter as a


class Override(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts={n:(a.life.ROOT/p).read_text() for n,p in dict(
            tb='hardware/tb/ara_tb.sv',harness='hardware/tb/ara_testharness.sv',
            soc='hardware/src/ara_soc.sv',system='hardware/src/ara_system.sv',
            build='hardware/deps/cva6/core/include/build_config_pkg.sv').items()}
    def test_actual_frozen_chain_and_layout(self):
        p=a.source_proof()
        self.assertEqual(p['layouts']['dcache_req_i_t']['width'],136)
        self.assertEqual(p['parameters']['CVA6Cfg.DCACHE_USER_WIDTH'],1)
        old=a.original.source_proof()
        self.assertEqual({n:v for n,v in p['layouts'].items() if n!='dcache_req_i_t'},
            {n:v for n,v in old['layouts'].items() if n!='dcache_req_i_t'})
    def reject(self,name,old,new):
        texts=dict(self.texts);self.assertIn(old,texts[name]);texts[name]=texts[name].replace(old,new,1)
        with self.assertRaises(ValueError):a.derive_override(texts)
    def test_base_config_width_not_override(self):
        self.reject('soc','cfg.AxiUserWidth          = AxiUserWidth;', 'cfg.AxiUserWidth          = 64;')
    def test_extra_writer(self):
        self.reject('soc','cfg.AxiUserWidth          = AxiUserWidth;', 'cfg.AxiUserWidth = AxiUserWidth; cfg.AxiUserWidth = 2;')
    def test_harness_connection(self):
        self.reject('harness','.AxiUserWidth(AxiUserWidth )','.AxiUserWidth(64 )')
    def test_build_assignment(self):
        self.reject('build','cfg.DCACHE_USER_WIDTH = CVA6Cfg.AxiUserWidth;','cfg.DCACHE_USER_WIDTH = 64;')
    def test_core_connection(self):
        self.reject('system','.CVA6Cfg          (CVA6Cfg           )','.CVA6Cfg          (otherCfg          )')
    def request(self, bad=None):
        layout=a.source_proof()['layouts']['dcache_req_i_t']
        bits=['0']*136
        fields=layout['fields']
        bits[135-fields['data_wuser'][0]]='x'
        if bad:bits[135-fields[bad][0]]='x'
        return ''.join(bits),layout
    def test_only_unread_single_user_x(self):
        bits,layout=self.request();r=a.read_request(bits,layout)
        self.assertIsNone(r['data_wuser']);self.assertEqual(r['data_we'],0)
    def test_kill_x_rejected(self):
        bits,layout=self.request('kill_req')
        with self.assertRaises(ValueError):a.read_request(bits,layout)
    def test_tag_x_rejected(self):
        bits,layout=self.request('tag_valid')
        with self.assertRaises(ValueError):a.read_request(bits,layout)
    def test_address_x_rejected(self):
        bits,layout=self.request('address_tag')
        with self.assertRaises(ValueError):a.read_request(bits,layout)
    def test_write_enable_one_rejected(self):
        bits,layout=self.request();bits=list(bits);bits[135-layout['fields']['data_we'][0]]='1'
        with self.assertRaises(ValueError):a.read_request(''.join(bits),layout)
    def test_wrong_width_rejected(self):
        bits,layout=self.request();layout=dict(layout,width=199)
        with self.assertRaises(ValueError):a.read_request(bits,layout)
    def test_every_non_user_field_unknown_rejected(self):
        _,layout=self.request()
        for name in set(layout['fields'])-{'data_wuser'}:
            for unknown in ('x','z'):
                with self.subTest(field=name,unknown=unknown):
                    bits,_=self.request();bits=list(bits)
                    bits[135-layout['fields'][name][0]]=unknown
                    with self.assertRaises(ValueError):a.read_request(''.join(bits),layout)
    def test_user_known_zero_and_one_also_valid_when_not_writing(self):
        for value in ('0','1'):
            bits,layout=self.request();bits=list(bits);bits[135-layout['fields']['data_wuser'][0]]=value
            self.assertEqual(a.read_request(''.join(bits),layout)['data_wuser'],int(value))
    def test_user_zero_does_not_allow_write(self):
        bits,layout=self.request();bits=list(bits)
        bits[135-layout['fields']['data_wuser'][0]]='0';bits[135-layout['fields']['data_we'][0]]='1'
        with self.assertRaises(ValueError):a.read_request(''.join(bits),layout)
    def test_inactive_slot1_unknown_with_known_port0_owner(self):
        layout=a.source_proof()['layouts']['scoreboard_entry_t']
        owner=(0x80002660<<374)|(6<<371)
        r=a.read_commit_owner('x'*438+format(owner,'0438b'),layout,0)
        self.assertEqual(r,dict(pc=0x80002660,trans_id=6))
    def test_unknown_commit_pc_or_tid_rejected(self):
        layout=a.source_proof()['layouts']['scoreboard_entry_t']
        for name in ('pc','trans_id'):
            bits=list('0'*876);bits[875-layout['fields'][name][0]]='x'
            with self.assertRaises(ValueError):a.read_commit_owner(''.join(bits),layout,0)
    def test_wrong_commit_width_or_slot_rejected(self):
        layout=a.source_proof()['layouts']['scoreboard_entry_t']
        with self.assertRaises(ValueError):a.read_commit_owner('0'*876,layout,1)
        with self.assertRaises(ValueError):a.read_commit_owner('0'*876,dict(layout,width=437),0)


if __name__=='__main__':unittest.main()
