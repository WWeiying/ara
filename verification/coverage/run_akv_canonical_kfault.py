"""Prepare/verify one complete frozen-image 480s phase; parallel phases allowed."""
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from types import ModuleType

import preflight_akv_canonical_kfault as p
import preflight_akv_canonical_kfault_split as split
import run_vfirst_long_mask as inherited

life, require = inherited.life, p.need
NAME = 'akv_canonical_kfault_pair'
PRE = life.OUT/'akv-canonical-kfault-split-preflight-agent-20261008-02/preflight.json'
PRE_SHA = '71427e0f644bcbdef97d22a0157bcebad7787c5a3f5568cf16e52c5ccf7603ee'
ELF = PRE.parent/'phase0/dut.elf'
BUDGET = 480
PROBE = Path(__file__).with_name('akv_canonical_kfault_probe.tcl')
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine.i_read_engine'
PROBE_NAMES = ('clk_i', 'rst_ni', 'en_ld_st_translation_i', 'plan_state_q',
    'range_valid_i', 'range_ready_o', 'range_vaddr_i', 'range_bytes_i', 'range_tag_i',
    'mmu_req_o', 'mmu_vaddr_o', 'mmu_valid_i', 'mmu_paddr_i',
    'mmu_exception_valid_i', 'mmu_exception_i', 'physical_check_valid_o',
    'physical_check_addr_o', 'physical_range_allowed_i', 'planner_fault_event',
    'planner_fault_kind', 'planner_fault_vaddr', 'planner_fault_tag', 'fault_pending_q',
    'fault_kind_o', 'fault_vaddr_o', 'fault_mmu_exception_o',
    'fault_valid_o', 'fault_ready_i', 'burst_fifo_count_q', 'range_fifo_count_q',
    'response_drain_q', 'axi_ar_valid_o', 'axi_ar_ready_i', 'axi_ar_o.addr',
    'axi_r_valid_i', 'axi_r_ready_o', 'axi_r_i.last', 'axi_r_i.resp',
    'completion_valid_o', 'completion_ready_i', 'ar_stalled_q',
    'planner_fault_mmu_exception', 'response_fault_event')


def historical_gate():
    base = life.OUT/'scalar-entropy64-offline-admitted788-agent-20261008-01'
    manifest_path = base/'admission-manifest.json'
    manifest_sha = 'cf59a7fd898c33493f662b247448d52642b694a6cce68785e938f20112d12641'
    manifest = life.read_bound(manifest_path,manifest_sha)
    ledger_path = base/'combined-inputs.txt'
    ledger_sha = 'b94f9d42aee1c1bd8a93644e0b0efb43bd60b158949d96a8db873e90dbedb08f'
    require(manifest['coverage_admitted'] is True and life.digest(ledger_path) == ledger_sha
        and manifest['output_pins'][str(ledger_path)] == ledger_sha, 'Pinned admitted788 dedup ledger')
    ledger = ledger_path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 789 and not any(NAME in row for row in ledger), 'Distinct new software fixture')
    require(any('/gap71_akv_fault/' in row for row in ledger)
        and any('sv39-fault-alternating' in row for row in ledger)
        and not any('gap71-canonical' in row for row in ledger), 'Exact historical comparison cases')
    history = life.OUT/'closure92-current-20261005-01/results/gap71_akv_fault/summary.json'
    prior = json.loads(history.read_text())
    require(len(prior) == 1 and prior[0]['elapsed_s'] == 347.675922696013
        and prior[0]['status'] == 'PASS', 'Matched single-phase timing, not a new benchmark')
    refs = [manifest_path,ledger_path,history,p.ROOT/'apps/common/gap71_data.h',
        p.ROOT/'verification/coverage/preflight_sv39_fault_alternating771.py',
        life.OUT/'gap71-canonical-qbs-positive779-failure-agent-20261008-02.json']
    return dict(population_for_dedup_only=788, proposed_addresses=[hex(a) for a in p.ADDRESSES],
        old_AKV_K_fault_address='0x40002080', ordinary_RVV_alternating_not_AKV_owner=True,
        canonical_QBS_functional_failure_not_reused=True, matched_single_phase_wall_seconds=prior[0]['elapsed_s'],
        policy='Two independent480s phases; unchanged5680-word checks, retry and release. No numeric gain prediction.'), p.h.pins(refs)


def elf_path(phase):
    require(type(phase) is int and phase in (0,1), 'Exact phase')
    return PRE.parent/('phase%d/dut.elf'%phase)


def command(out, phase=0):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(elf_path(phase)), '+TESTCASE='+NAME+'_phase%d'%phase,
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'), '+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '+AKV_PERF', '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out/'code.vdb'),
        '-cm_name', NAME+'_phase%d'%phase, '-ucli', '-do', str(PROBE)]


def preflight_gate(pre):
    require(pre['status'] == 'AKV_CANONICAL_KFAULT_SPLIT_HOST_SPIKE_PASS_NOT_DUT'
        and pre['parent_seal'] == split.PARENT_SHA and pre['host_words'] == 12288
        and pre['VCS_budget_per_phase'] == BUDGET and pre['EDA_launched'] is False
        and pre['no_checks_removed'] is True and len(pre['phases']) == 2, 'Exact software-only split contract')
    for i,phase in enumerate(pre['phases']):
        require(phase['index'] == i and phase['address'] == hex(p.ADDRESSES[i])
            and phase['trace']['status'] == 'SOFTWARE_REFERENCE_PASS_NOT_AKV_EXECUTION'
            and phase['trace']['compared_words'] == 5680 and phase['trace']['traps'] == 2
            and 0 < phase['trace']['retired'] < 150000
            and phase['dut']['elf'] == str(elf_path(i))
            and life.digest(elf_path(i)) == phase['dut']['sha256'], 'Full phase contract/custom ELF')


def prepare(out, phase=0, existing=False):
    import collect_akv_canonical_kfault as collector
    require(out.parent == life.OUT and out.resolve() == out and
        (out.is_dir() if existing else not out.exists()), 'Fresh run / explicit existing terminal')
    pre = life.read_bound(PRE, PRE_SHA); preflight_gate(pre)
    pins = dict(pre['input_pins'])
    for item in pre['phases']: pins = life.merge_pins(pins,item['pins'])
    dedup, historical_pins = historical_gate(); pins = life.merge_pins(pins,historical_pins)
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == inherited.IMAGE_SHA, 'Frozen image66')
    require('sim_l2_mb=2' in life.read_bound(inherited.COMPILE, inherited.COMPILE_SHA)['command'], 'Frozen 2MiB')
    pins = life.merge_pins(pins, image['image'])
    fixed = {PRE:PRE_SHA, life.PLAN:life.PLAN_SEAL, inherited.COMPILE:inherited.COMPILE_SHA, PROBE:life.digest(PROBE)}
    pending, seen = [p, split, inherited, collector], set()
    while pending:
        module = pending.pop()
        if id(module) in seen: continue
        seen.add(id(module)); file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and life.ROOT/'verification' in path.parents:
                fixed[path] = life.digest(path)
                pending.extend(v for v in vars(module).values() if isinstance(v, ModuleType))
    for name in ('run_akv_canonical_kfault.py', 'test_akv_canonical_kfault_run_collect.py'):
        path = Path(__file__).with_name(name); fixed[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(k):v for k,v in fixed.items()}); life.check(pins)
    return dict(schema='AKV_CANONICAL_KFAULT_SPLIT_RUN_V1', output=str(out), case=NAME+'_phase%d'%phase,phase=phase,
        command=command(out,phase), timeout_s=BUDGET, pins=pins, preflight_seal=PRE_SHA,
        elf_sha256=pre['phases'][phase]['dut']['sha256'], image_sha256=inherited.IMAGE_SHA,
        old_image_files_checked=66, probe_scope=SCOPE, probe_objects=list(PROBE_NAMES),
        physical_RAM_bytes=0x200000, addresses=[hex(p.ADDRESSES[phase])],
        qualification_required='Exact custom owner/PC/tval; all5680 words/VRF/CSR/guards; K retry/loads/release; complete preedge fault/PMA/AXI proof',
        software_reference_retired=pre['phases'][phase]['trace']['retired'], automatic_retry=False, coverage_admitted=False,
        historical_dedup_and_budget=dedup,
        admission_performed=False, RTL_modified=False, simulator_exit_is_not_functional_pass=True,
        authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED',
        parallel_allowed=True, systemd_policy=dict(RuntimeMaxSec=540, TimeoutStopSec=10, KillMode='control-group'))


def invoke_run(out, manifest):
    phase = manifest['phase']
    require(manifest['command'] == command(out,phase) and manifest['timeout_s'] == BUDGET,
        'Exact bounded command')
    require(not out.exists(), 'No retry / fresh output')
    life.check(manifest['pins']); out.mkdir(); life.save(out/'manifest.json', manifest)
    process = None; start = time.monotonic()
    try:
        with (out/'console.log').open('x') as log:
            process = subprocess.Popen(manifest['command'], cwd=out, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
            life.save(out/'started.json', dict(pid=process.pid, process_group=process.pid,
                launcher_pid=os.getpid(), budget_s=BUDGET, command=manifest['command'],
                input_elf=str(elf_path(phase)), elf_sha256=manifest['elf_sha256'],
                image=str(life.IMAGE), image_sha256=manifest['image_sha256']))
            code = process.wait(timeout=BUDGET)
        require(code == 0, 'Nonzero native exit')
        life.check(manifest['pins'])
        life.save(out/'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=code, timeout=False, pid=process.pid,
            wall_seconds=time.monotonic()-start, coverage_admitted=False))
    except BaseException as error:
        if process is not None and process.poll() is None:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
        life.save(out/'simulation-status.json', dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED',
            reason=str(error), returncode=process.returncode if process else None,
            timeout=isinstance(error, subprocess.TimeoutExpired),
            wall_seconds=time.monotonic()-start, coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare','verify','run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase',type=int,choices=(0,1),required=True)
    parser.add_argument('--seal'); parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require(bool(args.seal) == (args.mode != 'prepare'), 'Exact prepared seal')
    require(args.parent_authorized == (args.mode == 'run'), 'Separate launch approval')
    out = args.output.resolve(); manifest = prepare(out,args.phase)
    record = out.with_name(out.name+'.prepared.json')
    if args.mode == 'prepare':
        require(not record.exists(), 'Preserve prepared evidence'); life.save(record, manifest)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), pins=len(manifest['pins']))), flush=True)
    else:
        require(life.read_bound(record, args.seal) == manifest, 'Prepared drift')
        if args.mode == 'verify': print('CHECK_PASS_NO_VCS')
        else: invoke_run(out, manifest)


if __name__ == '__main__': main()
