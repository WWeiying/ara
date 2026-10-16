#!/usr/bin/env python3
"""Read an already-stalled task and code pages. No halt, reset or memory writes.

Only the pinned Linux Image's reviewed structure layout is supported. Memory
page tables are not observations of the hart's SATP, TLB or pending requests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

from analyze_loader_stall import IMAGE_SHA256, jal_target
from read_current_restore import physical


def progress_key(snapshot):
    return tuple(snapshot['core'][k] for k in
                 ('retired', 'last_pc', 'head_pc', 'trap_count'))


def saved_user_context(stack):
    if len(stack) != 4096:
        raise ValueError('Expected complete saved kernel stack page')
    # The pinned Image's user return stores sp+288 at task+16, then restores
    # registers from these offsets. This frame is historical, not live state.
    offsets = dict(epc=0, ra=8, sp=16, s0=64, a0=80, a7=136,
                   status=256, badaddr=264, cause=272)
    values = {name: struct.unpack_from('<Q', stack, 4096 - 288 + offset)[0]
              for name, offset in offsets.items()}
    if values['status'] & 0x100 or not 0 < values['sp'] < (1 << 38):
        raise ValueError('Saved frame is not a supported user context')
    return values


def translate(read_word, root, va):
    table = root
    entries = []
    for level in (2, 1, 0):
        address = table + ((va >> (12 + 9 * level)) & 511) * 8
        pte = read_word(address)
        entries.append(dict(level=level, pa=hex(address), pte=hex(pte)))
        if not pte & 1 or (pte & 6) == 4:
            raise ValueError('Invalid PTE at ' + hex(address))
        ppn = (pte >> 10) & ((1 << 44) - 1)
        if pte & 10:
            low = (1 << (9 * level)) - 1
            if ppn & low:
                raise ValueError('Misaligned superpage')
            return ((ppn | ((va >> 12) & low)) << 12) | (va & 4095), entries
        table = ppn << 12
    raise ValueError('No leaf PTE')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('software', 'image', 'probes', 'out'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--vivado', required=True)
    p.add_argument('--expected-retired', required=True, type=int)
    p.add_argument('--context', action='store_true',
                   help='Also read PTE lines, saved kernel stack and last-write page')
    args = p.parse_args()
    image = args.image.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError('Wrong kernel Image')
    sys.path.insert(0, str(args.software))
    from host_load import capture_snapshot, read_debug, COMMAND
    from host_transport import Operation, VivadoTransport

    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(memory_writes=False, reset=False, cpu_halt=False, reads=[], pages=[],
                  image_sha256=IMAGE_SHA256, evidence_verified=False,
                  limitations=['Page tables in memory, not live SATP/TLB',
                               'Head PC has no validity bit',
                               'JTAG reads themselves contribute DDR traffic'])

    def save():
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        with VivadoTransport(args.out / 'transport', probes=args.probes,
                             vivado=args.vivado) as t:
            def read(pa, n):
                if pa % 8 or n % 8 or not 0x80000000 <= pa < pa + n <= 0x100000000:
                    raise ValueError('Unreviewed memory read: ' + hex(pa))
                data = b''
                for start in range(0, n, 1024):
                    data += b''.join(t.exchange([Operation('M', 'READ', pa + i)
                                                for i in range(start, min(start + 1024, n), 8)]))
                if len(data) != n:
                    raise ValueError('Short memory read')
                report['reads'].append(dict(pa=hex(pa), data=data.hex()))
                save()
                return data

            def word(pa):
                return struct.unpack('<Q', read(pa, 8))[0]

            report['counter_frozen_before'] = read_debug(t, [COMMAND])[0]
            report['before'] = capture_snapshot(t)
            if report['counter_frozen_before'] or report['before']['watchdog_snapshot']:
                raise ValueError('Counters frozen; stationary values cannot prove a stall')
            if report['before']['core']['retired'] != args.expected_retired:
                raise ValueError('Execution changed; preserve scene and re-evaluate')
            time.sleep(2)
            report['second'] = capture_snapshot(t)
            if progress_key(report['before']) != progress_key(report['second']):
                raise ValueError('Execution progressed; this probe requires a stable scene')
            # Pinned task_curr, task->mm, mm->pgd and proc_task_name instructions.
            for offset, size in ((0x5e5c8, 48), (0x23098, 16),
                                 (0x20538, 16), (0x305b78, 16)):
                if read(0x80200000 + offset, size) != image[offset:offset + size]:
                    raise ValueError('Live kernel instruction mismatch')
            per_cpu = word(physical(0xffffffff81a61620))
            curr = (per_cpu + 0xffffffff80e48940 + 0xa80) & ((1 << 64) - 1)
            task = word(physical(curr))
            task_data = read(physical(task), 4096)
            (args.out / 'task.bin').write_bytes(task_data)
            mm = struct.unpack_from('<Q', task_data, 0x438)[0]
            pgd = word(physical(mm) + 104)
            report.update(task_va=hex(task), mm_va=hex(mm), pgd_va=hex(pgd),
                          task_comm=task_data[1696:1760].split(b'\0', 1)[0].decode('ascii'),
                          per_cpu_offset=hex(per_cpu), curr_va=hex(curr))

            def page(va, label):
                pa, entries = translate(word, physical(pgd), va)
                code = read(pa & ~4095, 4096)
                path = args.out / (label + '.bin')
                path.write_bytes(code)
                report['pages'].append(dict(label=label, requested_va=hex(va),
                                            code_va=hex(va & ~4095), pa=hex(pa),
                                            page_walk=entries,
                                            sha256=hashlib.sha256(code).hexdigest()))
                return code

            pc = report['before']['core']['last_pc']
            code = page(pc, 'retired_page')
            offset = pc & 4095
            if offset > 4092:
                raise ValueError('Instruction crosses captured page')
            instruction = struct.unpack_from('<I', code, offset)[0]
            report['last_instruction'] = hex(instruction)
            if instruction & 0x7f == 0x6f:
                target = jal_target(pc, instruction)
                report['jal_target'] = hex(target)
                page(target, 'target_page')
            if args.context:
                # These are memory snapshots, not current CPU registers or a
                # record of which master issued the last AXI write.
                pte_lines = sorted({int(entry['pa'], 16) & ~31
                                    for item in report['pages']
                                    for entry in item['page_walk']})
                report['pte_cache_lines'] = [dict(pa=hex(addr), data=read(addr, 32).hex())
                                             for addr in pte_lines]
                kernel_sp = struct.unpack_from('<Q', task_data, 0x10)[0]
                report['saved_kernel_sp_candidate'] = hex(kernel_sp)
                if not 0xffffffc000000000 <= kernel_sp < 0xffffffd600000000 or kernel_sp % 4096:
                    raise ValueError('Saved kernel stack pointer outside reviewed VMAP range')
                stack = page(kernel_sp - 512, 'saved_kernel_stack_page')
                if read(0x80200000 + 0xb93978, 96) != image[0xb93978:0xb939d8]:
                    raise ValueError('Live user-return instructions differ from Image')
                saved = saved_user_context(stack)
                report['historical_user_context'] = {k: hex(v) for k, v in saved.items()}
                report['limitations'].append('Saved user context is not current register state')
                page(saved['sp'], 'saved_user_stack_page')
                last_aw = report['before']['ddr1']['last_aw_addr']
                (args.out / 'last_aw_page.bin').write_bytes(read(last_aw & ~4095, 4096))
                report['last_aw_page_pa'] = hex(last_aw & ~4095)
                (args.out / 'mm.bin').write_bytes(read(physical(mm), 1024))
            repeat_task = read(physical(task), 4096)
            report['task_unchanged'] = repeat_task == task_data
            report['after'] = capture_snapshot(t)
            report['counter_frozen_after'] = read_debug(t, [COMMAND])[0]
            if progress_key(report['before']) != progress_key(report['after']):
                raise ValueError('Execution changed during observation')
            if report['counter_frozen_after'] or report['after']['core']['cycles'] <= report['before']['core']['cycles']:
                raise ValueError('Counters stopped during observation')
            if not report['task_unchanged']:
                raise ValueError('Task changed during observation')
            read_ops = sum(len(bytes.fromhex(row['data'])) // 8 for row in report['reads'])
            delta = report['after']['ddr1']['ar_count'] - report['before']['ddr1']['ar_count']
            report.update(diagnostic_read_ops=read_ops, ddr_ar_delta=delta,
                          diagnostic_reads_explain_ar_delta=(read_ops == delta),
                          evidence_verified=True)
    except Exception as exc:
        report['cleanup_error' if report['evidence_verified'] else 'error'] = str(exc)
        raise
    finally:
        save()
        print(json.dumps({k: v for k, v in report.items() if k != 'reads'}, indent=2))


if __name__ == '__main__':
    main()
