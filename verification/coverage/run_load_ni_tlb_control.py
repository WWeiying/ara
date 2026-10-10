"""One760-bound NI/TLB fixture: bounded build, Spike reference, one old VCS run."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import run_gap95_simulation as life
import build_gap98_preflight as build
import collect_gap103_strict as architecture

ROOT, OUT, require = life.ROOT, life.OUT, build.require
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vload_ni_tlb_control.c'
PROBE = ROOT / 'verification/coverage/load_ni_tlb_probe.tcl'
PRE = OUT / 'load-ni-tlb-preflight-760-agent-20261007-01'
RUN = OUT / 'load-ni-tlb-old-image-760-agent-20261007-01'
BASE = OUT / 'qbs-affine-min-scale-offline-admitted-760-agent-20261007-01'
BASE_SHA = '0b4ae9ddf332355cdbb02ff42f237487dd0857fa5872b86916bc5ac40b3b207e'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
SOURCE_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
TEMPLATE = OUT / 'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
LOAD = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.i_load_unit'
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'trap_fail', 'lnt_observed', 'lnt_original_status',
           'lnt_warm', 'lnt_cold', 'lnt_root', 'lnt_mid', 'lnt_leaf', 'lnt_ni_div',
           'lnt_ni_warm_load', 'lnt_ni_control_load', 'lnt_sv_warm_load', 'lnt_sv_cold_load')


def expected(symbols, original):
    return [0x5555555555555555, 0x123456789abcdef0, 0, 0x123456789abcdef0,
            0xfedcba9876543210, (8 << 60) | (symbols['lnt_root'] >> 12), 0x20800, 0, original]


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits), 'Unexpected vector/trap')
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    require([writes.get(symbols['g75_result']), writes.get(symbols['g75_result'] + 4),
             writes.get(symbols['num_failed']), writes.get(symbols['tohost'])] == [14, 0, 0, 1], 'Complete14-check terminal differs')
    original = writes.get(symbols['lnt_original_status'])
    require(original is not None and [writes.get(symbols['lnt_observed'] + 8 * i) for i in range(9)] ==
            expected(symbols, original), 'Independent two-phase values/CSR differ')
    require(not any(0xd0000000 <= address < 0xd0001000 and value is not None
                    for c in commits for address, value in c.memory_accesses), 'Forbidden CTRL write')
    control = [c for c in commits if c.pc == symbols['lnt_ni_control_load']]
    require(len(control) == 1 and control[0].instruction & 0x707f == 0x3003 and
            list(control[0].gpr_writes.values()) == [0], 'CTRL exact readonly load differs')
    ni = [c for c in commits if c.pc in {symbols[k] for k in ('lnt_ni_div', 'lnt_ni_warm_load', 'lnt_ni_control_load')}]
    require([c.pc for c in ni] == [symbols[k] for k in ('lnt_ni_div', 'lnt_ni_warm_load', 'lnt_ni_control_load')] and
            ni[0].instruction & 0xfe00707f == 0x02005033, 'NI instruction sequence differs')
    for table in ('lnt_root', 'lnt_mid', 'lnt_leaf'):
        require(symbols[table] % 4096 == 0, 'Page table alignment differs')
    def pte(address, flags): return ((address >> 12) << 10) | flags
    mapping = {symbols['lnt_root'] + 16: pte(0x80000000, 0xcf),
               symbols['lnt_root'] + 8: pte(symbols['lnt_mid'], 1),
               symbols['lnt_mid']: pte(symbols['lnt_leaf'], 1),
               symbols['lnt_leaf']: pte(symbols['lnt_warm'], 0xc7),
               symbols['lnt_leaf'] + 8: pte(symbols['lnt_cold'], 0xc7)}
    require(all(writes.get(p) == v for p, v in mapping.items()), 'Sv39 mapping differs')
    return architecture.reference_counts(commits, symbols)


def source_pins():
    book = life.read_bound(BUILD / 'build-source-pins.json', SOURCE_SHA)
    rels = ['hardware/src/ara_soc.sv', 'hardware/src/ctrl_registers.sv'] + ['hardware/deps/cva6/' + r for r in (
        'core/load_unit.sv', 'core/load_store_unit.sv', 'core/cva6.sv', 'core/cva6_mmu/cva6_mmu.sv',
        'core/cva6_mmu/cva6_ptw.sv', 'core/store_buffer.sv', 'core/controller.sv', 'core/scoreboard.sv',
        'core/issue_read_operands.sv', 'core/cache_subsystem/wt_dcache_ctrl.sv',
        'core/cache_subsystem/wt_dcache_mem.sv', 'core/cache_subsystem/wt_dcache_missunit.sv',
        'core/include/config_pkg.sv', 'core/include/build_config_pkg.sv',
        'core/include/cv64a6_imafdcv_sv39_config_pkg.sv')]
    pins = {str(ROOT / p): book[str(ROOT / p)] for p in rels}
    pins[str(BUILD / 'build-source-pins.json')] = SOURCE_SHA
    life.check(pins)
    soc = (ROOT / rels[0]).read_text(); ctrl = (ROOT / rels[1]).read_text()
    require("CTRLBase = 64'hD000_0000" in soc and 'cfg.NonIdempotentAddrBase = {UARTBase, CTRLBase};' in soc and
            'cfg.NonIdempotentLength   = {UARTLength, CTRLLength};' in soc, 'Frozen NI region differs')
    require("RegRstVal = '{" in ctrl and 'dram_base_address, exit})' in ctrl and
            re.search(r'DRAMBaseAddr,\s*0\s*\};', ctrl), 'Frozen CTRL exit reset contract differs')
    return pins


def make_command(elf, output):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1', '+PRELOAD=' + str(elf),
        '+TESTCASE=load_ni_tlb_control', '+COMMIT_TOHOST=80001000', '+COMMIT_TRACE=' + str(output / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(output / 'vector_trace.csv'), '-cm', 'line+cond+fsm+tgl+branch',
        '-cm_dir', str(output / 'code.vdb'), '-cm_name', 'load_ni_tlb_control',
        '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000', '-ucli', '-do', str(PROBE)]


def prepare():
    require(not PRE.exists() and not RUN.exists(), 'No overwrite/retry of fixture')
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    bits = life.read_bound(BASE / 'combined-bits.json', base['output_pins'][str(BASE / 'combined-bits.json')])
    require(len(bits['tests']) == len(set(bits['tests'])) == 760, 'Formal760 required')
    row = bits['metrics']['fsm'][LOAD]
    require((row['width'], row['checksum']) == (42, '1874282190') and all(
        not int(row['bits'], 16) & (1 << (41 - i)) for i in (21, 22, 28, 29)), 'Exact fresh760 FSM targets differ')
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66, 'Frozen66 image required')
    pins = life.merge_pins(source_pins(), image['image'])
    pins = life.merge_pins(pins, {str(life.PLAN): life.PLAN_SEAL, str(BASE / 'admission-manifest.json'): BASE_SHA,
        str(BASE / 'combined-bits.json'): base['output_pins'][str(BASE / 'combined-bits.json')]})
    command = json.loads(TEMPLATE.read_bytes())
    require(command.count(str(ROOT / 'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')) == 1,
            'Exact proven scalar compile template required')
    command = [str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(PRE / 'input.elf') if x.endswith('/input.elf') else x for x in command]
    for p in (APP, PROBE, TEMPLATE, Path(__file__).resolve(), Path(__file__).with_name('test_run_load_ni_tlb_control.py'),
        ROOT / 'verification/tests/gap75_start.S', ROOT / 'verification/tests/gap75.ld',
        Path(command[0]), build.LLVM / 'llvm-readelf', build.LLVM / 'llvm-objdump', build.SPIKE,
        Path(life.__file__).resolve(), Path(build.__file__).resolve(), Path(architecture.__file__).resolve()):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    for directory in ('apps/riscv-tests/isa/macros', 'apps/riscv-tests/env', 'apps/common'):
        for p in (ROOT / directory).rglob('*'):
            if p.is_file(): pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins); PRE.mkdir(); life.save(PRE / 'input-pins.json', pins)
    try:
        life.save(PRE / 'compile-command.json', command)
        with (PRE / 'build.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
        elf = PRE / 'input.elf'
        symbols = {n: build._elf_symbol(elf, build.LLVM / 'llvm-readelf', n) for n in SYMBOLS}
        with (PRE / 'input.disasm').open('x') as stream:
            subprocess.run([str(build.LLVM / 'llvm-objdump'), '-d', str(elf)], stdout=stream, timeout=30, check=True)
        spike = [str(build.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
                 '-m0x80000000:0x20000000,0xd0000000:0x1000', '-l', '--log-commits', str(elf)]
        life.save(PRE / 'spike-command.json', spike)
        with (PRE / 'spike.trace').open('x') as stream:
            subprocess.run(spike, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
        commits = build.parse_spike_commits(PRE / 'spike.trace'); counts = validate(commits, symbols)
        require('exception ' not in (PRE / 'spike.trace').read_text(), 'Unexpected architectural exception')
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in PRE.iterdir() if p.is_file()})
        value = dict(status='TWO_PHASE_SPIKE_ARCHITECTURE_AND_STATIC_CTRL_RESET_ORACLE_PASS_NOT_RTL',
            pins=pins, symbols=symbols, counts=counts, software_checks=14, baseline=760, baseline_seal=BASE_SHA,
            input_elf=str(elf), ctrl_device_emulated_by_Spike=False,
            ctrl_scope='Only one readonly exit-register load; frozen reset zero and no CTRL writes.',
            timeout_s=600, targets=dict(scope=LOAD, checksum='1874282190', width=42, raw_indices=[21, 22, 28, 29]),
            measured_increment=None, coverage_admitted=False, rtl_changed=False)
        life.save(PRE / 'preflight.json', value)
        pins = life.merge_pins(pins, {str(PRE / 'preflight.json'): life.digest(PRE / 'preflight.json')})
        manifest = dict(case='load_ni_tlb_control', pins=pins, command=make_command(elf, RUN), timeout_s=600,
            preflight_seal=life.digest(PRE / 'preflight.json'), baseline=760, wave_limit_bytes=64 * 1024 * 1024,
            no_retry=True, readonly_probes=True, coverage_admitted=False, population_merge_requires_latest761=True)
        life.save(RUN.with_name(RUN.name + '.prepared.json'), manifest)
        print('PREPARED ' + life.digest(RUN.with_name(RUN.name + '.prepared.json')), flush=True)
    except Exception as exc:
        life.save(PRE / 'failure.json', dict(reason=str(exc), coverage_admitted=False)); raise


def run(seal):
    path = RUN.with_name(RUN.name + '.prepared.json'); manifest = life.read_bound(path, seal)
    require(manifest['command'] == make_command(PRE / 'input.elf', RUN) and manifest['timeout_s'] == 600 and
            manifest['coverage_admitted'] is False and manifest['readonly_probes'] is True and not RUN.exists(),
            'Exact one-shot bounded runner required')
    manifest = dict(manifest, pins=life.merge_pins(manifest['pins'], {str(path): seal}))
    life.run(RUN, manifest)
    lines = (RUN / 'console.log').read_text().splitlines()
    require(lines.count('LOAD_NI_PROBE_READY') == 1 and not any(s.startswith('LOAD_NI_PROBE_ERROR') for s in lines),
            'Actual anchored probe readiness/error differs')
    wave = RUN / 'load-ni-tlb.vpd'
    require(wave.is_file() and 0 < wave.stat().st_size <= manifest['wave_limit_bytes'], 'Bounded observation missing')
    life.save(RUN / 'terminal-capture.json', dict(status='TERMINAL_CAPTURE_PENDING_ARCHITECTURE_AXI_AND_FSM_QUALIFICATION',
        wave_sha256=life.digest(wave), coverage_admitted=False, baseline_for_diagnostic=760,
        formal_merge_requires_latest761=True))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--prepare', action='store_true'); p.add_argument('--run-seal')
    a = p.parse_args(); require(bool(a.prepare) != bool(a.run_seal), 'One mode required')
    if a.prepare: prepare()
    else: run(a.run_seal)
