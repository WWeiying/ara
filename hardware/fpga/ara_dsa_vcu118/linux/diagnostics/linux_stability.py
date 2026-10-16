"""Bounded scalar Linux tests; preserve the running board on any failure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid


def plan(work, rounds):
    yield 'baseline', 'uname -a; cat /proc/uptime; head -n 8 /proc/meminfo; cat /proc/interrupts', 30, None
    yield 'mkdir', f'mkdir {work}', 30, None
    for i in range(rounds):
        prefix = f'round{i + 1}_'
        yield prefix+'random', f'dd if=/dev/urandom of={work}/a bs=65536 count=32; cp {work}/a {work}/b; cmp {work}/a {work}/b; sha256sum {work}/a {work}/b', 120, 'random'
        yield prefix+'zero', f'dd if=/dev/zero of={work}/z bs=1048576 count=8; sha256sum {work}/z', 120, 'zero'
        yield prefix+'offset', f'dd if={work}/a of={work}/slice bs=1 skip=4093 count=8195; dd if={work}/b of={work}/slice2 bs=1 skip=4093 count=8195; cmp {work}/slice {work}/slice2', 90, None
        yield prefix+'pipes', 'n=0; while [ $n -lt 30 ]; do test "$(printf abc | wc -c)" -eq 3; n=$((n+1)); done', 90, None
        yield prefix+'parallel', f'sha256sum {work}/a > {work}/h1 & p=$!; sha256sum {work}/a > {work}/h2 & q=$!; wait $p; wait $q; cmp {work}/h1 {work}/h2', 90, None
        yield prefix+'metadata', f'n=0; while [ $n -lt 30 ]; do printf "%s\\n" "$n" > {work}/f; mv {work}/f {work}/g; test "$(cat {work}/g)" = "$n"; rm {work}/g; n=$((n+1)); done', 90, None
        yield prefix+'timers', 'cat /proc/uptime; n=0; while [ $n -lt 5 ]; do sleep 1; n=$((n+1)); done; cat /proc/uptime; cat /proc/interrupts', 45, None
        yield prefix+'reclaim', f'rm {work}/a {work}/b {work}/z {work}/slice {work}/slice2 {work}/h1 {work}/h2; head -n 8 /proc/meminfo', 30, None
    yield 'idle_wakeup', 'cat /proc/uptime; sleep 30; cat /proc/uptime', 60, None
    yield 'cleanup', f'rmdir {work}; dmesg | tail -n 40; ps', 30, None


def has_kernel_fault(output):
    return bool(re.search(
        r'(?m)^\[\s*\d+\.\d+\].*(?:BUG:|Oops:|Kernel panic|'
        r'unhandled signal (?:7|11)\b|bad (?:pgd|p4d|pud|pmd|pte)\b)',
        output.replace('\r', '')))


def validate(kind, output, work):
    # PTYs may add CR to the guest's CRLF; compare result lines, not transport EOLs.
    output = output.replace('\r', '')
    if has_kernel_fault(output):
        raise ValueError('Kernel fault reported; preserve board for diagnosis')
    if isinstance(kind, tuple):
        if kind[0] == 'sha256':
            if not re.search(r'(?m)^'+kind[1]+r'\s+'+re.escape(kind[2])+r'\r?$', output):
                raise ValueError('Host SHA256 oracle mismatch')
        elif kind[0] == 'text':
            if not re.search(r'(?m)^'+re.escape(kind[1])+r'\r?$', output):
                raise ValueError('Expected result line absent')
        else:
            raise ValueError('Unknown oracle')
    if kind == 'zero':
        expected = hashlib.sha256(bytes(8 * 1024 * 1024)).hexdigest()
        if not re.search(r'(?m)^'+expected+r'\s+'+re.escape(work+'/z')+r'\r?$', output):
            raise ValueError('Zero file differs from host SHA256 oracle')
    if kind == 'random':
        found = {}
        for digest, name in re.findall(r'(?m)^([a-f0-9]{64})\s+(\S+)\r?$', output):
            found[name] = digest
        if work+'/a' not in found or found.get(work+'/a') != found.get(work+'/b'):
            raise ValueError('Missing or unequal random file hashes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--serial-wheel', type=Path, required=True)
    parser.add_argument('--port', default='COM6')
    parser.add_argument('--rounds', type=int, choices=range(1, 11), default=3)
    parser.add_argument('--profile', choices=('legacy', 'storage', 'process', 'compute', 'timers'), default='legacy')
    parser.add_argument('--repetitions', type=int, choices=range(1, 501), default=100)
    parser.add_argument('--extended-profile', help='Use pinned upstream stress/RVV suite')
    parser.add_argument('--process-case', help='Run one unstarted process case with fresh fixtures')
    parser.add_argument('--matrix-case', help='One original matrix target with independent fixtures')
    args = parser.parse_args()
    if args.matrix_case and (args.profile == 'legacy' or args.process_case or args.extended_profile):
        parser.error('--matrix-case requires a matrix profile and no other selection')
    if args.process_case and (args.extended_profile or args.profile not in ('legacy', 'process')):
        parser.error('--process-case cannot be combined with another profile')
    sys.path.insert(0, str(args.serial_wheel))
    import serial
    args.out.mkdir(parents=True, exist_ok=False)
    tag = uuid.uuid4().hex[:12]
    work = '/tmp/ara_stability_'+tag
    report = dict(passed=False, reset=False, scope='bounded_scalar_tmpfs_process_timer',
                  work=work, rounds=args.rounds, results=[], state='connecting')
    steps = list(plan(work, args.rounds))
    if args.profile != 'legacy':
        from linux_stability_matrix import matrix, GAPS
        steps = list(matrix(work, args.profile, args.repetitions))
        report['uncovered'] = GAPS
    if args.extended_profile:
        from extended_stability import extended_plan, DEFERRED
        steps = list(extended_plan(work, args.extended_profile))
        report.update(scope='extended_userspace_not_full_hardware_acceptance',
                      extended_profile=args.extended_profile, uncovered=DEFERRED)
    if args.process_case:
        from linux_stability_matrix import process_case, GAPS
        steps = list(process_case(work, args.process_case, args.repetitions))
        report.update(selected_case=args.process_case, fixture_steps=['case_setup', 'case_teardown'],
                      scope='isolated_remaining_case_not_full_process_regression', uncovered=GAPS)
    if args.matrix_case:
        from linux_stability_matrix import isolated_case
        steps = list(isolated_case(work, args.profile, args.matrix_case, args.repetitions))
        report.update(selected_case=args.matrix_case, scope='isolated_matrix_target_with_fixtures')
    report.update(profile=args.profile, repetitions=args.repetitions,
                  planned=[dict(name=n, command=c, timeout=t) for n,c,t,_ in steps])
    report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def save():
        (args.out/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    try:
        with (args.out/'uart.bin').open('wb') as log, serial.Serial(
                args.port, 115200, timeout=.2, write_timeout=5,
                rtscts=False, dsrdtr=False) as port:
            def receive(pattern, timeout):
                data = bytearray()
                deadline = time.monotonic()+timeout
                while time.monotonic() < deadline:
                    chunk = port.read(4096)
                    if chunk:
                        log.write(chunk)
                        log.flush()
                        data.extend(chunk)
                        match = pattern.search(data)
                        if match:
                            return match, data.decode(errors='replace')
                raise TimeoutError('No expected response; no further commands sent')

            port.write(b'\n')
            receive(re.compile(rb'(?:^|[\r\n])[^\r\n]*[#$] $'), 15)
            for index, (name, command, timeout, kind) in enumerate(steps):
                report['state'] = name
                save()
                print('BEGIN', name, flush=True)
                token = f'ARA_ST_{tag}_{index}'
                # A subshell retains fail-fast semantics without exiting PID 1.
                wire = f"( set -e; {command} ); printf '\\n%s:%s\\n' {token} \"$?\"\n"
                start = time.monotonic()
                result = dict(name=name, command=command, passed=False, status='running')
                report['results'].append(result)
                save()
                for byte in wire.encode('ascii'):
                    port.write(bytes([byte]))
                    time.sleep(.02)
                match, output = receive(re.compile(rb'(?:^|[\r\n])'+token.encode()+rb':([0-9]+)[\r\n]'), timeout)
                result.update(seconds=time.monotonic()-start, exit_code=int(match[1]), output=output)
                if args.extended_profile:
                    from extended_stability import result_status
                    result['status'] = result_status(result['exit_code'], kind, output, work)
                    result['passed'] = result['status'] == 'passed'
                else:
                    if result['exit_code']:
                        raise RuntimeError('Command failed: '+name)
                    validate(kind, output, work)
                    result['passed'] = True
                    result['status'] = 'passed'
                save()
                print('PASS' if result['passed'] else 'SKIP', name, round(result['seconds'], 3), flush=True)
            passed = all(r['passed'] for r in report['results'])
            report.update(passed=passed, state='passed' if passed else 'completed_with_skips')
    except Exception as exc:
        report['error'] = str(exc)
        if report['results'] and report['results'][-1].get('status') == 'running':
            report['results'][-1].update(status='failed', error=str(exc), seconds=time.monotonic()-start)
        print('FAILED', report['state'], str(exc), flush=True)
    finally:
        report['counts'] = dict(planned=len(steps), completed=len(report['results']),
                                passed=sum(r['passed'] for r in report['results']),
                                failed=sum(r.get('status') == 'failed' for r in report['results']),
                                skipped=sum(r.get('status') == 'skipped_unsupported' for r in report['results']),
                                not_run=len(steps)-len(report['results']))
        save()
    print('EVIDENCE', args.out, flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
