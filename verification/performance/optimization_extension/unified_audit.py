#!/usr/bin/env python3
"""Read-only audit successor with distinct report names; never rebuild targets."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    spec = importlib.util.spec_from_file_location('sealed_unified_driver', out / 'unified_driver.py')
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    b.require(b.output(out) == out, 'Wrong completed build')
    build = b.read(out / 'result.json')
    b.require(build['state'] == 'FRESH_UNIFIED_LLAMA_BUILD_CHECKED_NOT_MODEL_EXECUTED' and
              b.read(out / 'build-audit.json')['error'] == "FileExistsError(17, 'File exists')",
              'Not the known post-build audit report collision')
    b.require(b.sha(out / 'source-pins.json') == build['source_pins_sha256'] and
              b.sha(out / 'compile-source-pins.json') == build['compile_source_pins_sha256'], 'Original build receipt identity')
    b.verify(b.read(out / 'source-pins.json'))
    b.verify(b.read(out / 'compile-source-pins.json'))
    b.verify({r['path']: r['sha256'] for r in build['programs'].values()})
    b.require((out / 'compiled-capability-and-helpers.json').is_file(), 'Original audit did not reach the report collision')
    helper = (out / 'unified_driver.py').read_text()
    for before, after in (('cap5-macros', 'audit2-cap5-macros'), ('cap5-preprocessed', 'audit2-cap5-preprocessed'),
                          ('compiled-capability-and-helpers', 'audit2-compiled-capability-and-helpers'),
                          ("('audit-' + name + '-readelf.log')", "('audit2-' + name + '-readelf.log')")):
        b.require(before in helper, 'Missing exact helper report derivation')
        helper = helper.replace(before, after)
    audit = (out / 'unified_build_audit.py').read_text()
    audit = b.replace(audit, 'from unified_driver import audit_extensions', 'from unified_driver_audit2 import audit_extensions')
    for name in ('compile-source-pins.json', 'compiler-dependencies.json', 'math-modes.json',
                 'compiled-enablement.json', 'build-audit.json'):
        b.require(name in audit, 'Missing exact independent audit report name')
        audit = audit.replace(name, 'audit2-' + name)
    audit = b.replace(audit, "('audit-' + name + '-readelf.log')", "('audit2-' + name + '-readelf.log')")
    compile(helper, 'unified_driver_audit2.py', 'exec')
    compile(audit, 'unified_build_audit2.py', 'exec')
    for name, text in (('unified_driver_audit2.py', helper), ('unified_build_audit2.py', audit)):
        with (out / name).open('x') as stream:
            stream.write(text)
    b.save(out / 'audit2-derivation.json', dict(change='Only output report/log names changed; all checks retained',
        original_driver_sha256=b.sha(out / 'unified_driver.py'), original_audit_sha256=b.sha(out / 'unified_build_audit.py'),
        successor_driver_sha256=b.sha(out / 'unified_driver_audit2.py'), successor_audit_sha256=b.sha(out / 'unified_build_audit2.py'),
        controller=str(Path(__file__).resolve()), controller_sha256=b.sha(__file__), targets_recompiled=False,
        original_audit_failure_preserved=True))
    command = ['/usr/bin/python3.11', '-B', str(out / 'unified_build_audit2.py')]
    with (out / 'audit2.stdout.log').open('x') as stdout, (out / 'audit2.stderr.log').open('x') as stderr:
        code = subprocess.run(command, cwd=out, stdout=stdout, stderr=stderr).returncode
    b.save(out / 'audit2-command.json', dict(argv=command, returncode=code))
    b.require(code == 0, 'Successor independent audit failed; preserve evidence')
    checked = b.read(out / 'audit2-build-audit.json')
    b.require(checked['state'] == 'FRESH_UNIFIED_LLAMA_BUILD_INDEPENDENTLY_CHECKED_NOT_MODEL_EXECUTED', 'Audit not checked')
    live_dependencies = []
    for row in b.read(out / 'audit2-compiler-dependencies.json'):
        text = Path(row['path']).read_text().replace('\\\n', '')
        for name in shlex.split(text.split(':', 1)[1]):
            path = Path(name).resolve()
            if path.is_relative_to(b.LIVE) or path.is_relative_to(b.ROOT / 'software'):
                live_dependencies.append(str(path))
    b.require(not live_dependencies, 'Actual compiler dependency escaped the frozen inputs')
    image = {r['path']: r['sha256'] for r in checked['programs'].values()}
    for path in (out / 'build').rglob('*.a'):
        image[str(path)] = b.sha(path)
    b.verify(image)
    b.verify(b.read(out / 'source-pins.json'))
    b.verify(b.read(out / 'audit2-compile-source-pins.json'))
    b.save(out / 'image-pins-successor.json', image)
    artifacts = {str(p): b.sha(p) for p in out.iterdir() if p.is_file()}
    b.save(out / 'artifact-pins-successor.json', artifacts)
    delivery = dict(state='BUILT_NOT_MODEL_OR_RTL_PERFORMANCE_ACCEPTANCE', programs=checked['programs'],
        source_pins_sha256=b.sha(out / 'source-pins.json'), compile_source_pins_sha256=b.sha(out / 'audit2-compile-source-pins.json'),
        image_pins_sha256=b.sha(out / 'image-pins-successor.json'), artifact_pins_sha256=b.sha(out / 'artifact-pins-successor.json'),
        audit=str(out / 'audit2-build-audit.json'), audit_sha256=b.sha(out / 'audit2-build-audit.json'),
        sdk_revision=b.REV, overlay_manifest_sha256=b.sha(out / 'overlay-manifest.json'),
        source_and_image_pins_match=True, live_compiler_dependencies=[], resident=False, provider_supplied=False,
        model_executed=False, native_vcs_pass_claimed=False, rtl_performance_accepted=False, functional_acceptance=False,
        targets_recompiled=False, original_failures_preserved=True)
    b.save(out / 'delivery-successor.json', delivery)
    print(json.dumps(delivery, indent=2), flush=True)


if __name__ == '__main__':
    main()
