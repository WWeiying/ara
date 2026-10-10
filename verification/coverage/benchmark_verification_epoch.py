"""Readonly sealed-pin sample benchmark; never a report/admission qualification.

Large inputs are hash-only streamed captures, not reusable file contents. Small
JSON inputs use immutable VerificationEpoch bytes. No metadata-only live-content
cache is allowed, and no captured result may attest a later DVE filesystem read.
Two isolated workers make peak RSS comparable; warm page-cache/order effects are
explicit limitations, not a claimed full-runtime speedup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys
import time

import verification_epoch as epoch

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'verification/out/eight-policy-csv-fixed-729-agent-20261006-01'
PLAN_SHA = '744ffa4ce23553b52afc1d213c489e012ec9266b174314c663bafbec803dcd83'
MAX_JSON = 8 * 1024 * 1024
MAX_JSON_TOTAL = 16 * 1024 * 1024
CHUNK = 1024 * 1024


def require(value, message):
    if not value:
        raise epoch.EpochError(message)


def plain(value):
    if hasattr(value, 'items'):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def guard(path, pin, aliases):
    path = epoch._path(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        require(str(path) in aliases, 'Unapproved alias')
        binding = aliases[str(path)]
        require(os.readlink(path) == binding['link_target'], 'Literal alias differs')
        endpoint = epoch._path(binding['resolved'])
        require(binding['sha256'] == pin, 'Alias SHA differs')
        require(path.resolve(strict=True) == endpoint, 'Alias endpoint differs')
    else:
        require(str(path) not in aliases, 'Alias replaced')
        endpoint = path
    require(path.parent.resolve(strict=True) == path.parent, 'Aliased parent')
    require(endpoint.resolve(strict=True) == endpoint, 'Noncanonical endpoint')
    target = endpoint.lstat()
    require(stat.S_ISREG(target.st_mode), 'Nonregular endpoint')
    return str(endpoint), epoch._identity(info), epoch._identity(target)


def stream_capture(endpoint, identity):
    fd = os.open(endpoint, os.O_RDONLY | os.O_NOFOLLOW)
    digest = hashlib.sha256()
    count = 0
    with os.fdopen(fd, 'rb') as stream:
        require(epoch._identity(os.fstat(stream.fileno())) == identity, 'Changed before stream')
        while True:
            block = stream.read(CHUNK)
            if not block:
                break
            digest.update(block)
            count += len(block)
        require(epoch._identity(os.fstat(stream.fileno())) == identity, 'Changed during stream')
    require(count == identity[3], 'Stream size differs')
    return digest.hexdigest(), count


def evaluate(spec, mode):
    require(mode in ('repeated', 'capture'), 'Unknown mode')
    pins, aliases = spec['pins'], spec['aliases']
    json_paths = set(spec['json_paths'])
    require(json_paths <= set(pins), 'Unpinned JSON')
    require(type(spec['passes']) is int and spec['passes'] >= 2, 'Need repeated baseline')
    require(set(aliases) <= set(pins), 'Unpinned alias permission')
    for name, binding in aliases.items():
        require(binding['resolved'] in pins and
                pins[name] == pins[binding['resolved']] == binding['sha256'],
                'Missing/conflicting alias endpoint pin')
    small_pins = {p: pins[p] for p in json_paths}
    require(not json_paths.intersection(aliases), 'Sample JSON must be canonical')
    for path in json_paths:
        require(Path(path).stat().st_size <= MAX_JSON, 'JSON memory budget exceeded')
    require(sum(Path(p).stat().st_size for p in json_paths) <= MAX_JSON_TOTAL,
            'Total JSON capture budget exceeded')
    small = epoch.VerificationEpoch(small_pins)
    cached, snapshots, output, parsed = {}, {}, {}, {}
    reads = hashed_bytes = parses = 0
    start = time.perf_counter()
    for _ in range(spec['passes'] if mode == 'repeated' else 1):
        for path, expected in pins.items():
            epoch._sha(expected)
            before = guard(path, expected, aliases)
            endpoint, _, identity = before
            if mode == 'capture' and path in json_paths:
                value = small.json(path, expected)
                # Exercise sharing explicitly without another read/parse.
                require(small.json(path, expected) is value, 'JSON not shared')
                actual = expected
                parsed[path] = plain(value)
                reads += 1
                hashed_bytes += identity[3]
                parses += 1
            elif mode == 'capture':
                if endpoint not in cached:
                    cached[endpoint] = stream_capture(endpoint, identity)
                    reads += 1
                    hashed_bytes += cached[endpoint][1]
                    snapshots[endpoint] = identity
                require(snapshots[endpoint] == identity, 'Endpoint changed in capture')
                actual = cached[endpoint][0]
            else:
                # Mirrors existing whole-file hash reads, without retaining all
                # historical data or weakening JSON parsing between modes.
                data = Path(endpoint).read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                reads += 1
                hashed_bytes += len(data)
                if path in json_paths:
                    value = json.loads(data, object_pairs_hook=epoch._pairs,
                                       parse_constant=epoch._constant)
                    parsed[path] = plain(epoch._freeze(value))
                    parses += 1
                del data
            require(actual == expected, 'Exact expected SHA mismatch: ' + path)
            require(guard(path, expected, aliases) == before, 'Path changed during evaluation')
            output[path] = actual
    if mode == 'capture':
        small.finish()
    return dict(mode=mode, seconds=time.perf_counter() - start,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                file_reads=reads, hashed_bytes=hashed_bytes, json_parses=parses,
                matched_pins=output,
                parsed_json_sha256=hashlib.sha256(json.dumps(parsed, sort_keys=True,
                    separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
                scope='CAPTURED_SAMPLE_ONLY_NOT_LIVE_FILESYSTEM_QUALIFICATION')


def selection(plan_path, seal):
    captured = epoch.VerificationEpoch({str(plan_path): seal})
    plan = captured.json(plan_path, seal)
    captured.finish()
    require(plan['population'] == 729 and plan['targets'] == 5892 and
            plan['protected'] == 17774 and plan['audited'] == 23666,
            'Not exact reviewed729 launch')
    pins = plan['pins']
    main = Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin')
    chosen = [
        ROOT / 'verification/out/branch-combo-six-policy-population-729-agent-20261006-02/config.json',
        ROOT / 'verification/out/lzc-snapshot-eight-policy-runtime-729-agent-20261006-01/config.json',
        DEFAULT / 'config.json',
        main / 'clang-22', main / 'clang',
        DEFAULT / 'csv-fixed-eight-plan.json', DEFAULT / 'runtime-plan.json',
    ]
    selected = {str(p): pins[str(p)] for p in chosen}
    alias = str(main / 'clang')
    aliases = {alias: dict(link_target='clang-22', resolved=str(main / 'clang-22'),
                          sha256=selected[alias])}
    require(selected[alias] == selected[str(main / 'clang-22')], 'Conflicting alias pair')
    return dict(pins=selected, aliases=aliases, passes=2,
                json_paths=[str(DEFAULT / 'csv-fixed-eight-plan.json'), str(DEFAULT / 'runtime-plan.json')],
                source_plan=str(plan_path), source_plan_sha256=seal,
                population=729, full_launch_pin_count=len(pins), selected_pin_count=len(selected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', choices=('repeated', 'capture'))
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--spec-sha')
    args = parser.parse_args()
    if args.worker:
        require(args.spec is not None and args.spec_sha is not None, 'Sealed worker spec required')
        captured = epoch.VerificationEpoch({str(args.spec): args.spec_sha})
        spec = captured.json(args.spec, args.spec_sha)
        captured.finish()
        print(json.dumps(evaluate(spec, args.worker), sort_keys=True))
        return
    require(args.output is not None, 'Fresh output required')
    out = args.output.absolute()
    require(out.parent == ROOT / 'verification/out' and not out.exists() and
            out.resolve() == out, 'Fresh canonical direct output required')
    spec = selection(DEFAULT / 'population-launch-plan.json', PLAN_SHA)
    out.mkdir()
    spec_path = out / 'sample-spec.json'
    spec_bytes = (json.dumps(spec, sort_keys=True, indent=2) + '\n').encode()
    spec_path.write_bytes(spec_bytes)
    spec_sha = hashlib.sha256(spec_bytes).hexdigest()
    results = {}
    for mode in ('repeated', 'capture'):
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', mode,
                   '--spec', str(spec_path), '--spec-sha', spec_sha]
        run = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        result = json.loads(run.stdout)
        results[mode] = result
        (out / (mode + '.json')).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    old, new = results['repeated'], results['capture']
    require(old['matched_pins'] == new['matched_pins'] == spec['pins'] and
            old['parsed_json_sha256'] == new['parsed_json_sha256'], 'Consumer outcomes differ')
    files = [Path(__file__).resolve(), Path(epoch.__file__).resolve(),
             Path(__file__).with_name('test_benchmark_verification_epoch.py'),
             spec_path, out / 'repeated.json', out / 'capture.json']
    report = dict(status='READONLY_PIN_SAMPLE_BENCHMARK_EQUIVALENT_NOT_QUALIFICATION',
        population=729, full_pin_validation=False, EDA_started=False,
        independent_postrun_epoch_required=True, immutable_live_filesystem_proved=False,
        sample=spec, results=results,
        file_read_reduction=old['file_reads'] - new['file_reads'],
        hashed_byte_reduction=old['hashed_bytes'] - new['hashed_bytes'],
        limitations=['Baseline ran first; warm cache/order confounds elapsed-time comparison.',
                    'Only two small JSONs parsed; 114MB config structural validation not benchmarked.',
                    'Hashes attest captured bytes only, not later file contents or native semantics.',
                    'No current/frozen consumer wiring, no aggregate admission or report approval.'],
        pins={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    data = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    (out / 'benchmark-report.json').write_bytes(data)
    print(json.dumps(dict(output=str(out), seal=hashlib.sha256(data).hexdigest(),
                         status=report['status'], repeated_seconds=old['seconds'],
                         capture_seconds=new['seconds'], repeated_peak_rss_kib=old['peak_rss_kib'],
                         capture_peak_rss_kib=new['peak_rss_kib'],
                         hashed_byte_reduction=report['hashed_byte_reduction'])))


if __name__ == '__main__':
    main()
