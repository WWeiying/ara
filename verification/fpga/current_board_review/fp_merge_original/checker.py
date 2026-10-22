"""Exact original vfmerge195 raw-oracle and architectural-retirement checks."""
import csv
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PREP = HERE / 'prepared01'
BAD = re.compile(r'\bRVV_[A-Z0-9_]*(?:FAIL(?:ED)?|DETAIL|CLASSIFY)\b|BOARD_\w*(?:FAIL(?:ED)?|TRAP|MISMATCH)|'
                 r'\b(?:SKIP|MATRIX_FAIL|EXTENSION_MATRIX_FAIL|EXTENDED_FAIL|EPOCH_FAIL)\b|'
                 r'Core Test \*\*\* FAIL|Error-\[|Fatal[-:]|UVM_(?:ERROR|FATAL)|Assertion[^\n]*failed')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def console(text):
    lines = [s.strip() for s in text.splitlines()]
    markers = ['RVV_FP_MOVE_PASS sew=16 cases=195 errors=0',
               'BOARD_CASE_PASS fp_merge_prefix195', 'BOARD_REPLAY_PASS']
    require(not BAD.search(text) and all(lines.count(m) == 1 for m in markers), 'Raw original oracle veto')
    require(re.findall(r'^RVV_FP_MOVE_PASS.*$', text, re.M) == [markers[0]], 'Wrong/duplicate summary')
    require('Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text, 'Missing zero-tohost/finish')


def layout():
    text = (PREP / 'soc/fp_merge_prefix195.dis').read_text()
    body = text.split('<op_0>:\n', 1)[1].split('\n\n', 1)[0]
    instructions = [(int(pc, 16), int(op, 16), asm.strip()) for pc, op, asm in
                    re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+([^\n]+)', body, re.M)]
    require(len(instructions) == 21 and instructions[12][:2] == (0x800005e6, 0x5c805c57), 'Sealed op0 layout')
    return instructions


def gpr_write(insn):
    if insn & 3 != 3:
        return not ((insn & 3) in (0, 2) and (insn >> 13) in (1, 5))
    opcode = insn & 127
    return opcode in (0x03, 0x13, 0x1b, 0x33, 0x3b, 0x37, 0x17, 0x6f, 0x67, 0x73) or (
        opcode == 0x57 and (insn >> 12) & 7 == 7)


def retirement(rows):
    seq = json.loads((PREP / 'call_sequence.json').read_text())
    body = layout()
    pcs = {x[0] for x in body}
    regs = {0: 0}
    count = 0
    step = None
    retired = 0
    cycle = -1
    targets = []
    exits = 0
    state = {}
    for row in rows:
        current = int(row['cycle'])
        require(current >= cycle, 'Nonmonotonic cycle')
        cycle = current
        if row['event'] != 'retire':
            continue
        require(int(row['order']) == retired and int(row['trap'], 0) == 0, 'Retire gap/trap')
        retired += 1
        pc, insn = int(row['pc'], 16), int(row['insn'], 16)
        rd, value = int(row['rd']), int(row['rd_wdata'], 16)
        if pc == body[0][0]:
            require(step is None and count < 195, 'Unexpected additional/nested call')
            step, state = 0, {}
        if step is not None:
            require((pc, insn) == body[step][:2], 'Original op0 instruction sequence differs')
            expected = seq[count]
            ctrl = (expected['sticky'] << 32) | expected['vstart']
            require(regs.get(13) == expected['vl'] and regs.get(14) == 512 and regs.get(16) == ctrl,
                    'VL/capacity/packed-control predecessor argument differs')
            if step == 0:
                require(rd == 30 and value == 0, 'Saved caller fflags differs')
            elif step in (1, 6, 18):
                wanted = expected['vl'] if step == 6 else 512
                require(rd == 5 and value == wanted, 'Actual vsetvli VL differs')
                state['vl'] = value
            elif step == 5:
                require(rd == 0 and value == 0xffffffffffff0000 and int(row['mem_rmask'], 16) == 255 and
                        int(row['mem_addr'], 16) == regs.get(11), 'Actual scalar load/boxing differs')
                state['boxed'] = value
            elif step == 8:
                require(regs.get(7) == expected['sticky'], 'Sticky CSR write differs')
                state['sticky'] = regs[7]
            elif step == 11:
                require(regs.get(7) == expected['vstart'], 'Vstart CSR write differs')
                state['vstart'] = regs[7]
            elif step == 12:
                require(state == dict(vl=expected['vl'], boxed=0xffffffffffff0000,
                        sticky=expected['sticky'], vstart=expected['vstart']), 'Incomplete target setup')
                targets.append(dict(index=count, pc=hex(pc), opcode=hex(insn), cycle=cycle, **state))
            elif step == 13:
                require(rd == 10 and value == 0, 'Returned vstart not zero')
            elif step == 14:
                require(rd == 6 and value == expected['sticky'], 'Returned fflags differs')
            elif step == 16:
                require(rd == 10 and value == expected['sticky'] << 32, 'Returned packed status differs')
            elif step == 17:
                require(regs.get(30) == 0, 'Caller fflags restore operand differs')
            elif step == 20:
                require(regs.get(10) == expected['sticky'] << 32, 'Return status changed')
            step += 1
            if step == len(body):
                count += 1
                step = None
        elif pc in pcs or insn == 0x5c805c57:
            raise ValueError('Unframed or unexpected merge target')
        if int(row['mem_wmask'], 16) and int(row['mem_addr'], 16) == 0xd0000000:
            require(pc == 0x80000072 and insn == 0x00a2b023 and count == 195 and
                    int(row['mem_wmask'], 16) == 255 and int(row['mem_wdata'], 16) == 0,
                    'Wrong raw exit store')
            exits += 1
        if rd and gpr_write(insn):
            regs[rd] = value
    require(count == len(targets) == 195 and step is None and exits == 1, 'Incomplete calls/exit')
    return dict(calls=count, targets=targets, retired=retired, last_cycle=cycle, raw_exit=0)


def check_trace(path):
    with path.open() as stream:
        return retirement(csv.DictReader(stream))
