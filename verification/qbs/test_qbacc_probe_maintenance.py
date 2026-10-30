import csv
import unittest

from qbacc_probe_maintenance import SHAPES,check_probe_with_maintenance
import test_qbacc_soc as fixture


class MaintenanceClassification(fixture.ProbeChecker):
    def setUp(self):
        super().setUp()
        self.rows=[]
        for i,(m,n) in enumerate(SHAPES):
            word=((m-1+8)<<25)|(11<<20)|(10<<15)|(8<<7)|0x5b
            common=dict(arch_seq=str(i),insn=f"{word:08x}",vd="8",eew="2",vl=str(m*32),
                        vstart="0",use_vd="1",source="0",lane="0",addr="0",be="00")
            if i%2 or i==12:
                for r in range(m):
                    local=dict(common,vd=str(8+r),vl="32")
                    self.rows.append(dict(local,event="alloc"))
                    for w in range(4):
                        for lane in range(4):
                            self.rows.append(dict(local,event="write",source="3",lane=str(lane),
                                                  addr=str((8+r)*4+w),be="ff"))
            self.rows.append(dict(common,event="alloc"))
            if i!=12:
                for r in range(m):
                    for w in range(4):
                        for lane in range(4):
                            be=255 if m<=4 else (15*int(w*8+lane<n)+240*int(w*8+lane+4<n))
                            if be:
                                self.rows.append(dict(common,event="write",source="4",lane=str(lane),
                                                      addr=str((8+r)*4+w),be=f"{be:02x}"))
        self.write()

    def write(self):
        with self.trace.open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=self.rows[0].keys())
            writer.writeheader();writer.writerows(self.rows)

    # Base tests operate on the minimal old fixture; only these new tests use
    # the full alloc/write fixture and the successor classifier.
    def test_classified(self):
        result=check_probe_with_maintenance(self.log,self.trace)
        self.assertEqual(result["maintenance_allocations"],33)
        self.assertEqual(result["maintenance_vrf_bytes"],4224)
        self.assertEqual(result["qbs_result_vrf_bytes"],4312)

    def test_missing_repair(self):
        index=next(i for i,r in enumerate(self.rows) if r["source"]=="3")
        self.rows.pop(index);self.write()
        with self.assertRaises(ValueError):check_probe_with_maintenance(self.log,self.trace)

    def test_duplicate_actual(self):
        self.rows.insert(1,dict(self.rows[0]));self.write()
        with self.assertRaises(ValueError):check_probe_with_maintenance(self.log,self.trace)

    def test_fault_commit_rejected(self):
        row=next(r for r in self.rows if r["arch_seq"]=="12" and r["source"]=="3")
        self.rows.append(dict(row,source="4"));self.write()
        with self.assertRaises(ValueError):check_probe_with_maintenance(self.log,self.trace)

    def test_wrong_writer_rejected(self):
        next(r for r in self.rows if r["source"]=="4")["source"]="0"
        self.write()
        with self.assertRaises(ValueError):check_probe_with_maintenance(self.log,self.trace)

    def test_valid(self):
        self.test_classified()

    def test_missing_real_allocation(self):
        self.rows.pop(0);self.write()
        with self.assertRaises(ValueError):check_probe_with_maintenance(self.log,self.trace)


if __name__=="__main__":unittest.main()
