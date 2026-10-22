#!/usr/bin/env python3
"""Reuse three previously accepted Sv39/indexed-restart controls unchanged."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run as base


def main():
    old=HERE.parent/'indexed_fault_prefix_20261018'
    records=[('pilot_inputs01','pilot_current01','p1_o1_c0_s1'),
             ('pilot_inputs01','pilot_current01','p10_o1_c0_s1'),
             ('position14_inputs01','position14_current01','p14_o1_c0_s1')]
    out=HERE/'memory_admitted02';out.mkdir(exist_ok=False)
    programs={};pins={}
    for prepared,measured,name in records:
        directory=old/prepared/name
        receipt=old/measured/name/'result.json'
        result=json.loads(receipt.read_text())
        assert result['status']=='PASS' and base.sha(directory/'soc.elf')==result['elf_sha256']
        ref=directory/'reference.json';reference=json.loads(ref.read_text())
        assert reference['status']=='SPIKE_PASS_NOT_DUT' and reference['faults']==1
        assert base.sha(directory/'spike.elf')==reference['elf_sha256']
        for path in (receipt,ref,directory/'spike.elf',directory/'soc.elf',old/prepared/'source-pins.json'):
            pins[str(path)]=base.sha(path)
        # Reuse the sources sealed with the accepted ELF, not later live edits.
        frozen={base.sha(path):path for path in (old/prepared/'inputs').iterdir() if path.is_file()}
        for origin,digest in json.loads((old/prepared/'source-pins.json').read_text()).items():
            assert digest in frozen,origin
            pins[str(frozen[digest])]=digest
        programs[name]=dict(directory=str(directory),elf_sha256=result['elf_sha256'],
            pass_markers=['SYSTEM_PASS faults=0000000000000001 errors=0000000000000000'])
    base.save(out/'prepared.json',dict(programs=programs,pins=pins,files={},
        scope='Three unchanged Sv39 indexed-overlap fault/restart controls, prefixes1/10/14. Not Linux or new FPGA acceptance'))
    print('ADMITTED_THREE_EXISTING_SYSTEM_CONTROLS_NOT_DUT')


if __name__=='__main__':main()
