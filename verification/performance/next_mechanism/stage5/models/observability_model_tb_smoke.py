"""Normal model-TB same-image/same-ELF range-versus-entry trace control."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def main():
    out = OUT/'stage5_models_observability_normal_tb_smoke_20261110_01'
    out.mkdir()
    original = json.loads((OUT/'stage5_qemu_execution_20261110_03/selection.json').read_text())['commands'][0]['guest']
    assert original[original.index('-accel') + 1] == 'tcg,one-insn-per-tb=on'
    original[original.index('-accel') + 1] = 'tcg'
    base_filter = original[original.index('-dfilter') + 1]
    points = {int(v.split('+')[0], 16) for v in base_filter.split(',')}
    entry, size = 0x8000050a, 0x1dc  # Frozen ELF run_matrix_case symbol.
    results = []
    for name, extent in (('range', size), ('entry', 1)):
        argv = list(original)
        argv[argv.index('-dfilter') + 1] = base_filter + ',' + hex(entry) + '+' + str(extent)
        trace = out/(name + '.trace.log')
        argv[argv.index('-D') + 1] = str(trace)
        start = time.monotonic()
        with (out/(name + '.guest.log')).open('xb') as log:
            done = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=5)
        elapsed = time.monotonic() - start
        assert done.returncode == 0
        counts = {}; last = None
        for line in trace.read_text().splitlines():
            if line.startswith('Trace '):
                match = re.match(r'Trace 0: (0x[0-9a-f]+) \[[0-9a-f]+/([0-9a-f]+)/', line)
                assert match
                last = match[1], int(match[2], 16)
                counts[last[1]] = counts.get(last[1], 0) + 1
            elif line.startswith('Stopped execution of TB chain before '):
                match = re.match(r'Stopped execution of TB chain before (0x[0-9a-f]+) \[([0-9a-f]+)\]', line)
                assert match and last == (match[1], int(match[2], 16))
                counts[last[1]] -= 1
                last = None
            else:
                last = None
        results.append(dict(policy=name, argv=argv, returncode=done.returncode,
                            elapsed_seconds=elapsed, trace_bytes=trace.stat().st_size,
                            required_pc_counts={str(pc): counts.get(pc, 0) for pc in points},
                            entry_hits=counts.get(entry, 0)))
    assert results[0]['required_pc_counts'] == results[1]['required_pc_counts']
    assert results[0]['entry_hits'] == results[1]['entry_hits'] > 0
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report = dict(state='NORMAL_TB_SAME_ELF_QBS_TRACE_SCOPE_CONTROL_PASS', results=results,
                  one_insn_per_tb=False, per_guest_timeout_seconds=5,
                  qemu_sha256=sha(original[0]), elf_sha256=sha(original[original.index('-kernel') + 1]),
                  source_sha256=sha(__file__), guest_workload_changed=False,
                  verbose_environment_not_exercised_by_baremetal_smoke=True,
                  qemu_time_not_a_performance_claim=True)
    with (out/'result.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
