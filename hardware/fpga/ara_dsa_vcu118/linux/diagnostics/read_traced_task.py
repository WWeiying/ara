"""Read a ptrace-stopped task through JTAG, without reset, halt or memory writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from read_current_restore import physical, IMAGE_HASH
from read_stalled_task import translate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('software', 'image', 'probes', 'trace', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--vivado', required=True)
    a = p.parse_args()
    image = a.image.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_HASH:
        raise ValueError('Wrong kernel Image')
    trace = a.trace.read_text().replace('\r', '')
    if trace.count('TRACE_FAULT') != 1 or 'TRACE_HOLDING' not in trace:
        raise ValueError('Expected one retained fault')
    tail = trace.split('TRACE_FAULT\n', 1)[1]
    pid = int(re.search(r'^pid=(0x[0-9a-f]+)$', tail, re.M)[1], 16)
    values = {int(m[0], 16): int(m[1], 16) for m in re.findall(
        r'^PEEK (0x[0-9a-f]+) ret=0x0000000000000000 data=(0x[0-9a-f]+)$', tail, re.M)}
    pfns = {int(va, 16) >> 12: int(entry, 16) for va, entry in re.findall(
        r'^PAGEMAP (0x[0-9a-f]+) ret=0x0000000000000008 entry=(0x[0-9a-f]+)$', tail, re.M)}
    if not values or not pfns or any(not entry & (1 << 63) for entry in pfns.values()):
        raise ValueError('Missing or absent pagemap evidence')
    sys.path.insert(0, str(a.software))
    from host_load import capture_snapshot
    from host_transport import Operation, VivadoTransport
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(reset=False, memory_writes=False, cpu_halt=False, pid=pid,
                  image_sha256=IMAGE_HASH, tasks=[], reads=[], pages=[], verified=False,
                  scope='JTAG AXI/LLC memory and saved page tables, not live CPU TLB')

    def save():
        (a.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    try:
        with VivadoTransport(a.out/'transport', vivado=a.vivado, probes=a.probes) as t:
            def read(pa, size):
                if pa % 8 or size % 8 or not 0x80000000 <= pa < pa+size <= 0x100000000:
                    raise ValueError('Read outside reviewed DDR range')
                data = b''
                for start in range(0, size, 1024):
                    data += b''.join(t.exchange([Operation('M', 'READ', pa+i)
                        for i in range(start, min(start+1024, size), 8)]))
                if len(data) != size:
                    raise ValueError('Short JTAG read')
                report['reads'].append(dict(pa=hex(pa), data=data.hex()))
                save()
                return data

            def word(pa):
                return struct.unpack('<Q', read(pa, 8))[0]

            report['before'] = capture_snapshot(t)
            # show_state_filter: init_task=...8180e1c0, tasks at +1000.
            # sched_show_task: pid at +1208; established mm->pgd at +104.
            for offset, size in ((0x60b68, 32), (0x5a538, 16), (0x23098, 16), (0x20538, 16)):
                if read(0x80200000+offset, size) != image[offset:offset+size]:
                    raise ValueError('Live kernel does not match structure-layout oracle')
            head = 0xffffffff8180e1c0
            task, seen = head, set()
            for _ in range(256):
                if task in seen:
                    raise ValueError('Retained PID not found in task list')
                seen.add(task)
                pa = physical(task)
                ident = read(pa+1208, 8)
                task_pid, tgid = struct.unpack('<2I', ident)
                comm = read(pa+1696, 16).split(b'\0', 1)[0].decode('ascii')
                report['tasks'].append(dict(va=hex(task), pid=task_pid, tgid=tgid, comm=comm))
                if task_pid == pid:
                    break
                task = word(pa+1000)-1000
            else:
                raise ValueError('Task-list traversal limit reached')
            state = word(pa+72) & 0xffffffff
            if state != 8:
                raise ValueError('Task is not TASK_TRACED; no user memory inspection')
            mm = word(pa+0x438)
            pgd = word(physical(mm)+104)
            report.update(task_va=hex(task), mm_va=hex(mm), pgd_va=hex(pgd), task_state=state)
            (a.out/'task.bin').write_bytes(read(pa, 4096))
            (a.out/'mm.bin').write_bytes(read(physical(mm), 1024))
            comparisons = []
            for vpn in sorted({va >> 12 for va in values}):
                addr, walk = translate(word, physical(pgd), vpn << 12)
                if vpn in pfns and addr >> 12 != (pfns[vpn] & ((1 << 55)-1)):
                    raise ValueError('JTAG page walk disagrees with stopped-task pagemap')
                data = read(addr, 4096)
                stable = data == read(addr, 4096)
                label = f'page_{vpn:x}.bin'
                (a.out/label).write_bytes(data)
                report['pages'].append(dict(va=hex(vpn << 12), pa=hex(addr), walk=walk,
                    stable=stable, file=label, sha256=hashlib.sha256(data).hexdigest()))
                for va, value in values.items():
                    if va >> 12 != vpn:
                        continue
                    observed = struct.unpack_from('<Q', data, va & 4095)[0]
                    comparisons.append(dict(va=hex(va), ptrace=hex(value), jtag=hex(observed),
                                            matches=value == observed))
            report['comparisons'] = comparisons
            report['identity_stable'] = (read(pa+1208, 8) == ident and
                word(pa+0x438) == mm and (word(pa+72) & 0xffffffff) == 8)
            report['after'] = capture_snapshot(t)
            report['verified'] = (report['identity_stable'] and
                all(x['stable'] for x in report['pages']) and all(x['matches'] for x in comparisons))
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        save()
        print(json.dumps({k:v for k,v in report.items() if k != 'reads'}, indent=2))


if __name__ == '__main__':
    main()
