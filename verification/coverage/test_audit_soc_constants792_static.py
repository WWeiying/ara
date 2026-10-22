import json
import unittest
import audit_soc_constants792_static as a


class TestProof(unittest.TestCase):
    def texts(self):
        book=json.loads(a.BOOK.read_text())
        names=('ara_soc.sv','ara_system.sv','cv64a6_imafdcv_sv39_config_pkg.sv','build_config_pkg.sv',
            'riscv_pkg.sv','branch_unit.sv','ariane_pkg.sv','cva6.sv','fpu_wrap.sv','ex_stage.sv',
            'load_unit.sv','cva6_ptw.sv','acc_dispatcher.sv','cvxif_issue_register_commit_if_driver.sv')
        from pathlib import Path
        result={}
        for n in names:
            paths=[Path(p) for p in book if Path(p).name==n]
            self.assertEqual(len(paths),1)
            self.assertEqual(a.t.digest(paths[0]),book[str(paths[0])]);result[n]=paths[0].read_text()
        return result

    def test_actual_source_guard(self):a.source_guard(self.texts())

    def test_branch_literal_mutation(self):
        text=self.texts();text['riscv_pkg.sv']=text['riscv_pkg.sv'].replace('INSTR_ADDR_MISALIGNED = 0;','INSTR_ADDR_MISALIGNED = 1;')
        with self.assertRaises(Exception):a.source_guard(text)

    def test_cvxif_enabled(self):
        text=self.texts();text['cv64a6_imafdcv_sv39_config_pkg.sv']=text['cv64a6_imafdcv_sv39_config_pkg.sv'].replace('CVA6ConfigCvxifEn = 0;','CVA6ConfigCvxifEn = 1;')
        with self.assertRaises(Exception):a.source_guard(text)

    def test_changed_read_wdata(self):
        text=self.texts();text['load_unit.sv']=text['load_unit.sv'].replace("assign req_port_o.data_wdata = '0;","assign req_port_o.data_wdata = operand;")
        with self.assertRaises(Exception):a.source_guard(text)

    def test_changed_hart(self):
        text=self.texts();text['ara_soc.sv']=text['ara_soc.sv'].replace("assign hart_id = '0;","assign hart_id = '1;")
        with self.assertRaises(Exception):a.source_guard(text)

    def test_closed_field_partition(self):
        rows=a.targets();self.assertEqual(len(rows),len({(r['scope'],r['name']) for r in rows}))
        self.assertFalse(any(r['name']=='x_result_i.hartid' or r['name']=='dcache_req_ports_id_cache.data_wdata' for r in rows))
        self.assertFalse(any('mem_q' in r['name'] or 'data_nodes' in r['name'] or 'group_hit' in r['name'] for r in rows))


if __name__=='__main__':unittest.main()
