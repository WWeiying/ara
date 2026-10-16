"""Bounded BusyBox coverage on the original image, not ISA/whole-RAM signoff."""
import hashlib

PROFILES = ('storage', 'process', 'compute', 'timers')
REMAINING_PROCESS_CASES = ('pipes', 'metadata', 'links_permissions', 'fifo',
                           'parallel_wait', 'signal_term', 'cleanup')
GAPS = ['dedicated RVV instruction/context tests', 'pthread/futex contention',
        'dedicated LR/SC and AMO tests', 'full physical RAM/address-bit coverage',
        'second DDR channel', 'Linux Ethernet driver/network stress',
        'external SD/USB/PCIe peripherals', 'long-duration reliability']


def zero_digest(size):
    h = hashlib.sha256()
    block = bytes(65536)
    while size:
        chunk = block[:min(size, len(block))]
        h.update(chunk)
        size -= len(chunk)
    return h.hexdigest()


def process_case(work, name, repetitions=200):
    """Run one previously unstarted case with fresh, separately counted fixtures."""
    if name not in REMAINING_PROCESS_CASES:
        raise ValueError('Not a remaining process case')
    original = {s[0]: s for s in matrix(work, 'process', repetitions)}
    yield 'case_setup', f'mkdir {work}', 30, None
    yield original[name]
    if name != 'cleanup':
        _, command, timeout, oracle = original['cleanup']
        yield 'case_teardown', command, timeout, oracle


def isolated_case(work, profile, name, repetitions=200):
    """Keep the original target command/oracle; prepare dependencies separately."""
    steps = {s[0]: s for s in matrix(work, profile, repetitions)}
    if name not in steps:
        raise ValueError('Unknown matrix case')
    if name not in ('baseline', 'capabilities', 'mkdir'):
        yield 'fixture_mkdir', f'mkdir {work}', 30, None
    if profile == 'storage' and (name.startswith('offset_') or name == 'remove_data'):
        yield ('fixture_random', f'dd if=/dev/urandom of={work}/a bs=65536 count=128; '
               f'cp {work}/a {work}/b; cmp {work}/a {work}/b', 240, None)
    if profile == 'compute' and name in ('base64', 'compression', 'tar_roundtrip', 'remove_pattern'):
        _, command, timeout, oracle = steps['pattern_oracle']
        yield 'fixture_pattern', command, timeout, oracle
    yield steps[name]
    if name not in ('baseline', 'capabilities', 'cleanup'):
        yield 'fixture_cleanup', f'rm -rf {work}', 45, None


def matrix(work, profile, repetitions=100):
    if profile not in PROFILES or not 1 <= repetitions <= 500:
        raise ValueError('Invalid bounded matrix configuration')
    yield 'baseline', 'uname -a; cat /proc/uptime; cat /proc/meminfo; cat /proc/interrupts; dmesg | tail -n 12', 45, None
    apps = {
        'storage': 'dd sha256sum cmp cp rm mkdir rmdir',
        'process': 'sh cat mv rm ln readlink chmod mkfifo wc sleep kill',
        'compute': 'awk sort uniq seq gzip gunzip base64 cmp tar sha256sum',
        'timers': 'sleep cat sha256sum dd rm',
    }[profile]
    yield 'capabilities', f'for a in {apps}; do command -v "$a" >/dev/null; done', 30, None
    yield 'mkdir', f'mkdir {work}; cd {work}', 30, None
    if profile == 'storage':
        for size in (0, 1, 7, 8, 63, 64, 65, 511, 512, 513, 4095, 4096, 4097, 65535, 65536, 65537, 1048576):
            write = f'dd if=/dev/zero of={work}/z bs={max(size, 1)} count={int(size != 0)}'
            yield f'bytes_{size}', f'{write}; sha256sum {work}/z; rm {work}/z', 60, ('sha256', zero_digest(size), work+'/z')
        for mib in (8, 32, 64):
            yield f'ram_file_{mib}MiB', f'dd if=/dev/zero of={work}/z bs=1048576 count={mib}; sha256sum {work}/z; rm {work}/z; head -n 8 /proc/meminfo', 360, ('sha256', zero_digest(mib*1048576), work+'/z')
        yield 'random_8MiB', f'dd if=/dev/urandom of={work}/a bs=65536 count=128; cp {work}/a {work}/b; cmp {work}/a {work}/b; sha256sum {work}/a {work}/b', 240, 'random'
        for offset in (1, 7, 63, 4093, 4095, 4096, 65533):
            yield f'offset_{offset}', f'dd if={work}/a of={work}/s bs=1 skip={offset} count=8195; dd if={work}/b of={work}/t bs=1 skip={offset} count=8195; cmp {work}/s {work}/t; rm {work}/s {work}/t', 90, None
        yield 'remove_data', f'rm {work}/a {work}/b', 30, None
    elif profile == 'process':
        yield 'subshell_exit', 'set +e; (exit 7); r=$?; set -e; test "$r" -eq 7', 30, None
        yield 'environment', f'n=0; export ARA_ENV=expected; while [ $n -lt {repetitions} ]; do sh -c \'test "$ARA_ENV" = expected\'; n=$((n+1)); done', 300, None
        yield 'exec_loader', f'n=0; while [ $n -lt {repetitions} ]; do /bin/busybox true; n=$((n+1)); done', 300, None
        # On the 50 MHz board, the unchanged 200-loop workload takes 409 s.
        # Keep the full correctness workload and allow measured runtime margin.
        yield 'pipes', f'n=0; while [ $n -lt {repetitions} ]; do test "$(printf abc | cat | wc -c)" -eq 3; n=$((n+1)); done', max(300, 3 * repetitions), None
        yield 'metadata', f'n=0; while [ $n -lt {repetitions} ]; do printf "%s\\n" "$n" > {work}/f; mv {work}/f {work}/g; test "$(cat {work}/g)" = "$n"; rm {work}/g; n=$((n+1)); done', 300, None
        yield 'links_permissions', f'printf abc > {work}/f; ln {work}/f {work}/hard; ln -s f {work}/soft; chmod 600 {work}/f; test "$(readlink {work}/soft)" = f; rm {work}/f; test "$(cat {work}/hard)" = abc; test ! -e {work}/soft; rm {work}/hard {work}/soft', 60, None
        yield 'fifo', f'mkfifo {work}/fifo; cat {work}/fifo > {work}/out & p=$!; printf abc > {work}/fifo; wait $p; test "$(cat {work}/out)" = abc; rm {work}/fifo {work}/out', 45, None
        yield 'parallel_wait', 'sh -c "exit 3" & p=$!; sh -c "exit 5" & q=$!; set +e; wait $p; a=$?; wait $q; b=$?; set -e; test "$a" -eq 3; test "$b" -eq 5', 45, None
        yield 'signal_term', 'sleep 30 & p=$!; kill -TERM $p; set +e; wait $p; r=$?; set -e; test "$r" -eq 143', 45, None
    elif profile == 'compute':
        yield 'integer64', 'test "$((2147483647+1))" = 2147483648; test "$((4294967296*3+7))" = 12884901895; test "$((-1234567/89))" = -13871; test "$(((1<<40)>>20))" = 1048576', 30, None
        yield 'integer_loop', 'n=1; s=0; while [ $n -le 5000 ]; do s=$((s+n)); n=$((n+1)); done; test "$s" -eq 12502500', 90, None
        yield 'awk_float', "awk 'BEGIN {s=0; for(i=0;i<10000;i++) s+=0.125; if(s!=1250 || 1.5*2.5!=3.75) exit 1; print \"FLOAT_OK\"}'", 45, ('text', 'FLOAT_OK')
        pattern = ''.join(f'{i:04d}\n' for i in range(4096)).encode()
        yield 'pattern_oracle', f"awk 'BEGIN {{for(i=0;i<4096;i++) printf \"%04d\\n\",i}}' > {work}/p; sha256sum {work}/p", 60, ('sha256', hashlib.sha256(pattern).hexdigest(), work+'/p')
        yield 'sort_numeric', f'seq 1000 -1 1 > {work}/a; sort -n {work}/a > {work}/b; seq 1 1000 > {work}/c; cmp {work}/b {work}/c; rm {work}/a {work}/b {work}/c', 90, None
        yield 'base64', f'base64 {work}/p > {work}/enc; base64 -d {work}/enc > {work}/dec; cmp {work}/p {work}/dec; rm {work}/enc {work}/dec', 60, None
        yield 'compression', f'gzip -c {work}/p > {work}/z; gunzip -c {work}/z > {work}/d; cmp {work}/p {work}/d; rm {work}/z {work}/d', 90, None
        yield 'tar_roundtrip', f'mkdir {work}/unpack; tar -cf {work}/p.tar -C {work} p; tar -xf {work}/p.tar -C {work}/unpack; cmp {work}/p {work}/unpack/p; rm {work}/unpack/p {work}/p.tar; rmdir {work}/unpack', 90, None
        yield 'remove_pattern', f'rm {work}/p', 30, None
    else:
        for group in range(4):
            yield f'short_sleep_{group}', 'cat /proc/uptime; n=0; while [ $n -lt 10 ]; do sleep 1; n=$((n+1)); done; cat /proc/uptime; cat /proc/interrupts', 60, None
            yield f'load_after_idle_{group}', f'dd if=/dev/zero of={work}/z bs=1048576 count=8; sha256sum {work}/z; rm {work}/z', 120, ('sha256', zero_digest(8*1048576), work+'/z')
        yield 'idle_60s', 'cat /proc/uptime; sleep 60; cat /proc/uptime; cat /proc/interrupts', 100, None
    yield 'cleanup', f'rmdir {work}; head -n 8 /proc/meminfo; dmesg | tail -n 40; ps', 45, None
