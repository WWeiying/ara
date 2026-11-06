#!/usr/bin/env python3
"""Independently bind the SDK archive, one relink and complete model comparisons."""
import argparse
from pathlib import Path

from audit import digest, require, verify_pins
from build_trace_context_library import write
from sdk_dispatch_model import HERE, ROOT, RUNS, PRIOR, LIBRARY, MODEL, read, recipe, relink, guest_listing, accepted_inputs
from trace_context_model import check


def collect(root):
    root = root.resolve(strict=True)
    report = read(root / 'result.json')
    require(report['state'] == 'SDK_DISPATCH_MODEL_PAIR_FUNCTIONAL_PASS' and report['post_pins_match'] and
            not report['performance_measured'] and not report['model_library_promoted'] and
            not report['production_sdk_changed'] and not report['rtl_changed'] and
            report['compiled_translation_units'] == 0 and report['reused_model_driver'] and
            report['baseline_link_reproduced_exactly'], 'Unaccepted worker')
    require(digest(root / 'source-pins.json') == report['source_pins_sha256'], 'Source inventory drift')
    pins = read(root / 'source-pins.json')
    checked = verify_pins(pins)
    verify_pins(report['artifacts'])
    for path, target in read(root / 'path-identities.json').items():
        require(str(Path(path).resolve(strict=True)) == target, 'Symlink identity drift')

    def pin(path, expected=None):
        actual = digest(path)
        require(pins.get(str(Path(path).resolve())) == actual and
                (expected is None or actual == expected), 'Missing/different consumed pin: ' + str(path))

    prior, _, library, expected_work = accepted_inputs(pin)
    require(report['library_build'] == str(LIBRARY) and report['prior_model_worker'] == str(PRIOR), 'Wrong input roots')
    for path, field in ((PRIOR / 'model.o', 'common_model_object_sha256'),
                        (PRIOR / 'candidate', 'baseline_elf_sha256'),
                        (PRIOR / 'test', 'driver_elf_sha256'), (root / 'candidate', 'candidate_elf_sha256')):
        pin(path, report[field])
    require(report['baseline_library_sha256'] == library['baseline_library_sha256'] and
            report['candidate_library_sha256'] == library['candidate_library_sha256'], 'Archive report binding')
    commands = read(root / 'commands.json')
    require(not any(r['label'].startswith('compile') for r in commands), 'Unexpected new translation unit')
    expected = relink(recipe(read(PRIOR / 'commands.json'), 'link-candidate'), PRIOR / 'model.o',
                      Path(library['baseline_library']), Path(library['candidate_library']),
                      PRIOR / 'candidate', root / 'candidate')
    require(recipe(commands, 'link-candidate') == expected, 'Link changed more than SDK archive/output')
    reproduced = relink(recipe(read(PRIOR / 'commands.json'), 'link-candidate'), PRIOR / 'model.o',
                        Path(library['baseline_library']), Path(library['baseline_library']),
                        PRIOR / 'candidate', root / 'baseline-reproduced')
    require(recipe(commands, 'link-reproduce-baseline') == reproduced, 'Baseline reproduction command differs')
    pin(root / 'baseline-reproduced', report['baseline_elf_sha256'])
    init = [Path(line.split()[2]) for line in (PRIOR / 'initramfs.list').read_text().splitlines()
            if line.startswith('file /init ')]
    require(len(init) == 1 and (root / 'initramfs.list').read_text() ==
            guest_listing(init[0], PRIOR / 'candidate', root / 'candidate', PRIOR / 'test'), 'Guest ELF mapping')
    expected_qemu = recipe(read(PRIOR / 'commands.json'), 'qemu')
    expected_qemu[expected_qemu.index('-initrd') + 1] = str(root / 'initramfs.cpio')
    require(recipe(commands, 'qemu') == expected_qemu, 'Native model/CPU/boot configuration changed')
    require(all(row['returncode'] == 0 for row in commands), 'Failed worker command')
    import sys
    sys.path.insert(0, str(ROOT / 'verification/qbs'))
    from run_ggml_segmented import verify_native_build
    for path in verify_native_build(Path(expected_qemu[0])):
        pin(path)
    require(digest(root / 'qemu.log') == report['log_sha256'], 'Guest log drift')
    measured = check((root / 'qemu.log').read_text(), (MODEL / 'qemu.log').read_text(), read(PRIOR / 'projection-schema.json'))
    require(measured == report['measured'] == expected_work == prior['measured'], 'Model replay/work binding differs')
    verify_pins(pins)
    return dict(run=str(root), checked_inputs=checked, measured=measured,
                source_pins_sha256=report['source_pins_sha256'], worker_result_sha256=digest(root / 'result.json'),
                log_sha256=report['log_sha256'], common_model_object_sha256=report['common_model_object_sha256'],
                baseline_elf_sha256=report['baseline_elf_sha256'], candidate_elf_sha256=report['candidate_elf_sha256'],
                candidate_library_sha256=report['candidate_library_sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Sole verification output required')
    out.mkdir(parents=True, exist_ok=False)
    pins = {str(p): digest(p) for p in (Path(__file__).resolve(), HERE / 'sdk_dispatch_model.py',
                                       HERE / 'build_sdk_dispatch_library.py', HERE / 'build_trace_context_library.py',
                                       HERE / 'audit.py', HERE / 'trace_context_model.py')}
    result = dict(state='CHECKING', performance_measured=False, rtl_changed=False, production_sdk_changed=False)
    try:
        report = collect(args.run)
        verify_pins(pins)
        result.update(state='SDK_DISPATCH_QWEN3_MODEL_PAIR_REAUDITED', report=report, collector_pins=pins,
            limitations=['Native QEMU validates full logits and work, not RTL cycles or speed',
                         '40-token prompt and one Decode step per KV kind; not broad model/format signoff',
                         'Non-M1 performance regression remains a separate RTL acceptance gate',
                         'Isolated archive only; production runtime is unchanged'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out / 'result.json', result)


if __name__ == '__main__':
    main()
