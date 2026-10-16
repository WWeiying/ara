#!/usr/bin/env python3
"""Bounded MMU-netlist/cache-RTL reproduction; never accesses the board."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import struct
from run_inval_read_collision import extract
from analyze_loader_stall import inspect_task_capture


def capture_fixture(capture, loader, out):
    report, summary = inspect_task_capture(capture, loader.read_bytes())
    target = next(item for item in report['pages'] if item['label'] == 'target_page')
    root = int(target['page_walk'][0]['pa'], 16) & ~4095
    # The address and timing of AW are a controlled stimulus, NOT a hardware
    # measurement. Any external invalidation exercises the defective arbitration.
    words = [int(target['requested_va'], 16), root >> 12, int(target['pa'], 16), 0x90000000]
    for entry in target['page_walk']:
        address = int(entry['pa'], 16) & ~31
        matches = [row for row in report['pte_cache_lines'] if int(row['pa'], 16) == address]
        if len(matches) != 1:
            raise ValueError('Missing captured PTE cache line')
        data = bytes.fromhex(matches[0]['data'])
        if len(data) != 32 or not any(int(row['pa'], 16) == address and
                                     row['data'] == matches[0]['data'] for row in report['reads']):
            raise ValueError('Cache line not present in raw reads')
        if struct.unpack_from('<Q', data, int(entry['pa'], 16) & 31)[0] != int(entry['pte'], 16):
            raise ValueError('PTE changed between reads')
        words.extend([address, *struct.unpack('<4Q', data)])
    if len(set(words[4::5])) != 3:
        raise ValueError('Test requires three distinct page-table cache lines')
    summary.update(aw_stimulus='controlled_address_and_timing_not_captured',
                   capture_report_sha256=hashlib.sha256((capture/'report.json').read_bytes()).hexdigest())
    (out/'fixture_summary.json').write_text(json.dumps(summary, indent=2))
    path = out/'capture.hex'
    path.write_text(''.join(f'{word:016x}\n' for word in words))
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--netlist',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True)
    p.add_argument('--xpm',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--candidate',action='store_true')
    p.add_argument('--capture',type=Path,help='Verified read_stalled_task --context evidence')
    p.add_argument('--loader',type=Path,help='Original loader ELF required with --capture')
    a=p.parse_args()
    root=a.package.resolve(); out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    if a.capture and not a.loader:
        p.error('--capture requires --loader')
    fixture = capture_fixture(a.capture, a.loader, out) if a.capture else None
    core=root/'rtl/cva6/core'; common=root/'rtl/common_cells'; axi=root/'rtl/axi'
    top=(core/'cva6.sv').read_text(); cache=(core/'cache_subsystem/wt_cache_subsystem.sv').read_text()
    types='// Frozen CVA6 types; Solderpad Hardware License 0.51.\n'
    for name in ('icache_req_t','icache_rtrn_t','dcache_req_i_t','dcache_req_o_t'):
        types+=extract(top,name)
    for name in ('dcache_inval_t','dcache_req_t','dcache_rtrn_t'):
        types+=extract(cache,name)
    (out/'collision_types.svh').write_text(types)
    adapter=core/'cache_subsystem/wt_axi_adapter.sv'
    if a.candidate:
        old='axi_rd_rdy        = ~invalidate;'; source=adapter.read_text()
        if source.count(old)!=1: raise ValueError('Candidate anchor mismatch')
        adapter=out/'wt_axi_adapter_candidate.sv'
        adapter.write_text(source.replace(old,'axi_rd_rdy        = ~invalidate & ~inval_valid_i;'))
    files=[common/'src/cf_math_pkg.sv',axi/'src/axi_pkg.sv']
    files += [core/'include'/n for n in ('config_pkg.sv','cv64a6_imafdcv_sv39_config_pkg.sv',
        'riscv_pkg.sv','ariane_pkg.sv','build_config_pkg.sv','wt_cache_pkg.sv')]
    files += [common/'src'/n for n in ('lzc.sv','rr_arb_tree.sv','fifo_v3.sv','lfsr.sv','exp_backoff.sv')]
    files += [root/'rtl/ara/hardware/src/axi_inval_filter.sv',core/'cva6_fifo_v3.sv',core/'axi_shim.sv',adapter]
    files += [core/'cache_subsystem'/n for n in ('wt_dcache.sv','wt_dcache_ctrl.sv','wt_dcache_missunit.sv',
        'wt_dcache_wbuffer.sv','wt_dcache_mem.sv')]
    files += [a.xpm.resolve(),root/'rtl/tech_cells_generic/src/fpga/tc_sram_xilinx.sv']
    # The frozen Xilinx implementation always uses MEM_INIT_PARAM="0";
    # make the simulation-only SimInit assertion agree with that fixed hardware.
    wrapper_source=core.parent/'common/local/util/tc_sram_wrapper.sv'
    wrapper_text=wrapper_source.read_text()
    if wrapper_text.count('.SimInit(SimInit)')!=1: raise ValueError('RAM init anchor mismatch')
    wrapper=out/'tc_sram_wrapper_sim.sv'
    wrapper.write_text(wrapper_text.replace('.SimInit(SimInit)', '.SimInit("zeros")'))
    files += [wrapper]+[core.parent/'common/local/util'/n for n in ('sram.sv','sram_cache.sv')]
    files += [a.netlist.resolve(),Path(__file__).with_name('loader_cache_chain_tb.sv').resolve()]
    manifest={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files+[wrapper_source]+list(a.models.resolve().glob('*.v'))}
    (out/'sources.json').write_text(json.dumps(manifest,indent=2))
    command=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-top','loader_cache_chain_tb',
             '-top','glbl','+libext+.v','-y',str(a.models.resolve())]
    command += ['+incdir+'+str(d) for d in (common/'include',axi/'include',core/'include',out)]
    with (out/'compile.log').open('w') as log:
        subprocess.run(command+list(map(str,files))+['-o','simv','-Mdir=csrc'],cwd=out,
                       stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
    results=[]
    for beat,enable in ((-1,1),(0,1),(1,1),(2,1),(3,1),(3,0)):
        path=out/f'run_{beat}_{enable}.log'
        with path.open('w') as log:
            fixture_args = [f'+fixture={fixture}'] if fixture else []
            run=subprocess.run([str(out/'simv'),'-no_save',f'+collide={beat}',f'+filter_enable={enable}']+fixture_args,
                cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=60)
        text=path.read_text()
        result={'beat':beat,'filter_enable':enable,'passed':run.returncode==0 and
                'CACHE_CHAIN_PASS' in text and 'Fatal:' not in text}
        results.append(result); print(json.dumps(result),flush=True)
    (out/'results.json').write_text(json.dumps(results,indent=2))
    return 0 if all(r['passed'] for r in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
