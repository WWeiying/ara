"""FOF successor: native CVA6 ECALL text omits tval; verify mtval in RVFI.

All scalar, RAM/context, native bitwise, lifecycle and terminal checks remain.
No simulator launch or edits to original receipts or sealed v1/v2 helpers.
"""
from pathlib import Path
import re
from types import FunctionType

import audit_fof_repair_v2 as v2

base, require = v2.base, v2.require
V2_SHA = '3b7e93f1722d81eeea4989aa2dbdf1f6eb498b486db1ecff5c108da4837e95c0'


def tracer_exact(text, rows, symbols):
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := pattern.match(line))]
    retired = base.trap_contract(rows, symbols)
    wanted = [(str(int(r['cycle'])),
               'S' if symbols['sf_s_entry'] <= int(r['pc'], 16) < symbols['sf_s_end'] else 'M',
               '%016x' % int(r['pc'], 16), '%08x' % int(r['insn'], 16)) for r in retired]
    require(actual[:len(wanted)] == wanted, 'Full tracer retirement/privilege differential')
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], 'M',
                                 '%016x' % (int(wanted[-1][2], 16) + 4), '0000a001')],
            'Unexpected post-terminal tracer tail')

    # ex_trace_item.svh:64-76 deliberately suppresses tval for ECALLs.
    events = re.findall(r'^Exception @\s*(\d+), PC: ([0-9a-fA-F]{16}), '
                        r'Cause: ([^,\r\n]+)$', text, re.MULTILINE)
    require(len(events) == text.count('Exception @') == 1 and
            int(events[0][1], 16) == symbols['sf_ecall'] and
            events[0][2] == 'Environment Call Supervisor Mode' and
            not re.search(r'\btval\s*:', text),
            'Exactly one native S ECALL header; no printed tval or other trap')

    handler = [r for r in retired if symbols['sf_handler'] <= int(r['pc'], 16)
               < symbols['sf_handler_end']]
    reads = [r for r in handler if int(r['insn'], 16) == 0x34302373]
    stores = [r for r in handler if int(r['mem_wmask'], 16) and
              int(r['mem_addr'], 16) == symbols['sf_record'] + 16]
    require(len(reads) == len(stores) == 1 and int(reads[0]['rd']) == 6 and
            int(reads[0]['rd_wdata'], 16) == 0 and
            int(stores[0]['insn'], 16) == 0x0062b823 and
            int(stores[0]['mem_wmask'], 16) == 255 and
            int(stores[0]['mem_wdata'], 16) == 0 and
            int(reads[0]['order']) < int(stores[0]['order']),
            'Handler mtval CSR read and trap-ledger store must independently be zero')
    return dict(nontrap_retirements=len(retired), S_ecalls=1, fof_traps=0,
                printed_tval=False, handler_mtval=0,
                handler_mtval_read_cycle=int(reads[0]['cycle']),
                handler_mtval_store_cycle=int(stores[0]['cycle']))


def audit(directory):
    require(base.life.digest(Path(base.__file__)) == v2.BASE_SHA, 'Sealed v1 helper identity')
    require(base.life.digest(Path(v2.__file__)) == V2_SHA, 'Sealed v2 helper identity')
    implementation = FunctionType(base.audit.__code__, dict(base.audit.__globals__,
        native=v2.native, tracer_exact=tracer_exact, __file__=__file__))
    result = implementation(directory)
    result['input_pins'].update({str(Path(base.__file__).resolve()): v2.BASE_SHA,
                                 str(Path(v2.__file__).resolve()): V2_SHA})
    result['checker'] = 'audit_fof_repair_v3'
    base.life.check(result['input_pins'])
    return result
