#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('prep',HERE/'prepare.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
u=p.u


def main():
    archive=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8')
    expected='266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754'
    assert u.sha(archive)==expected
    assert u.sha(p.CASE/'original_rebuilt.elf')==expected
    gcc=json.loads((p.OLD/'soc'/('alias_v8_e16m8_prefix682.compile.log.command.json')).read_text())[0]
    # Archived Linux ELF is stripped: use unique complete instruction sequences.
    old=re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s+',
                   (HERE/'run01/archive_dis.log').read_text(),re.M)
    blocks=re.split(r'^[0-9a-f]+ <([^>]+)>:\n',
                    (HERE/'run01/soc_final_dis.log').read_text(),flags=re.M)
    new={blocks[i]:re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s+',blocks[i+1],re.M)
         for i in range(1,len(blocks),2)}
    helpers=['capacity']+['op_'+str(i) for i in range(10)]
    assert all(sum(old[i:i+len(new[h])]==new[h] for i in range(len(old)-len(new[h])+1))==1 for h in helpers)
    for name,words in new.items():
        if name in helpers:continue
        for w in words:
            op=int(w,16)&127
            assert not (len(w)==8 and op in (0x43,0x47,0x4b,0x4f,0x53)),(name,w)
    orig_pins=json.loads((HERE/'run01/input_pins.json').read_text())
    assert all(u.sha(n)==h for n,h in orig_pins.items())
    flow=json.loads((HERE/'host_flow01/result.json').read_text())
    assert flow['status']=='HOST_ACTUAL_SOURCE_CALL_FLOW_EQUIVALENT'
    ref=json.loads((HERE/'run01/result.json').read_text())
    fp50=p.OLD.parent/'fp_alias50_vcs_m6_realmarkers01/prepared01'
    complete=json.loads((fp50/'complete.json').read_text())
    csv_path=fp50/'replay/tests/alias_v8_e16m8_prefix50/trace_summary.json'
    assert u.sha(csv_path)==complete['evidence_pins'][str(csv_path)]
    trace=json.loads(csv_path.read_text())
    fp_rate=trace['retire_count']/complete['results'][0]['elapsed_s']
    ref['fp50_calibration']=dict(retirements=trace['retire_count'],elapsed_s=complete['results'][0]['elapsed_s'],
           retired_per_second=fp_rate,nominal_s=ref['retired']/fp_rate,margin20_s=1.2*ref['retired']/fp_rate)
    allpins=dict(orig_pins)
    for f in list(HERE.rglob('*'))+[archive,p.CASE/'original_rebuilt.elf',fp50/'complete.json',csv_path]:
        if f.is_file():allpins[str(f)]=u.sha(f)
    u.save(HERE/'pins.json',allpins)
    u.save(HERE/'READY.json',dict(status='PREPARED_SCALAR_OPTIMIZATION_HOST_REFERENCE_COST_NOT_DUT_ENTRY',
       scope='All original first682 calls/681 predecessors; not full17920 parent or Linux ABI',
       pins_sha256=u.sha(HERE/'pins.json'),original_linux_elf_sha256=expected,
       soc_elf_sha256=u.sha(HERE/'run01/soc.elf'),spike_elf_sha256=u.sha(HERE/'run01/spike.elf'),
       full_helper_bytes_match_original_linux=True,source_order_host_equivalent=True,
       host_exhaustive_bytes=11173888,host_negative_pairs=6,reference=ref,
       remaining='Independent transformation review and exact relocated-PC packed-oracle worker/Host needed before DUT. No new full dynamic reference audit performed.',
       DUT_launched=False))
    print((HERE/'READY.json').read_text())


if __name__=='__main__':main()
