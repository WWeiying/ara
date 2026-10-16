"""Bounded upstream stress tools; successful execution is not exhaustive ISA coverage."""
import hashlib
import re
from linux_stability import validate
from linux_stability_matrix import matrix

TOOLS = '/opt/ara-tests'
STRESSORS = {
    'atomic_threads': {'atomic': '', 'futex': '', 'pthread': '--pthread-max 8',
                       'sem': '', 'sem-sysv': '', 'switch': ''},
    'virtual_memory': {'mmap': '--mmap-bytes 32M', 'mprotect': '', 'fault': '',
                       'vm': '--vm-bytes 64M --vm-keep', 'brk': '',
                       'stack': '--stack-fill'},
    'ipc_signals': {'fork': '--fork-max 8', 'vfork': '--vfork-max 8',
                    'pipe': '', 'fifo': '',
                    'sigq': '', 'sigfd': '', 'poll': '', 'epoll': '',
                    'timer': '', 'timerfd': '', 'clock': ''},
    'arithmetic': {'cpu': '--cpu-method all', 'intmath': '', 'fp': '',
                   'memcpy': '', 'bsearch': '', 'hsearch': ''},
}
PROFILES = ('regression', *STRESSORS, 'memory_patterns', 'rvv_context',
            'soak4h', 'soak24h', 'boot_smoke')
DEFERRED = {
    'dual_ddr': 'Current bitstream has one DDR channel; needs separately accepted dual-DDR image.',
    'physical_address_coverage': 'User-space allocations cannot certify every physical RAM address.',
    'linux_network': 'J10 loader is not a Linux network device; no live-Linux network stress claimed.',
    'peripherals': 'SD/USB/PCIe need connected devices and kernel drivers.',
    'power_cycles': 'FPGA reprogram/reboot is not a physical power cycle.',
    'exhaustive_ISA': 'RVV context and stress tools do not replace ISA/conformance regression.',
}


def stress_step(name, options='', seconds=180, label=None):
    command = (f'{TOOLS}/stress-ng --{name} 1 {options} --verify --metrics-brief '
               f'--timeout {seconds}s --oomable --oom-avoid --oom-avoid-bytes 256M')
    return label or name, command, seconds+180, ('stress', [name])


def extended_plan(work, profile, reference=False):
    if profile not in PROFILES:
        raise ValueError('Unknown extended profile')
    if profile == 'regression':
        # Four independent batches exercise the original loader/cat/copy paths.
        for batch in range(1 if reference else 4):
            for n, c, t, k in matrix(work+f'_{batch}', 'process', 3 if reference else 250):
                yield f'batch{batch}_{n}', c, max(t, 900) if not reference else t, k
            count = 3 if reference else 250
            copy = work+f'_copy{batch}'
            digest = hashlib.sha256(''.join(f'{i:04d}\n' for i in range(4096)).encode()).hexdigest()
            yield f'batch{batch}_copy_compare', (f'mkdir {copy}; '
                  f"awk 'BEGIN {{for(i=0;i<4096;i++) printf \"%04d\\n\",i}}' > {copy}/a; "
                  f'n=0; while [ $n -lt {count} ]; do cp {copy}/a {copy}/b; '
                  f'cmp {copy}/a {copy}/b; n=$((n+1)); done; '
                  f'sha256sum {copy}/b; rm {copy}/a {copy}/b; rmdir {copy}'), 900, ('sha256', digest, copy+'/b')
        return
    yield 'baseline', 'uname -a; cat /proc/cpuinfo; cat /proc/meminfo; cat /proc/interrupts', 60, None
    if profile in STRESSORS:
        for name, options in STRESSORS[profile].items():
            yield stress_step(name, options, 3 if reference else 180)
    elif profile == 'memory_patterns':
        for mib, loops in ((1, 1),) if reference else ((32, 2), (128, 2), (256, 1)):
            # Reserve at least 256 MiB for the kernel and other resident processes.
            command = ("free=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo); "
                       f'test "$free" -gt {(mib+256)*1024}; '
                       f'{TOOLS}/memtester {mib}M {loops}')
            yield f'memtester_{mib}MiB_{loops}', command, 180 if reference else 14400, ('memtester', mib, loops)
    elif profile == 'rvv_context':
        for i in range(1 if reference else 30):
            yield f'rvv_{i:02}', f'{TOOLS}/rvv_linux_smoke', 180, ('rvv',)
    elif profile in ('soak4h', 'soak24h'):
        for i in range(1 if reference else (48 if profile == 'soak4h' else 288)):
            seconds = 3 if reference else 300
            yield (f'mixed_{i:03}', f'{TOOLS}/stress-ng --cpu 1 --cpu-method int64 '
                   '--vm 1 --vm-bytes 64M --vm-keep --futex 1 --pthread 1 --pthread-max 4 '
                   f'--verify --metrics-brief --timeout {seconds}s '
                   '--oomable --oom-avoid --oom-avoid-bytes 256M', seconds+180,
                   ('stress', ['cpu', 'vm', 'futex', 'pthread']))
            yield f'health_{i:03}', 'cat /proc/uptime; head -n 8 /proc/meminfo; dmesg | tail -n 40', 60, None
    else:
        yield 'copy_hash', (f'mkdir {work}; printf ara_boot_check > {work}/a; '
                           f'cp {work}/a {work}/b; cmp {work}/a {work}/b; '
                           f'test "$(cat {work}/b)" = ara_boot_check; '
                           f'rm {work}/a {work}/b; rmdir {work}'), 90, None
    yield 'kernel_health', 'dmesg; cat /proc/interrupts; cat /proc/meminfo', 90, None


def validate_extended(kind, output, work):
    validate(None, output, work)
    text = output.replace('\r', '')
    if re.search(r'(?m)^\[\s*\d+\.\d+\].*(?:Out of memory:|oom-kill:|soft lockup|rcu.*stall)', text):
        raise ValueError('Kernel resource/forward-progress failure')
    if kind and kind[0] == 'stress':
        if 'successful run completed' not in text:
            raise ValueError('No successful upstream stress-ng completion')
        if re.search(r'(?:skipped|failed|metrics untrustworthy):\s*[1-9]', text):
            raise ValueError('Skipped/failed stressors are not a pass')
        for name in kind[1]:
            matches = re.findall(r'(?m)^stress-ng: metrc:\s*\[\d+\]\s*'+re.escape(name)+r'\s+(\d+)\s', text)
            if not matches or max(map(int, matches)) == 0:
                raise ValueError('No completed bogo operations for '+name)
    elif kind and kind[0] == 'memtester':
        mib, loops = kind[1:]
        if f'got  {mib}MB ({mib*1048576} bytes)' not in text or 'Done.' not in text:
            raise ValueError('Memtester allocation reduced or incomplete')
        for i in range(1, loops+1):
            if f'Loop {i}/{loops}:' not in text:
                raise ValueError('Missing memory-pattern loop')
        if 'FAILURE:' in text:
            raise ValueError('Memory pattern mismatch')
    elif kind and kind[0] == 'rvv':
        for marker in ('RVV fallback userspace PASS', 'RVV context switch and fault return PASS'):
            validate(('text', marker), text, work)
    else:
        validate(kind, text, work)


def result_status(code, kind, output, work):
    if code == 4 and kind and kind[0] == 'stress' and 'not implemented' in output.lower():
        validate(None, output, work)
        return 'skipped_unsupported'
    if code:
        raise ValueError('Command exit '+str(code))
    validate_extended(kind, output, work)
    return 'passed'
