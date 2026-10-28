#!/usr/bin/env python3
"""Prepare a reviewed combined delta and backups, never install implicitly."""
import argparse
import difflib
import json
from pathlib import Path

from stage import ROOT, LIVE, PUBLIC, files, atomic_json, hashes
from guard import accepted_inputs, merge


def candidate_files():
    result = files()
    path = Path('repack.cpp')
    old = 'if constexpr (is_qbs_block_type<BLOC_TYPE>::value && INTER_SIZE == 1) {'
    new = ('if constexpr (INTER_SIZE == 1 &&\n'
           '                              (PARAM_TYPE == GGML_TYPE_Q8_K || PARAM_TYPE == GGML_TYPE_Q8_0)) {')
    if result[path].count(old) != 2:
        raise ValueError('Expected only the two accepted gather guards')
    result[path] = result[path].replace(old, new)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out') or out.exists():
        raise ValueError('Fresh independent backup required')
    pins = accepted_inputs()
    reports = {
        'm4-packed-qkv-vcs-20261027-01': 'PASS',
        'm4-packed-integration-audit-20261027-01': 'PASS',
        'm4-stride-rvv-repair-20261027-04': 'PASS',
    }
    for name, state in reports.items():
        report = ROOT / 'verification/out' / name / 'result.json'
        if json.loads(report.read_text())['state'] != state:
            raise ValueError('Missing gate: ' + name)
        merge(pins, hashes([report]))
    merge(pins, hashes([Path(__file__)]))
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Accepted input drift; do not refresh expected hashes')
    generated = candidate_files()
    out.mkdir(parents=True)
    patch = []
    targets = []
    for relative, text in generated.items():
        source = LIVE / relative
        destination = out / 'candidate' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
        before = source.read_text() if source.exists() else ''
        if source.exists():
            backup = out / 'before/runtime' / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(source.read_bytes())
        prefix = 'ggml/src/ggml-cpu/' + str(relative)
        patch.extend(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                     fromfile='a/' + prefix if source.exists() else '/dev/null', tofile='b/' + prefix))
        targets.append(dict(runtime=str(source), candidate=str(destination), existed=source.exists()))
        if relative.parent == Path('arch/riscv') and (PUBLIC / relative.name).exists():
            backup = out / 'before/canonical' / relative.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes((PUBLIC / relative.name).read_bytes())
    (out / 'integration.patch').write_text(''.join(patch))
    merge(pins, hashes(p for p in out.rglob('*') if p.is_file()))
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Inputs changed while preparing candidate')
    atomic_json(out / 'manifest.json', pins)
    atomic_json(out / 'result.json', dict(state='PREPARED_NOT_INSTALLED', targets=targets,
        rtl_changed=False, runtime_changed=False, scope='Combined reviewed delta and backups only',
        remaining='Independent complete-call audit, installation, normal library build and execution gates'))


if __name__ == '__main__':
    main()
