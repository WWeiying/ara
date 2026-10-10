"""Software-only M-mode SATP/SEPC WARL matrix; no DUT or admission."""
import argparse
import json
from pathlib import Path
import subprocess

import build_gap98_preflight as shared
import inventory_csr_707 as inventory
import targeted_toggle_evidence_v2 as toggle

ROOT, OUT, sha, save, require = shared.ROOT, shared.OUT, shared.sha, shared.save, shared.require
BASE = OUT / 'valu-restart-offline-admitted785-agent-20261008-01'
BASE_SHA = '10273c45e4a4eb21929e0599a2bfc27bfb76afb2b36fe547de0198b5ee918cf5'
RESIDUAL = OUT / 'rr-disabled-formats783-residual-agent-20261008-01.json'
RESIDUAL_SHA = '72fa095bde6587789258359f12e8f7ddf921b7769e00734e6755918c5fe899e5'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/csr_satp_sepc_matrix785.c'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane'
PPN = [0, (1 << 44) - 1, 0xaaaaaaaaaaa, 0x55555555555, 1 << 43, (1 << 43) | 1]
EPC = [0, (1 << 38) - 1, 0xffffffc000000000, (1 << 64) - 1, 0x1555555555, 0x2aaaaaaaaa]
GUARDS = [0x13579bdf2468ace0, 0xfedcba9876543210]
SPIKE_SOURCE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart')
SPIKE_ISA = 'rv64gcv_zfh_zvfh_zvl1024b'
REGRESSION = OUT / 'csr-satp-sepc785-preflight-agent-20261008-03'
REGRESSION_PINS = {
    str(REGRESSION / 'input.elf'): 'db6e0c5fe7835da7dfb903c5650a9afb69902acedf31706e8f977f15c323ce11',
    str(REGRESSION / 'spike.trace'): '71ec33327b4784f2bbaab48d166fc82e079d2c99d7125edfba3e181af03708fe'}


def expected(status):
    require(type(status) is int and status & 0x20008 == 0, 'MPRV/MIE must stay zero')
    values, old = [0, 0, 0], 0
    for ppn in PPN:
        new = (8 << 60) | ppn
        values.extend((old, new, 0)); old = new
    old = 0
    for epc in EPC:
        new = epc & ~1
        values.extend((old, new, 0)); old = new
    return values + [0, 0, status]


def target_evidence(pins):
    def pin(path, seal=None):
        path = Path(path).absolute(); digest = sha(path)
        require(seal is None or digest == seal, 'Bound input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == digest, 'Conflicting pin')
        pins[str(path)] = digest
        return path
    base = json.loads(pin(BASE / 'admission-manifest.json', BASE_SHA).read_bytes())
    status = json.loads(pin(BASE / 'status.json', base['output_pins'][str(BASE / 'status.json')]).read_bytes())
    ledger_path = pin(BASE / 'combined-inputs.txt', base['output_pins'][str(BASE / 'combined-inputs.txt')])
    ledger = ledger_path.read_text().splitlines()
    require(status['coverage_admitted'] is True and type(status['aggregate_passed']) is int
            and status['aggregate_passed'] == 785 and len(ledger) == len(set(ledger)) == 786, 'Exact formal785')
    residual = json.loads(pin(RESIDUAL, RESIDUAL_SHA).read_bytes())
    require(residual['population'] == 783, 'Exact residual783 authority')
    book = json.loads(pin(inventory.BUILD / 'build-source-pins.json').read_bytes())
    for path in (inventory.SOURCE, inventory.CONFIG, ROOT / 'hardware/src/ara_soc.sv',
                 ROOT / 'hardware/deps/cva6/core/include/config_pkg.sv'):
        pin(path, book[str(path)])
    source = inventory.SOURCE.read_text()
    config = inventory.CONFIG.read_text()
    require('CVA6ConfigCExtEn = 1;' in config and 'RVS: bit\'(1)' in config,
            'Frozen C/S extension source guard')
    for fragment in ("sepc_d = {csr_wdata[CVA6Cfg.XLEN-1:1], 1'b0}", 'satp = satp_t\'(csr_wdata)',
                     'satp_d = satp;', 'config_pkg::ModeOff', 'CVA6Cfg.MODE_SV'):
        require(fragment in source, 'WARL source guard')
    scopes = [SCOPE, SCOPE + '.csr_regfile_i']
    db = Path(ledger[0]) / 'snps/coverage/db'
    files = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for path in files:
        require(str(path) in base['input_pins'], 'Unbound design/shape')
        pin(path, base['input_pins'][str(path)])
    checks, definitions = toggle.definitions(*(toggle.xml(p) for p in files), scopes)
    suffix = []
    for vdb in ledger[-2:]:
        paths = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths) == 1 and str(paths[0]) in base['input_pins'], 'Bound784/785 suffix')
        pin(paths[0], base['input_pins'][str(paths[0])])
        rows, digest = toggle.rows(paths[0], scopes)
        require(digest == pins[str(paths[0])], 'Suffix bytes differ')
        suffix.append(rows)
    requested = {SCOPE: {'satp_ppn_csr_ex'}, SCOPE + '.csr_regfile_i':
                 {'satp_q.ppn', 'satp_d.ppn', 'satp_ppn_o', 'sepc_q', 'sepc_d'}}
    targets = []
    for group in residual['residual_groups']:
        for member in group['members']:
            scope, name = member['scope'], member['attributes']['name']
            if scope not in requested or name not in requested[scope]: continue
            require(member['checksum'] == checks[scope], 'Compiled checksum mismatch')
            remaining = list(member['coordinates'])
            for rows in suffix:
                row = rows[scope]
                require(row['checksum'] == member['checksum'], 'Suffix checksum mismatch')
                remaining = [i for i in remaining if not int(row['bits'], 16) >> (row['width'] - 1 - i) & 1]
            targets.append(dict(scope=scope, name=name, checksum=member['checksum'], kind=member['kind'],
                attributes=member['attributes'], missing_coordinates=remaining, missing_count=len(remaining),
                dynamic_gain_promised=False, fixed_bit0_retained=name.startswith('sepc_')))
    require(len(targets) == 6 and len({(r['scope'], r['name']) for r in targets}) == 6, 'Exact six typed fields')
    return dict(baseline=785, baseline_seal=BASE_SHA, fields=targets,
        coordinate_semantics='zero-based left-to-right serialized positions; not official denominators',
        source_predicate='M-mode throughout, MPRV=MIE=0; no SRET/MRET; no access via test PPN/SEPC',
        compiled_definitions=definitions, official_gain_claimed=False, native_qualification=False)


def validate(commits, symbols):
    regs, mstatus, reads, writes, accesses = {0: 0}, 0, [], [], 0
    final_memory, initial_status = {}, None
    for c in commits:
        require(not c.vector_writes and c.pc != symbols['trap_fail'], 'Unexpected vector/trap')
        require(c.instruction not in (0x30200073, 0x10200073), 'Privilege return forbidden')
        require(0x80000000 <= c.pc < 0x80200000, 'Fetch outside sealed RAM')
        insn = c.instruction; csr = insn >> 20; fun = (insn >> 12) & 7; rs = (insn >> 15) & 31; rd = (insn >> 7) & 31
        if insn & 127 == 0x73 and fun in (1, 2, 3, 5, 6, 7):
            value = rs if fun >= 5 else regs.get(rs)
            require(value is not None, 'Unknown CSR operand')
            if csr == 0x300:
                if fun in (1, 5): mstatus = value
                elif fun in (2, 6): mstatus |= value
                else: mstatus &= ~value
                require(mstatus & 0x20008 == 0, 'MPRV/MIE changed')
                if initial_status is None and rd:
                    initial_status = c.gpr_writes.get(rd)
            if csr in (0x180, 0x141):
                accesses += 1
                if fun == 1 and rs: writes.append((csr, value))
                elif fun == 1 and not rs: writes.append((csr, 0))
                else: require(fun == 2 and rs == 0, 'Unexpected matrix CSR operation')
                if rd:
                    require(rd in c.gpr_writes, 'Missing CSR readback GPR')
                    reads.append((csr, c.gpr_writes[rd]))
        for address, value in c.memory_accesses:
            require(0x80000000 <= address < 0x80200000, 'High physical memory access')
            if value is not None: final_memory[address] = value
            require(address not in (symbols['matrix_guards'], symbols['matrix_guards'] + 8) or value is None, 'Guard store')
        regs.update(c.gpr_writes); regs[0] = 0
    require(initial_status is not None, 'No initial status read')
    wanted = expected(initial_status)
    observed = [final_memory.get(symbols['matrix_observed'] + 8 * i) for i in range(42)]
    require(observed == wanted, 'Independent 42-value CSR oracle')
    require(writes == [(0x180, (8 << 60) | p) for p in PPN] + [(0x141, p) for p in EPC] + [(0x180, 0), (0x141, 0)], 'Exact write population')
    expected_reads = [(0x141, 0), (0x180, 0)]
    old = 0
    for p in PPN:
        new = (8 << 60) | p; expected_reads += [(0x180, old), (0x180, new)]; old = new
    old = 0
    for p in EPC:
        new = p & ~1; expected_reads += [(0x141, old), (0x141, new)]; old = new
    expected_reads += [(0x180, 0), (0x141, 0)]
    require(reads == expected_reads and accesses == 30, 'Exact old/new/restored CSR readback sequence')
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols['tohost'] and v is not None]
    require(terminal == [1] and final_memory.get(symbols['g75_result']) == 44 and
            final_memory.get(symbols['g75_result'] + 4) == final_memory.get(symbols['num_failed']) == 0 and
            all(final_memory.get(symbols['g75_trap'] + i) == 0 for i in (0, 8, 16)), 'Exact success/signature/no trap')
    return dict(status='SPIKE_SOFTWARE_CSR_MATRIX_PASS_NOT_DUT', checks=44, observed_bytes=336,
                matrix_CSR_accesses=30, CSR_writes=14, traps=0, vector_destination_instructions=0,
                entry_to_tohost_retired=len(commits), all_reference_memory_accesses=sum(len(c.memory_accesses) for c in commits),
                native_qualified=False, RTL_changed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output')
    pins = {}; targets = target_evidence(pins)
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name('test_build_csr_satp_sepc785.py'),
             ROOT / 'verification/tests/gap75_start.S', ROOT / 'verification/tests/gap75.ld',
             shared.LLVM / 'clang', shared.LLVM / 'llvm-readelf', shared.SPIKE,
             Path(shared.__file__).resolve(), Path(inventory.__file__).resolve(),
             Path(toggle.__file__).resolve(), Path(toggle.base.__file__).resolve(),
             SPIKE_SOURCE / 'riscv/csrs.cc', SPIKE_SOURCE / 'riscv/csr_init.cc']
    paths += list((ROOT / 'verification/ara_verify').glob('*.py'))
    paths += [p for p in (ROOT / 'apps/riscv-tests/isa/macros').rglob('*') if p.is_file()]
    for p in paths: pins = shared.merge_pins(pins, {str(p): sha(p)})
    pins = shared.merge_pins(pins, REGRESSION_PINS)
    shared.check(pins); out.mkdir(); save(out / 'target-before.json', targets)
    save(out / 'independent-gold.json', dict(PPN=PPN, SEPC_input=EPC, SEPC_read=[p & ~1 for p in EPC], guards=GUARDS, checks=44))
    command = [str(shared.LLVM / 'clang'), '--target=riscv64-unknown-elf', '-march=rv64g',
               '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-O2',
               '-fno-vectorize', '-fno-slp-vectorize', '-ffreestanding', '-DG75_NO_PRINT', '-D__SPIKE__',
               '-DVLEN=1024', '-DNR_LANES=4', '-I' + str(ROOT / 'apps/riscv-tests/isa/macros/vector'),
               '-I' + str(ROOT / 'apps/riscv-tests/env'), '-I' + str(ROOT / 'apps/common'),
               '-fuse-ld=lld', '-nostdlib', '-T' + str(ROOT / 'verification/tests/gap75.ld'),
               str(ROOT / 'verification/tests/gap75_start.S'), str(APP), '-o', str(out / 'input.elf')]
    try:
        save(out / 'compile-command.json', command)
        with (out / 'compile.log').open('x') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {k: shared._elf_symbol(out / 'input.elf', shared.LLVM / 'llvm-readelf', k) for k in
                   ('tohost', 'g75_result', 'g75_trap', 'num_failed', 'trap_fail', 'matrix_observed', 'matrix_guards')}
        command = [str(shared.SPIKE), '--isa=' + SPIKE_ISA, '--priv=msu', '--pmpregions=0',
                   '-l', '--log-commits', str(out / 'input.elf')]
        save(out / 'spike-command.json', command)
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=60)
        commits = list(shared.parse_spike_commits(out / 'spike.trace'))
        start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
        end = next(i for i, c in enumerate(commits) if any(a == symbols['tohost'] and v is not None for a, v in c.memory_accesses))
        validation = validate(commits[start:end + 1], symbols)
        save(out / 'spike-validation.json', validation); shared.check(pins)
        outputs = {str(p): sha(p) for p in out.iterdir() if p.is_file()}
        save(out / 'preflight-manifest.json', dict(status='CSR_SATP_SEPC785_PREFLIGHT_PASS_NOT_DUT', baseline=785,
             baseline_seal=BASE_SHA, input_elf=str(out / 'input.elf'), input_spike_trace=str(out / 'spike.trace'),
             symbols=symbols, pins=pins, output_pins=outputs, validation=validation,
             VCS_authorized=False, coverage_admitted=False, measured_gain=None, RTL_changed=False))
        print(json.dumps(dict(output=str(out), seal=sha(out / 'preflight-manifest.json'), validation=validation)))
    except Exception as error:
        save(out / 'failure.json', dict(status='SOFTWARE_PREFLIGHT_FAILED', reason=str(error))); raise


if __name__ == '__main__': main()
