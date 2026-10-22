#!/usr/bin/env python3
"""Admit the independently checked packed319 ELF to the explicit-image runner."""
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run as base


def main():
    source=HERE/'packed/out319_04'
    ledger=source/'result.json'
    assert base.sha(ledger)=='c0f8eb71aff5295e40b05812de9d74dda686090dc561bd41d1f4c3761234af17'
    data=json.loads(ledger.read_text())
    assert data['bound']==319 and data['reference']['status']=='SPIKE_PASS_NOT_DUT'
    pins={str(ledger):base.sha(ledger)}
    for group in ('pins','files'):
        for path,digest in data[group].items():assert base.sha(path)==digest,path
        pins.update(data[group])
    audit=source/'trace_audit.json';record=json.loads(audit.read_text())
    assert record['actual_calls']==319 and record['retired_to_exit']==332948
    pins[str(audit)]=base.sha(audit)
    out=HERE/'packed319_admitted01';out.mkdir(exist_ok=False)
    case=out/'packed319';case.mkdir()
    shutil.copyfile(source/'soc.elf',case/'soc.elf')
    assert base.sha(case/'soc.elf')=='1371b771ba6b2addb92d694b122891b9f6cab3aa079e347dd67d7a2acd4e9015'
    base.save(out/'prepared.json',dict(programs=dict(packed319=dict(directory=str(case),
        elf_sha256=base.sha(case/'soc.elf'),pass_markers=['RVV_FP_COMPARE_PASS sew=32 cases=319 errors=0','BOARD_REPLAY_PASS'])),
        files={str(case/'soc.elf'):base.sha(case/'soc.elf')},pins=pins,
        scope='Original319 vector-helper history and exact allowed-output scalar oracle; optimized scalar timing; no Linux scheduler or full17920 acceptance'))
    print('ADMITTED_ORIGINAL319_SCALAR_PACKED_NOT_DUT',flush=True)


if __name__=='__main__':main()
