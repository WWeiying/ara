"""Original metadata workload with a subshell-local core limit, no ptrace."""
import base64
import hashlib
import re
import struct

from linux_stability_matrix import process_case
from linux_stability import has_kernel_fault


def core_segments(header):
    if header[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Not a little-endian ELF64 core')
    if struct.unpack_from('<HH', header, 16) != (4, 243):
        raise ValueError('Not a RISC-V ET_CORE')
    start = struct.unpack_from('<Q', header, 32)[0]
    size, count = struct.unpack_from('<HH', header, 54)
    if size != 56 or count == 0 or start+size*count > len(header):
        raise ValueError('Core program headers exceed captured header')
    return [struct.unpack_from('<IIQQQQQQ', header, start+i*size) for i in range(count)]


def global_file_offset(header, address, length):
    matches = [p[2]+address-p[3] for p in core_segments(header)
               if p[0] == 1 and p[3] <= address and address+length <= p[3]+p[5]]
    if len(matches) != 1:
        raise ValueError('Global is not uniquely present in saved core bytes')
    return matches[0]


def collect_saved(line, receive, report, out, path):
    if not re.fullmatch(r'/tmp/[a-zA-Z0-9_/-]+/core', path):
        raise ValueError('Only a diagnostic tmpfs core path is accepted')
    report.update(scope='saved_core_read_only_no_new_workload', core_path=path,
                  state='reading_core_header')

    def read_blocks(count):
        line(f"printf '\\nSAVED_CORE_BEGIN\\n'; dd if={path} bs=4096 count={count} 2>/dev/null | base64; printf '\\nSAVED_CORE_END\\n'")
        match = receive(rb'(?:^|[\r\n])SAVED_CORE_BEGIN[\r\n]+([\s\S]*?)SAVED_CORE_END[\r\n]', 180)
        return base64.b64decode(re.sub(rb'\s+', b'', match[1]), validate=True)

    header = read_blocks(1)
    (out/'core_header.bin').write_bytes(header)
    segments = core_segments(header)
    required = max(p[2]+p[5] for p in segments if p[5])
    if required > 2*1024*1024:
        raise ValueError('Core exceeds this small diagnostic transfer limit')
    report.update(core_required_bytes=required, state='reading_core_segments')
    data = read_blocks((required+4095)//4096)
    if len(data) < required:
        raise ValueError('Core truncated before last program segment')
    (out/'core.elf').write_bytes(data)
    report.update(passed=True, state='core_saved_not_a_test_pass',
                  core_sha256=hashlib.sha256(data).hexdigest(), core_bytes=len(data))


def run(line, receive, report, data, out, tag, rounds, seconds):
    report.update(scope='original_metadata_with_local_core_limit_no_ptrace',
                  core_limit_bytes=16*1024*1024, state='core_preflight')
    # Do not change a machine-wide core handler or overwrite an old core.
    line("IFS= read -r pat < /proc/sys/kernel/core_pattern; printf '\\nCORE_PATTERN:%s\\n' \"$pat\"")
    m = receive(rb'(?:^|[\r\n])CORE_PATTERN:([^\r\n]*)[\r\n]', 20)
    if m[1] != b'core':
        raise ValueError('Nondefault core handler; no workload attempted')
    line("IFS= read -r usepid < /proc/sys/kernel/core_uses_pid; printf '\\nCORE_PID:%s\\n' \"$usepid\"")
    m = receive(rb'(?:^|[\r\n])CORE_PID:([^\r\n]*)[\r\n]', 20)
    if m[1] != b'0':
        raise ValueError('Unexpected core filename policy; no workload attempted')
    work = '/tmp/ara_metadata_core_'+tag
    command = list(process_case(work, 'metadata', rounds))[1][1]
    report.update(work=work, command=command, state='metadata_testing')
    start = len(data)
    line(f"( set -e; mkdir {work}; cd {work}; ulimit -c 16384; {command} ); r=$?; printf '\\nCORE_TEST:%s\\n' \"$r\"")
    result = receive(rb'(?:^|[\r\n])CORE_TEST:([0-9]+)[\r\n]', seconds)
    output = bytes(data[start:])
    report.update(exit_code=int(result[1]), state='metadata_finished')
    fault = re.search(rb'unhandled signal 11[^\r\n]*ld-linux-riscv64-lp64d.so.1\[11c4c,([0-9a-f]+)\+', output)
    report['kernel_fault_reported'] = has_kernel_fault(output.decode(errors='replace'))
    report['passed'] = report['exit_code'] == 0 and not report['kernel_fault_reported']
    if report['passed']:
        return
    if not fault:
        report['error'] = 'Workload failed without the reviewed loader fault; scene retained'
        return
    base = int(fault[1], 16)
    report['loader_base'] = hex(base)
    core = work+'/core'

    def read_core(offset, length, label):
        if not 0 <= offset < offset+length <= 16*1024*1024 or length > 4096:
            raise ValueError('Core read outside diagnostic bounds')
        line(f"printf '\\nCORE_DATA_BEGIN\\n'; dd if={core} bs=1 skip={offset} count={length} 2>/dev/null | base64; printf '\\nCORE_DATA_END\\n'")
        match = receive(rb'(?:^|[\r\n])CORE_DATA_BEGIN[\r\n]+([\s\S]*?)CORE_DATA_END[\r\n]', 60)
        blob = base64.b64decode(re.sub(rb'\s+', b'', match[1]), validate=True)
        if len(blob) != length:
            raise ValueError('Truncated core read')
        (out/label).write_bytes(blob)
        report.setdefault('core_reads', []).append(dict(offset=offset, bytes=length,
                 file=label, sha256=hashlib.sha256(blob).hexdigest()))
        return blob

    report['state'] = 'reading_saved_core'
    header = read_core(0, 4096, 'core_header.bin')
    offset = global_file_offset(header, base+0x22ca0, 32)
    block = read_core(offset, 32, 'loader_globals.bin')
    report['saved_dl_argv'] = hex(struct.unpack_from('<Q', block, 24)[0])
    report['state'] = 'core_globals_captured_needs_review'
    report['error'] = 'Original fault reproduced; saved core is post-fault evidence, not an RTL waveform'
