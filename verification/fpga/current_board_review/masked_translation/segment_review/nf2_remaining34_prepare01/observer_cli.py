#!/usr/bin/env python3
"""One group per process: future bounded CSV validation, never a DUT launcher."""
import argparse
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from scope import HERE,read,save,sha,require
import csv_check

def main():
    p=argparse.ArgumentParser();p.add_argument('--group',required=True);p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    inv=read(HERE/'source_manifest.json');groups={g['id']:g for g in inv['groups']}
    require(a.group in groups and not a.out.exists(),'Exact group and fresh output required')
    root=HERE/a.group/'reference02';proof=read(root/'source_proof.json')
    require(sha(root/'soc.elf')==proof['elfs']['soc']['sha256'],'Compiled SoC ELF drift')
    csv_check.configure(groups[a.group]['cases'])
    code={str(int(m[1],16)):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
         (root/'soc.dis').read_text(),re.M)}
    result=csv_check.analyze(a.csv,read(root/'soc.symbols.json'),code)
    result['group']=a.group;result['CSV_sha256']=sha(a.csv)
    save(a.out,result);return int(result['status']!='NF2_CSV_ORACLE_PASS')

if __name__=='__main__':raise SystemExit(main())
