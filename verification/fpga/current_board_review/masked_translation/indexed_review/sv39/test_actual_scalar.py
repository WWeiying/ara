#!/usr/bin/env python3
"""Read-only decoder check against completed extended8 DUT CSV; not NF7 DUT evidence."""
import csv
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import csv_oracle
from support import HERE,EXT,save
import reference as ref


def main():
    path=EXT/'candidate02_extended8_02/run/tests/extended8/commit_trace.csv'
    regs={i:0 for i in range(32)}; counts={'read':0,'write':0}; shifted=0
    with path.open() as stream:
        rows=csv.DictReader(stream)
        ref.base.require(rows.fieldnames==csv_oracle.FIELDS,'Unexpected actual CSV header')
        for row in rows:
            if row['event']!='retire': continue
            trap=int(row['trap'])
            if not trap:
                access=csv_oracle.scalar_access(row,regs)
                if access:
                    kind,address,_,_=access; counts[kind]+=1; shifted+=address%8!=0
                if int(row['rd']): regs[int(row['rd'])]=int(row['rd_wdata'],16)
            regs[0]=0
    ref.base.require(all(counts.values()) and shifted,'Actual decode coverage missing')
    save(HERE/'actual_scalar01.json',dict(status='ACCEPTED_EXTENDED8_SCALAR_DECODER_PASS_NOT_NF7_DUT',
         counts=counts,shifted_accesses=shifted,input=str(path),input_sha256=ref.base.sha(path),
         decoder_sha256=ref.base.sha(Path(csv_oracle.__file__)),VCS_started=False))
    print('ACCEPTED_EXTENDED8_SCALAR_DECODER_PASS_NOT_NF7_DUT',counts,shifted)


if __name__=='__main__': main()
