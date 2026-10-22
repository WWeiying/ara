"""Matched RTL/Spike cause-storage contract; software only, not portable WLRL values."""
import argparse
import json
import re
from pathlib import Path
import subprocess

import build_csr_satp_sepc785 as prior

shared, require = prior.shared, prior.require
ROOT, OUT, sha, save = prior.ROOT, prior.OUT, prior.sha, prior.save
BASE = OUT / 'scalar-entropy64-offline-admitted788-agent-20261008-01'
BASE_SHA = 'cf59a7fd898c33493f662b247448d52642b694a6cce68785e938f20112d12641'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/csr_cause_wlrl788.c'
GUARDS, SPIKE_SOURCE, SPIKE_ISA, SCOPE = prior.GUARDS, prior.SPIKE_SOURCE, prior.SPIKE_ISA, prior.SCOPE
PATTERNS = [0, (1 << 64) - 1, 0xaaaaaaaaaaaaaaaa, 0x5555555555555555,
            1 << 63, (1 << 63) - 1]
SOURCE_SHAS = {'riscv/csrs.cc': '8f22b4fc5f2b6b5d5b9d01ac9abd18fe9aed0f41b27cefd7e4531cfd342a5fdc',
               'riscv/csr_init.cc': '1f1d915df99a0ded4a5df9897555198aec2a2dce3549d4d9714097fbcd9328d8'}


def expected(status):
    require(type(status) is int and status & 0x20008 == 0, 'MIE/MPRV must remain zero')
    result = [0, 0, 0]
    for _ in range(2):
        old = 0
        for value in PATTERNS:
            result.extend((old, value, 0)); old = value
    return result + [0, 0, status]


def source_contract(pins):
    book_path = prior.inventory.BUILD / 'build-source-pins.json'
    book = json.loads(book_path.read_bytes()); pins[str(book_path)] = sha(book_path)
    for path in (prior.inventory.SOURCE, prior.inventory.CONFIG):
        require(sha(path) == book[str(path)], 'Frozen RTL/config changed'); pins[str(path)] = book[str(path)]
    source = re.sub(r'\s+', ' ', prior.inventory.SOURCE.read_text())
    for text in ('scause_d = csr_wdata;', 'riscv::CSR_MCAUSE: mcause_d = csr_wdata;',
                 'mcause_d = mcause_q;', 'scause_d = scause_q;', 'mcause_q <= mcause_d;',
                 'scause_q <= scause_d;'):
        require(text in source, 'Cause storage writer/hold contract changed')
    require("RVS: bit'(1)" in prior.inventory.CONFIG.read_text(), 'Supervisor CSR unavailable')
    for name, seal in SOURCE_SHAS.items():
        path = SPIKE_SOURCE / name
        require(sha(path) == seal, 'Pinned Spike implementation changed'); pins[str(path)] = seal
    header = SPIKE_SOURCE / 'riscv/csrs.h'; pins[str(header)] = sha(header)
    require('class cause_csr_t: public basic_csr_t' in header.read_text(), 'Spike cause writer inheritance')
    return dict(portable_exception_codes=False, scope='RV64 M-mode full64 storage, no actual traps',
                MIE=0, MPRV=0, write_csrs=[0x342, 0x142], RTL_changed=False)


def target_evidence(pins):
    path = BASE / 'admission-manifest.json'
    require(sha(path) == BASE_SHA, 'Formal788 seal'); pins[str(path)] = BASE_SHA
    base = json.loads(path.read_bytes())
    ledger_path = BASE / 'combined-inputs.txt'
    require(sha(ledger_path) == base['output_pins'][str(ledger_path)], 'Formal ledger drift')
    pins[str(ledger_path)] = sha(ledger_path); ledger = ledger_path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 789, 'Exact788 population')
    rp = prior.RESIDUAL; require(sha(rp) == prior.RESIDUAL_SHA, 'Residual authority')
    pins[str(rp)] = prior.RESIDUAL_SHA
    wanted = {'mcause_q', 'mcause_d', 'scause_q', 'scause_d', 'rvfi_csr_o.mcause_q',
              'rvfi_csr_o.scause_q', 'rvfi_csr.mcause_q', 'rvfi_csr.scause_q'}
    members = [m for g in json.loads(rp.read_bytes())['residual_groups'] if g['field'] in wanted for m in g['members']]
    require(len(members) == 8, 'Exact eight fields')
    scopes = {m['scope'] for m in members}; suffix = []
    for vdb in ledger[784:]:
        paths = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths) == 1, 'Single suffix Toggle member'); p = paths[0]
        require(sha(p) == base['input_pins'][str(p)], 'Bound suffix metric'); pins[str(p)] = sha(p)
        rows, digest = prior.toggle.rows(p, scopes); require(digest == pins[str(p)], 'Suffix race'); suffix.append(rows)
    db = Path(ledger[0]) / 'snps/coverage/db'
    files = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for p in files:
        require(sha(p) == base['input_pins'][str(p)], 'Compiled identity'); pins[str(p)] = sha(p)
    checks, definitions = prior.toggle.definitions(*(prior.toggle.xml(p) for p in files), scopes)
    fields = []
    for m in members:
        require(m['checksum'] == checks[m['scope']] and m['kind'] == 'vectornode'
                and m['attributes']['left'] == '63' and m['attributes']['right'] == '0', 'Exact full64 typed field')
        remaining = m['coordinates'][:]
        for rows in suffix:
            r = rows[m['scope']]; require(r['checksum'] == m['checksum'], 'Suffix shape changed')
            remaining = [i for i in remaining if not (int(r['bits'], 16) >> (r['width'] - 1 - i)) & 1]
        fields.append(dict(scope=m['scope'], attributes=m['attributes'], checksum=m['checksum'],
                           missing_coordinates=remaining, missing_count=len(remaining)))
    return dict(baseline=788, baseline_seal=BASE_SHA, fields=fields, compiled_definitions=definitions,
                predicted_capacity=sum(f['missing_count'] for f in fields), measured_gain=None,
                official_percentage_claimed=False)


def validate(commits, symbols):
    regs, state, reads, writes, mem = {0: 0}, {0x342: 0, 0x142: 0}, [], [], {}
    status = None
    for c in commits:
        require(not c.vector_writes and not c.fpr_writes and c.pc != symbols['trap_fail'], 'Unexpected trap/vector/FP')
        require(c.instruction not in (0x30200073, 0x10200073, 0x73), 'Trap/privilege return forbidden')
        require(0x80000000 <= c.pc < 0x80200000, 'Fetch range')
        insn = c.instruction; csr = insn >> 20; fun = insn >> 12 & 7; rd = insn >> 7 & 31; rs = insn >> 15 & 31
        if insn & 127 == 0x73 and csr in state:
            require(fun == 1 or (fun == 2 and rs == 0), 'Unexpected cause CSR operation')
            old = state[csr]
            require(not rd or c.gpr_writes == {rd: old}, 'Independent old/readback cause value')
            if rd: reads.append((csr, old))
            if fun == 1:
                require(rs in regs, 'Unknown cause write operand'); state[csr] = regs[rs]; writes.append((csr, regs[rs]))
        elif insn & 127 == 0x73 and csr == 0x300:
            if rs:
                require(status is None and c.pc == 0x80000018 and insn == 0x3002a073
                        and regs.get(rs) == 0x6600 and rd == 0, 'Only sealed CRT mstatus initialization allowed')
            else:
                require(fun == 2 and rd in c.gpr_writes, 'mstatus must be read only')
                current = c.gpr_writes[rd]; expected(current)
                if status is None: status = current
                require(current == status, 'mstatus changed')
        for address, value in c.memory_accesses:
            require(0x80000000 <= address < 0x80200000, 'Physical access outside RAM')
            require(value is None or not symbols['matrix_guards'] <= address < symbols['matrix_guards'] + 16, 'Guard mutation')
            if value is not None: mem[address] = value
        regs.update(c.gpr_writes); regs[0] = 0
    require(status is not None and [mem.get(symbols['matrix_observed'] + 8*i) for i in range(42)] == expected(status), 'Complete independent gold')
    wanted_reads = [(0x342, 0), (0x142, 0)]
    for csr in state:
        old = 0
        for new in PATTERNS: wanted_reads.extend(((csr, old), (csr, new))); old = new
    wanted_reads.extend(((0x342, 0), (0x142, 0)))
    require(reads == wanted_reads and writes == [(csr, v) for csr in state for v in PATTERNS] + [(0x342, 0), (0x142, 0)]
            and state == {0x342: 0, 0x142: 0}, 'Exact30 owners /14 writes /restore')
    terminal = [v for c in commits for a,v in c.memory_accesses if a == symbols['tohost'] and v is not None]
    require(terminal == [1] and mem.get(symbols['g75_result']) == 44 and mem.get(symbols['g75_result']+4) == 0
            and mem.get(symbols['num_failed']) == 0 and all(mem.get(symbols['g75_trap']+i) == 0 for i in (0,8,16)), 'Success/zero trap signature')
    return dict(status='SPIKE_MATCHED_CAUSE_STORAGE_PASS_NOT_DUT', checks=44, observed_bytes=336,
                matrix_CSR_accesses=30, CSR_writes=14, traps=0, entry_to_tohost_retired=len(commits),
                all_reference_memory_accesses=sum(len(c.memory_accesses) for c in commits), portable_exception_codes=False)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); out = p.parse_args().output.absolute()
    require(out.parent == OUT and not out.exists(), 'Fresh direct output')
    pins = {}; contract = source_contract(pins); targets = target_evidence(pins)
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name('test_build_csr_cause_wlrl788.py'),
             ROOT/'verification/tests/gap75_start.S', ROOT/'verification/tests/gap75.ld', shared.LLVM/'clang',
             shared.LLVM/'llvm-readelf', shared.SPIKE, Path(prior.__file__), Path(shared.__file__), Path(prior.toggle.__file__)]
    paths += list((ROOT/'verification/ara_verify').glob('*.py'))
    paths += [f for f in (ROOT/'apps/riscv-tests/isa/macros').rglob('*') if f.is_file()]
    pins = shared.merge_pins(pins, {str(f): sha(f) for f in paths}); shared.check(pins); out.mkdir()
    save(out/'target-before.json', targets); save(out/'implementation-contract.json', contract)
    command = [str(shared.LLVM/'clang'), '--target=riscv64-unknown-elf', '-march=rv64g', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-O2', '-fno-vectorize', '-fno-slp-vectorize', '-ffreestanding', '-DG75_NO_PRINT', '-D__SPIKE__', '-DVLEN=1024', '-DNR_LANES=4', '-I'+str(ROOT/'apps/riscv-tests/isa/macros/vector'), '-I'+str(ROOT/'apps/riscv-tests/env'), '-I'+str(ROOT/'apps/common'), '-fuse-ld=lld', '-nostdlib', '-T'+str(ROOT/'verification/tests/gap75.ld'), str(ROOT/'verification/tests/gap75_start.S'), str(APP), '-o', str(out/'input.elf')]
    save(out/'compile-command.json', command)
    with (out/'compile.log').open('x') as log: subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    symbols = {k: shared._elf_symbol(out/'input.elf', shared.LLVM/'llvm-readelf', k) for k in ('tohost','g75_result','g75_trap','num_failed','trap_fail','matrix_observed','matrix_guards')}
    command = [str(shared.SPIKE), '--isa='+SPIKE_ISA, '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(out/'input.elf')]
    save(out/'spike-command.json', command)
    with (out/'spike.stdout').open('x') as stdout, (out/'spike.trace').open('x') as trace: subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=60)
    commits = list(shared.parse_spike_commits(out/'spike.trace')); start = next(i for i,c in enumerate(commits) if c.pc == 0x80000000)
    end = next(i for i,c in enumerate(commits) if (symbols['tohost'],1) in c.memory_accesses)
    validation = validate(commits[start:end+1], symbols); save(out/'spike-validation.json', validation); shared.check(pins)
    save(out/'preflight-manifest.json', dict(status='CAUSE_WLRL788_PREFLIGHT_PASS_NOT_DUT', baseline=788, baseline_seal=BASE_SHA, input_elf=str(out/'input.elf'), input_spike_trace=str(out/'spike.trace'), symbols=symbols, pins=pins, output_pins={str(f):sha(f) for f in out.iterdir() if f.is_file()}, validation=validation, implementation_contract=contract, VCS_authorized=False, coverage_admitted=False, RTL_changed=False))
    print(json.dumps(dict(output=str(out), seal=sha(out/'preflight-manifest.json'), validation=validation)))

if __name__ == '__main__': main()
