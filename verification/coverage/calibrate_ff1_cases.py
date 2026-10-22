"""Measure standalone case-to-coverage mapping; never admit its VDBs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from inventory_operand_debug import ROOT
from inspect_branch_gaps import instance_bits


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    if out.parent != ROOT / 'verification/out' or not out.is_dir() or (out / 'mapping.json').exists():
        raise ValueError('Independent prepared compile directory required')
    source = ROOT / 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_ff1.v'
    build = ROOT / 'verification/out/repaired-aligned-build-20260930-01'
    if sha(source) != json.loads((build / 'build-source-pins.json').read_bytes())[str(source)]:
        raise ValueError('Source differs from frozen processor')
    bitmap_path = ROOT / 'verification/out/gap94-offline-admitted-701-20261006-01/combined-bits.json'
    bitmap = json.loads(bitmap_path.read_bytes())
    references = [r for s, r in bitmap['metrics']['branch'].items()
                  if '.i_ara.' in s and s.endswith(('x_frac0_expnt', 'x_frac1_expnt'))]
    if len(references) != 32 or len({(r['checksum'], r['width']) for r in references}) != 1:
        raise ValueError('Ambiguous processor FF1 definition')
    reference = references[0]
    files = [source, build / 'build-source-pins.json', bitmap_path, Path(__file__).resolve(),
             ROOT / 'verification/coverage/ff1_case_calibration_tb.sv', out / 'simv', out / 'compile.log']
    pins = {str(p): sha(p) for p in files}
    observations = []
    for selected in [-1, *range(52), -2]:
        name = 'zero' if selected == -1 else 'default_x' if selected == -2 else 'bit_%02d' % selected
        directory = out / name
        directory.mkdir()
        command = [str(out / 'simv'), '+CASE=%d' % selected, '-cm', 'branch',
                   '-cm_dir', str(directory / 'code.vdb'), '-cm_name', name]
        with (directory / 'console.log').open('x') as stream:
            subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=30, check=True)
        log = (directory / 'console.log').read_text()
        if log.count('FF1_CALIBRATION_PASS case=%d' % selected) != 1:
            raise ValueError('Missing exact selfcheck')
        data = list((directory / 'code.vdb/snps/coverage/db/testdata').glob('*/branch.verilog.data.xml'))
        if len(data) != 1:
            raise ValueError('Ambiguous coverage data')
        checksum, bits = instance_bits(data[0], 'ff1_case_calibration_tb.dut')
        if checksum != reference['checksum'] or len(bits) != reference['width'] or set(bits) - {'0', '1'}:
            raise ValueError('Unit/processor checksum or shape differs')
        observations.append(dict(case=selected, name=name, bits=bits,
            checksum=checksum, command=command, data=str(data[0]), data_sha256=sha(data[0])))
    baseline = observations[0]['bits']
    if baseline.count('1') != 1:
        raise ValueError('Initial zero case has ambiguous coverage')
    positions = {baseline.index('1')}
    for row in observations[1:]:
        if any(a == '1' and b != '1' for a, b in zip(baseline, row['bits'])):
            raise ValueError('Baseline coverage disappeared')
        new = [i for i, (a, b) in enumerate(zip(baseline, row['bits'])) if a == '0' and b == '1']
        if len(new) != 1 or new[0] in positions:
            raise ValueError('Nonunique case mapping')
        row['raw_index'] = new[0]
        positions.add(new[0])
    observations[0]['raw_index'] = baseline.index('1')
    if positions != set(range(54)) or any(sha(Path(p)) != h for p, h in pins.items()):
        raise ValueError('Incomplete mapping or input drift')
    result = dict(status='STANDALONE_FF1_CASE_MAPPING_NOT_NATIVE_EXCLUSION',
        cases=54, processor_coverage_added=False, native_exclusion_qualified=False,
        checksum=reference['checksum'], pins=pins, observations=observations)
    with (out / 'mapping.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'cases', 'checksum')}))


if __name__ == '__main__':
    main()
