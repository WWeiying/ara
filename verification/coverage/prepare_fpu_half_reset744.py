"""Host/Spike preparation only; no simulation or admission entry point."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from elftools.elf.elffile import ELFFile

import run_gap115_active_reset as old

life, require = old.life, old.require
APP = life.ROOT / 'apps/riscv-tests/isa/rv64uv/vgap_fpu_half_active_reset.c'
OUT = life.OUT / 'fpu-half-active-reset-preflight744-agent-20261007-01'
BASE = life.OUT / 'rvv-lmul8-payload-walk-offline-admitted-744-agent-20261007-01'
SYMBOLS = ('fpar_mul', 'fpar_div', 'fpar_first_ar_load', 'fpar_vrf', 'fpar_csr',
           'g75_result', 'num_failed', 'tohost', 'trap_fail', 'source')


def expected_word(i):
    require(0 <= i < 512, 'Invalid full VRF word')
    return (0x123456789abcdef0, 0x3c003c003c003c00,
            0x4200420042004200, 0x3555355535553555)[i // 128]


def oracle(value):
    require([value('g75_result', 0, 4), value('g75_result', 4, 4),
             value('num_failed', 0, 4), value('tohost')] == [679, 0, 0, 1], 'Terminal/check count')
    for i in range(512):
        require(value('fpar_vrf', i * 8) == expected_word(i), 'Full VRF differs')
    require([value('fpar_csr', i * 8) for i in range(5)] == [512, 11, 0, 0, 33], 'CSR/RTZ/NX differs')


def build():
    require(not OUT.exists(), 'Fresh preflight only')
    book = json.loads((BASE / 'admission-manifest.json').read_bytes())
    bits = life.read_bound(BASE / 'combined-bits.json', book['output_pins'][str(BASE / 'combined-bits.json')])
    require(len(bits['tests']) == len(set(bits['tests'])) == 744, 'Not exact744')
    prior = json.loads((old.PRE / 'preflight.json').read_bytes())
    life.check(prior['pins'])
    pins = dict(prior['pins'])
    for p in (APP, Path(__file__).resolve(), Path(__file__).with_name('test_prepare_fpu_half_reset744.py'),
              BASE / 'admission-manifest.json', BASE / 'combined-bits.json', old.PRE / 'preflight.json'):
        pins[str(p)] = life.digest(p)
    source_pins = json.loads((old.shared.reviewed.base.capture.BUILD / 'build-source-pins.json').read_bytes())
    for rel in ('hardware/tb/ara_tb.sv', 'hardware/src/lane/vmfpu.sv', 'hardware/include/ara_pkg.sv',
                'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv',
                'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_ctrl.v'):
        p = life.ROOT / rel
        pins[str(p)] = source_pins[str(p)]
    command = json.loads((old.PRE / 'compile-command.json').read_bytes())
    command = [str(APP) if x == str(old.APP) else str(OUT / 'input.elf')
               if x == str(old.PRE / 'input.elf') else x for x in command]
    require('ZCC' not in ' '.join(command) and '-O2' in command, 'Compiler contract')
    life.check(pins)
    OUT.mkdir()
    life.save(OUT / 'compile-command.json', command)
    with (OUT / 'build.log').open('x') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    symbols = {k: old.shared.template.s._elf_symbol(OUT / 'input.elf', old.shared.template.s.LLVM / 'llvm-readelf', k)
               for k in SYMBOLS}
    dis = subprocess.check_output(['/usr/bin/llvm-objdump', '-d', '--no-show-raw-insn', str(OUT / 'input.elf')], text=True)
    window = dis.split('<fpar_div>:')[1].split('<fpar_first_ar_load>:')[0]
    require(len(re.findall(r'\bnop\b', window)) == 32 and 'vfdiv.vv' in window, 'Fixed window ELF differs')
    require('vfmul.vv' in dis.split('<fpar_mul>:')[1].split('<fpar_div>:')[0], 'Dependent MUL missing')
    spike = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    pins[str(spike)] = life.digest(spike)
    sc = [str(spike), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(OUT / 'input.elf')]
    life.save(OUT / 'spike-command.json', sc)
    with (OUT / 'spike.trace').open('x') as log:
        subprocess.run(sc, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    commits = old.shared.shared.spike_trace.parse_spike_commits(OUT / 'spike.trace')
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    oracle(lambda n, o=0, size=8: writes.get(symbols[n] + o))
    require(not any(c.pc == symbols['trap_fail'] for c in commits), 'Spike trap')
    require('exception ' not in (OUT / 'spike.trace').read_text(), 'Spike exception')
    counts = old.shared.shared.reference_counts(commits, symbols)
    with (OUT / 'input.elf').open('rb') as stream:
        segments = [(s['p_vaddr'], s.data()) for s in ELFFile(stream).iter_segments() if s['p_type'] == 'PT_LOAD']
    def elf_bytes(address, size):
        found = [data[address - start:address - start + size] for start, data in segments
                 if start <= address and address + size <= start + len(data)]
        require(len(found) == 1, 'ELF range ambiguous')
        return found[0]
    words = {name: elf_bytes(symbols[name], 4).hex()
             for name in ('fpar_mul', 'fpar_div', 'fpar_first_ar_load')}
    source_gold = b''.join(x.to_bytes(8, 'little') for x in
        [0x5a3c719de4b208f6]*16 + [0x123456789abcdef0]*128 + [0x5a3c719de4b208f6]*16)
    require(elf_bytes(symbols['source'], len(source_gold)) == source_gold, 'ELF source/guards differ')
    targets = []
    for scope, row in bits['metrics']['fsm'].items():
        if '.i_ara.gen_lanes[' in scope and scope.endswith('.i_ct_vfdsu_top.x_ct_vfdsu_ctrl'):
            require(row['width'] == 17, 'C910 FSM shape')
            require(all(not int(row['bits'], 16) & (1 << (16 - i)) for i in (7, 8, 12, 15)), 'Target already hit')
            targets.append(dict(scope=scope, primary_raw_index=8, primary='EX2->IDLE',
                                other_reset_indices=[7, 12, 15], bitmap=row))
    require(len(targets) == 16, 'Exact sixteen vector C910 controllers')
    for n in ('input.elf', 'compile-command.json', 'spike-command.json', 'spike.trace', 'build.log'):
        pins[str(OUT / n)] = life.digest(OUT / n)
    pins[str(Path('/usr/bin/llvm-objdump').resolve())] = life.digest(Path('/usr/bin/llvm-objdump').resolve())
    life.check(pins)
    record = dict(status='HOST_SPIKE679_PASS_RESET_TIMING_MEASUREMENT_PENDING', symbols=symbols,
        counts=counts, words=words, pins=pins, targets=targets, fixed_nops=32,
        reset_plusargs=['+ARA_UVM_RESET_ON_AXI=read', '+ARA_UVM_RESET_READ_INDEX=1'],
        intended_budget_s=600, EDA_launched=False, coverage_admitted=False,
        independent_gold='binary16 RTZ 1/3 = 0x3555, NX=1; 1*1 exact; full512 VRF words, CSR and679 software checks',
        timing_boundary='LatFDivSqrt=3 is pipeline allocation, not C910 execution latency. Fixed32 inherited GAP115; historical acceptance-to-load121cycles is evidence, not a universal bound. No exact EX2 phase or new FSM count promised.',
        qualification_requirements=['Independent AR/R twoepoch conservation including aborted AR and no stale response',
          'First Ara AR must belong to fpar_first_ar_load; no earlier vector loads/stores',
          'Epoch0 DIV allocated but backend not done at reset, exact owner and no cross-epoch leak',
          'Epoch1 complete scalar/vector Spike diff and679/fullVRF/CSR/source guards',
          'Actual raw8 or other reset targets measured relative to744; zero reset sampling gain is possible'],
        reusable_epoch_tools=['postprocess_gap115_events_v2.py', 'run_gap115_axi_capture.py'],
        epoch_tool_boundary='Existing event helper contains GAP115-specific counts/opcodes. Reuse mechanisms, not unchanged case-specific gates; latest independent AR/R handoff from owner still required.')
    life.save(OUT / 'preflight.json', record)
    print(json.dumps(dict(output=str(OUT), seal=life.digest(OUT / 'preflight.json'), counts=counts, EDA_launched=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', required=True)
    parser.parse_args()
    build()
