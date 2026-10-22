"""Exact23 GAP100 exceptions/handlers/returns bound to15 ECALL RVFI trap rows."""
import argparse
from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path
import re

import replay_gap100_no_clint_dtb as reference

runtime, runner, software = reference.runtime, reference.runner, reference.software
require, save, OUT = reference.require, reference.save, reference.OUT
REFERENCE = OUT / 'gap100-spike-no-clint-dtb-713-20261006-01'
REFERENCE_SEAL = '9885f40f933e1e94ce0cdd2abc9fa6698d75fb435714e47d36676d83e49ba3c2'
TRACE_RE = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
EX_RE = re.compile(r'^Exception @\s*(\d+), PC: ([0-9a-fA-F]{16}), Cause: ([^,\n]+)(?:,\s*)?$')
CAUSES = {'Illegal Instruction': 2, 'Breakpoint': 3, 'Environment Call User Mode': 8,
          'Environment Call Supervisor Mode': 9, 'Environment Call Machine Mode': 11,
          'Supervisor Software Interrupt': (1 << 63) | 1}


def parse_trace(text):
    instructions, exceptions = [], []
    lines = text.splitlines()
    for number, line in enumerate(lines):
        instruction = TRACE_RE.match(line)
        if instruction:
            cycle, priv, pc, insn = instruction.groups()
            instructions.append(dict(line=number, cycle=int(cycle), privilege=priv,
                                     pc=int(pc, 16), insn=int(insn, 16)))
        if line.startswith('Exception'):
            event = EX_RE.fullmatch(line)
            require(event is not None, 'Malformed exception directive')
            tick, pc, name = event.groups()
            require(name in CAUSES, 'Unknown exception cause')
            tval = None
            if CAUSES[name] in (2, 3):
                require(number + 1 < len(lines), 'Missing exception TVAL')
                match = re.fullmatch(r'\s*tval: ([0-9a-fA-F]{16})\s*', lines[number + 1])
                require(match is not None, 'Malformed/missing TVAL')
                tval = int(match[1], 16)
            exceptions.append(dict(line=number, trace_tick=int(tick), pc=int(pc, 16),
                                   cause=CAUSES[name], tval=tval))
    require(len(exceptions) == 23 and all(a['trace_tick'] < b['trace_tick'] for a, b in zip(exceptions, exceptions[1:])),
            'Exception count/time ordering differs')
    return instructions, exceptions


def expected_events(symbols):
    result = []
    for phase in range(15):
        priv, _, _, cause = software.phase(phase)
        if cause:
            pc = symbols['g100_hpm'] if phase < 12 else symbols['g100_break'] if phase == 12 else \
                 symbols['g100_irq_begin'] if phase == 13 else symbols['g100_uecall']
            resume = pc + 4 if phase != 13 else symbols['g100_after_irq']
            result.append(dict(phase=phase, kind='primary', cause=cause, pc=pc, resume=resume,
                               handler_priv=1 if phase >= 13 else 3, resumed_priv=priv,
                               tval=0xc0302f73 if phase < 12 else None))
        exit_pc = symbols['g100_hpm'] + 16 if phase < 12 else symbols['g100_break'] + 4 if phase == 12 else \
                  symbols['g100_after_irq'] if phase == 13 else symbols['g100_uecall'] + 4
        result.append(dict(phase=phase, kind='exit', cause=2 if phase == 14 else priv + 8,
                           pc=exit_pc, resume=symbols['g100_return'], handler_priv=3, resumed_priv=3,
                           tval=0x30002f73 if phase == 14 else None))
    return result


def audit(rows, text, symbols):
    trace, exceptions = parse_trace(text)
    normal = [r for r in rows if not r['trap']]
    tail = trace[len(normal):]
    # The monitor finishes at port0's tohost store, before logging port1.
    require(len(tail) == 1 and tail[0]['cycle'] == normal[-1]['cycle'] and
            tail[0]['pc'] == normal[-1]['pc'] + 4 and tail[0]['insn'] == 0xa001 and
            tail[0]['privilege'] == 'M' and normal[-1]['port'] == 0 and
            normal[-1]['mem_addr'] == symbols['tohost'] and normal[-1]['mem_wmask'] == 255 and
            normal[-1]['mem_wdata'] == 1, 'Unexpected post-terminal tracer tail')
    trace = trace[:len(normal)]
    require(len(trace) == len(normal) and all((a['cycle'], a['pc'], a['insn']) ==
            (b['cycle'], b['pc'], b['insn']) for a, b in zip(trace, normal)), 'Independent trace/RVFI retirement differs')
    specs = expected_events(symbols)
    trap_rows = [r for r in rows if r['trap']]
    expected_rvfi = [x for x in specs if x['cause'] in (8, 9, 11)]
    require(len(trap_rows) == len(expected_rvfi) == 15 and
            all(r['pc'] == x['pc'] and r['insn'] == 0x73 and not r['mem_wmask'] and not r['mem_rmask']
                for r, x in zip(trap_rows, expected_rvfi)), 'ECALL RVFI trap inventory differs')
    # All operands are recovered from the complete, unnormalized retirement trace.
    regs, before = {0: 0}, []
    for r in normal:
        before.append(dict(regs))
        if r['rd']:
            regs[r['rd']] = r['rd_wdata']
    lines = [r['line'] for r in trace]
    entries = [bisect_right(lines, event['line']) for event in exceptions]
    ledger, rvfi_index = [], 0
    for index, (event, spec) in enumerate(zip(exceptions, specs)):
        require((event['cause'], event['pc']) == (spec['cause'], spec['pc']), 'Exception cause/PC/order differs')
        if spec['tval'] is not None:
            require(event['tval'] == spec['tval'], 'Illegal instruction TVAL differs')
        if spec['cause'] == 3:
            require(event['tval'] in (0, event['pc']), 'Breakpoint TVAL outside architectural contract')
        start = entries[index]
        stop = entries[index + 1] if index + 1 < len(entries) else len(normal)
        require(start < stop, 'Missing/overlapping handler interval')
        target = symbols['g100_s_table'] if spec['handler_priv'] == 1 else symbols['g100_m_table']
        target += 4 if spec['cause'] >> 63 else 0
        require(trace[start]['pc'] == target and trace[start]['privilege'] == {1: 'S', 3: 'M'}[spec['handler_priv']],
                'Wrong exact vector entry/privilege')
        returns = [i for i in range(start, stop) if normal[i]['insn'] in (0x30200073, 0x10200073)]
        require(returns, 'Missing trap return')
        ret = returns[0]
        immediate_trap = (spec['kind'] == 'primary' and index + 1 < len(specs) and
                          specs[index + 1]['phase'] == spec['phase'] and
                          specs[index + 1]['kind'] == 'exit' and
                          exceptions[index + 1]['pc'] == spec['resume'] and ret + 1 == stop)
        require(normal[ret]['insn'] == (0x10200073 if spec['handler_priv'] == 1 else 0x30200073) and
                (immediate_trap or (ret + 1 < len(normal) and normal[ret + 1]['pc'] == spec['resume'] and
                trace[ret + 1]['privilege'] == {0: 'U', 1: 'S', 3: 'M'}[spec['resumed_priv']])), 'Wrong return/resume privilege or PC')
        csr_reads, csr_writes = {}, []
        for i in range(start, ret):
            r = normal[i]
            insn = r['insn']
            if insn & 127 != 0x73 or not (insn >> 12) & 7:
                continue
            csr, funct, rs, rd = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31, (insn >> 7) & 31
            if rd and csr in (0x341, 0x342, 0x343, 0x141, 0x142, 0x143):
                require(r['rd'] == rd, 'Handler CSR read destination differs')
                csr_reads.setdefault(csr, []).append(r['rd_wdata'])
            if funct in (1, 5) or rs:
                operand = rs if funct >= 5 else before[i].get(rs)
                require(operand is not None, 'Unproven handler CSR write operand')
                csr_writes.append(dict(pc=r['pc'], csr=csr, funct=funct, operand=operand))
        cause_csr, epc_csr, tval_csr = (0x142, 0x141, 0x143) if spec['handler_priv'] == 1 else (0x342, 0x341, 0x343)
        require(csr_reads.get(cause_csr) == [spec['cause']], 'First handler cause observation differs')
        if spec['kind'] == 'primary':
            require(csr_reads.get(epc_csr) == [event['pc']], 'Primary original EPC observation differs')
            if event['tval'] is not None:
                require(csr_reads.get(tval_csr) == [event['tval']], 'Handler TVAL observation differs')
            else:
                require(csr_reads.get(tval_csr) == [0], 'Interrupt/ECALL TVAL differs')
        epc_writes = [r for r in csr_writes if r['csr'] == epc_csr]
        require(len(epc_writes) == 1 and epc_writes[0]['funct'] == 1 and epc_writes[0]['operand'] == spec['resume'],
                'Exact handler EPC write missing/different')
        row = dict(index=index, expected=spec, exception=event, vector_entry=trace[start],
                   cause_reads=csr_reads, csr_writes=csr_writes, return_pc=normal[ret]['pc'],
                   return_order=normal[ret]['order'], resume_order=normal[ret + 1]['order'])
        row['resume_immediately_traps'] = immediate_trap
        if spec['cause'] in (8, 9, 11):
            rvfi = trap_rows[rvfi_index]
            rvfi_index += 1
            require(rvfi['order'] < normal[start]['order'] and
                    (start == 0 or rvfi['order'] > normal[start - 1]['order']), 'RVFI ECALL not immediately bound to handler entry')
            row['rvfi_trap'] = rvfi
        else:
            row['rvfi_trap'] = None
            row['rvfi_omission_reason'] = 'Frozen cva6_rvfi valid emits ECALL exceptions only; monitor requires valid.'
        ledger.append(row)
    return dict(status='GAP100_EXACT23_TRAP_HANDLER_RETURN_LEDGER_NOT_ADMISSION', ledger=ledger,
                exceptions=23, rvfi_ecall_trap_rows=15, non_rvfi_exceptions=dict(illegal_instruction=6, breakpoint=1, SSIP=1),
                independent_trace_nontrap_retirements=len(normal), complete_handler_epc_return_binding=True,
                terminal_same_cycle_self_jump=tail,
                normalization_performed=False, coverage_admitted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct ledger output required')
    result = runner.life.read_bound(REFERENCE / 'reference-result.json', REFERENCE_SEAL)
    pins = runner.life.merge_pins(result['pins'], {str(REFERENCE / 'reference-result.json'): REFERENCE_SEAL})
    sourcefile = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcepins = json.loads(sourcefile.read_bytes())
    for rel in ('hardware/deps/cva6/core/cva6_rvfi.sv', 'hardware/tb/ara_commit_monitor.sv',
                'hardware/deps/cva6/common/local/util/instr_tracer.sv', 'hardware/deps/cva6/common/local/util/ex_trace_item.svh'):
        path = runtime.ROOT / rel
        require(str(path) in sourcepins, 'Source not pinned by frozen build: ' + rel)
        pins = runner.life.merge_pins(pins, {str(path): sourcepins[str(path)]})
    for path in (sourcefile, runtime.RUN / 'trace_hart_0.log', Path(__file__).resolve(),
                 Path(__file__).with_name('test_audit_gap100_trap_ledger.py')):
        pins = runner.life.merge_pins(pins, {str(path): runner.life.digest(path)})
    runner.life.check(pins)
    rvfi_source = (runtime.ROOT / 'hardware/deps/cva6/core/cva6_rvfi.sv').read_text()
    require('valid     = (commit_ack[i] && !ex_commit_valid && !commit_drop[i]) ||' in rvfi_source and
            'ex_commit_cause == riscv::ENV_CALL_MMODE' in rvfi_source and
            'ex_commit_cause == riscv::ENV_CALL_SMODE' in rvfi_source and
            'ex_commit_cause == riscv::ENV_CALL_UMODE' in rvfi_source, 'RVFI validity proof source differs')
    pre = runner.life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
    symbols = dict(pre['symbols'], g100_return=software.shared._elf_symbol(Path(pre['input_elf']),
                       software.shared.LLVM / 'llvm-readelf', 'g100_return'))
    ledger = audit(runtime.commit_rows(runtime.RUN / 'commit_trace.csv'),
                   (runtime.RUN / 'trace_hart_0.log').read_text(), symbols)
    runner.life.check(pins)
    ledger.update(pins=pins, original_execution_manifest_seal=runtime.RUN_SEAL,
                  qualified_reference_result_seal=REFERENCE_SEAL, source_checker_pins={k: v for k, v in pins.items()
                  if '/verification/ara_verify/' in k}, output_scope='Supplementary trap qualification, not aggregate admission')
    save(out, ledger)
    print(json.dumps(dict(output=str(out), seal=runner.life.digest(out), exceptions=23, rvfi=15, coverage_admitted=False)))


if __name__ == '__main__':
    main()
