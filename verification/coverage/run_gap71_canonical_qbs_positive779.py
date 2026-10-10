"""Prepare one600s frozen QBS canonical fault run; separate launch authorization."""
import argparse
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace

import preflight_gap71_canonical779 as p
import run_vfirst_long_mask as inherited

life, require = inherited.life, p.need
NAME = 'gap71_canonical_qbs_positive779'
PRE = life.OUT / 'gap71-canonical779-qbs-positive-preflight-agent-20261008-03/preflight.json'
PRE_SHA = '2a73b8a7ee19b477288f6a6f1b021ca732b23e4917030a986ef31e329a50de39'
ELF = PRE.parent / 'input.elf'
ELF_SHA = 'a3c1d05bdf97312cdd8974f482e1d498a55fe150ec3bea097b2131f035693ec3'
BOOK = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
BUDGET = 600
PROBE = Path(__file__).with_name('gap71_canonical_qbs_positive779_probe.tcl').resolve()
PROBE_NAMES = ('clk_i', 'rst_ni', 'en_ld_st_translation_i', 'plan_state_q',
    'range_valid_i', 'range_ready_o', 'range_vaddr_i', 'range_bytes_i',
    'mmu_req_o', 'mmu_vaddr_o', 'mmu_valid_i', 'mmu_paddr_i',
    'mmu_exception_valid_i', 'mmu_exception_i', 'physical_check_valid_o',
    'physical_check_addr_o', 'physical_range_allowed_i', 'planner_fault_event',
    'planner_fault_kind', 'planner_fault_vaddr', 'fault_pending_q',
    'fault_kind_o', 'fault_vaddr_o', 'fault_mmu_exception_o',
    'fault_valid_o', 'fault_ready_i', 'burst_fifo_count_q', 'range_fifo_count_q',
    'response_drain_q', 'axi_ar_valid_o', 'axi_ar_ready_i', 'axi_ar_o.addr',
    'axi_r_valid_i', 'axi_r_ready_o', 'axi_r_i.last', 'axi_r_i.resp',
    'completion_valid_o', 'completion_ready_i', 'ar_stalled_q',
    'planner_fault_mmu_exception', 'response_fault_event')


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), '+QBS_PERF',
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME,
        '-ucli', '-do', str(PROBE)]


def validate(pre):
    require(pre['status'] == 'CANONICAL_GAP71_SOFTWARE_PREFLIGHT_PASS_NOT_DUT_QUALIFIED'
        and pre['family'] == 'qbs' and pre['window'] == '0x1555400000'
        and pre['fault_address'] == '0x1555402080' and pre['formal_population'] == 779
        and pre['formal_manifest_sha256'] == p.BASE_SHA, 'Exact positive QBS/779 fixture')
    require(pre['trace'] == dict(status='PASS', retired=79002, full_compared_words=4688,
        traps=2, actual_execution='S/Sv39 payload; M handler/restore', custom_instructions_executed=0,
        scope='Software reference only; no accelerator/MMU internal condition claim'), 'Exact software-only trace')
    require(pre['uart']['checks'] == 160 and pre['uart']['backend'] == 'software-reference'
        and pre['host_compared_words'] == 12288 and pre['host_numeric_words'] == 64,
        'Full host/Spike preflight')
    require(pre['EDA_launched'] is False and pre['RTL_modified'] is False
        and pre['custom_instruction_execution_verified'] is False
        and pre['internal_drain_verified'] is False, 'No premature DUT qualification')
    require(pre['artifacts']['dut']['elf'] == str(ELF)
        and pre['artifacts']['dut']['sha256'] == ELF_SHA
        and pre['artifacts']['dut']['metadata']['software_reference'] is False, 'Native custom ELF only')


def probe_contract():
    return dict(plusargs=['+QBS_PERF'], probe=str(PROBE),
        scope='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_read_engine',
        objects=list(PROBE_NAMES), wave='qbs-canonical-focused.vpd',
        maximum_wave_bytes=64*1024*1024,
        wave_policy='Complete start-to-terminal VPD required; missing/truncated/over64MiB rejects. UCLI checks63MiB every100ns and aborts, never resumes without probe.',
        translation='Two QBS_PERF rows: fault translations>0; retry read_ranges=translations=3, payload_bytes=452',
        fault='CSR mcause=13 and mtval=0x1555402080; fault response then identical custom instruction retry',
        PMA='Cycle probe required: exact fault vaddr/MMU exception implies physical_check_valid_o=0 and no target AR; source proof alone insufficient',
        drain='Cycle probe required: fault_valid_o == fault_pending_q && burst_fifo_count_q==0 && !ar_stalled_q; response drain and AR/Rlast conservation; owner gates plus successful retry/RVV recovery',
        limitations='Probe records no payload data. Capacity abort is failure, never qualification.',
        owner_oracle='audit_gap71_custom: custom_write_lifetimes, runtime_traces owner/CSR/PTE/VRF gates, runtime_perf',
        recovery='Independent full v10 input and v11 doubled16uint64 writes plus preserved remainder; full memory readback',
        collector_status='REQUIRES_PRIVATE_RECOVERY_ADAPTER: unchanged runtime_traces rejects added recovery writers; never bypass owner gates',
        reference_policy='Software fallback is not custom native per-instruction reference',
        qualification_required=True, coverage_admitted=False)


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output')
    pre = life.read_bound(PRE, PRE_SHA); validate(pre)
    pins = {}
    for key in ('input_pins', 'source_pins', 'tool_pins', 'link_pins', 'output_pins'):
        pins = life.merge_pins(pins, pre[key])
    life.check(pins)
    book = life.read_bound(BOOK, BOOK_SHA)
    for name in p.RTL:
        path = str(p.ROOT / name)
        require(pins[path] == book[path], 'Frozen producer/probe source mismatch')
    p.driver_gate((p.ROOT / p.RTL[0]).read_text())
    base = life.read_bound(p.BASE / 'admission-manifest.json', p.BASE_SHA)
    ledger_path = p.BASE / 'combined-inputs.txt'
    ledger = ledger_path.read_text().splitlines()
    require(base['coverage_admitted'] is True and len(ledger) == len(set(ledger)) == 780,
        'Exact admitted779 prefix')
    require(life.digest(ledger_path) == pre['baseline_ledger_sha256'] == base['output_pins'][str(ledger_path)], '779 ledger pin')
    bits_path = p.BASE / 'combined-bits.json'
    bits = life.read_bound(bits_path, base['output_pins'][str(bits_path)])
    require(bits['tests'] == ledger[1:] and set(bits['metrics']) == {'line', 'cond', 'branch', 'fsm'}
        and {k: len(v) for k,v in bits['metrics'].items()} == dict(line=1892, cond=2023, branch=2155, fsm=92), 'Full779 bitmap prefix')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(plan['image']) == 66 and plan['image'][str(life.IMAGE)] == inherited.IMAGE_SHA, 'Frozen image66')
    require('sim_l2_mb=2' in life.read_bound(inherited.COMPILE, inherited.COMPILE_SHA)['command'], 'Frozen 2MiB')
    pins = life.merge_pins(pins, plan['image'])
    fixed = {PRE: PRE_SHA, BOOK: BOOK_SHA, life.PLAN: life.PLAN_SEAL,
        PROBE: life.digest(PROBE),
        inherited.COMPILE: inherited.COMPILE_SHA, p.BASE / 'admission-manifest.json': p.BASE_SHA,
        ledger_path: pre['baseline_ledger_sha256'], bits_path: base['output_pins'][str(bits_path)]}
    for name, sha in bits['design'].items():
        path = Path(ledger[0]) / 'snps/coverage/db' / name
        require(base['input_pins'][str(path)] == sha, 'Compiled design pin')
        fixed[path] = sha
    modules, seen = [p, inherited], set()
    while modules:
        module = modules.pop()
        if id(module) in seen: continue
        seen.add(id(module)); file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and life.ROOT / 'verification' in path.parents:
                fixed[path] = life.digest(path)
                modules.extend(v for v in vars(module).values() if isinstance(v, ModuleType))
    for name in (Path(__file__).name, 'test_run_gap71_canonical_qbs_positive779.py'):
        path = Path(__file__).with_name(name); fixed[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(k): v for k,v in fixed.items()}); life.check(pins)
    return dict(schema='GAP71_CANONICAL_QBS_POSITIVE779_RUN_FOCUSED', output=str(out),
        case=NAME, command=command(out), pins=pins, timeout_s=BUDGET,
        baseline=779, baseline_seal=p.BASE_SHA, preflight_seal=PRE_SHA,
        elf_sha256=ELF_SHA, image_sha256=inherited.IMAGE_SHA, software_reference_retired=79002,
        probes=probe_contract(), automatic_retry=False, no_FSDB=True,
        coverage_admitted=False, admission_performed=False, RTL_modified=False,
        simulator_exit_is_not_functional_pass=True,
        authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED',
        systemd_policy=dict(RuntimeMaxSec=660, TimeoutStopSec=10, KillMode='control-group'))


def invoke_run(out, manifest):
    worker = inherited.worker
    namespace = dict(worker.run.__globals__, BUDGET=BUDGET, PRE=ELF.parent,
        ELF_SEAL=ELF_SHA, IMAGE_SEAL=inherited.IMAGE_SHA,
        preflight=SimpleNamespace(NAME=NAME), command=command)
    FunctionType(worker.run.__code__, namespace, argdefs=worker.run.__defaults__)(out, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true'); args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.seal), 'Prepared seal required')
    require((args.mode == 'run') == args.parent_authorized, 'Separate explicit launch authorization')
    out = args.output.resolve(); manifest = prepare(out)
    record = out.with_name(out.name + '.prepared.json')
    if args.mode == 'prepare':
        require(not record.exists(), 'Preserve prepared record')
        life.save(record, manifest); print('PREPARED_NO_VCS', life.digest(record), len(manifest['pins']))
    else:
        require(life.read_bound(record, args.seal) == manifest, 'Prepared pins/command drift')
        if args.mode == 'verify': print('VERIFY_PASS_NO_VCS')
        else: invoke_run(out, manifest)


if __name__ == '__main__': main()
