"""Supplement sealed01 native evidence; no EDA, no changes to report outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import report_global777_compact as s

HERE = Path(__file__).resolve().parent
OUT = s.OUT / 'trusted-ip797-global-parent-20261008-01'
CONFIG_SHA = '4ca6047e0c9e96218f8c4c07aed35a4a29d38cd18042d015fa3f5ae1b5f4e358'
REVIEW = s.OUT / 'trusted-execution797-isystem-review-agent-20261008-02.json'
REVIEW_SHA = '7089a39a78818e9abf5e420aef5b5b4e61a196e8743983654ed19be6cf104769'
ANNOTATION = 'Trusted execution IP integration scope; not unreachability or exhaustive verification'
MARKERS = ('TRUSTED797_FIVE_PHASE_DONE', 'COMPACT777_FIVE_PHASE_DONE', 'DVE_COVERAGE_EXPORT_DONE')
need = s.need


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path, sha):
    data = Path(path).read_bytes()
    need(hashlib.sha256(data).hexdigest() == sha, 'Seal mismatch: ' + str(path))
    return json.loads(data)


def owned(scope, roots):
    return any(scope == r or scope.startswith(r + '.') for r in roots)


def whole_blocks(text, roots):
    # Inspect native blocks BEFORE semantic set normalization removes duplicates/annotations.
    blocks, current = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('CHECKSUM:'):
            if current:
                blocks.append(current)
            current = [line]
        else:
            need(current, 'Native content before checksum')
            current.append(line)
    if current:
        blocks.append(current)
    actual = {}
    for block in blocks:
        scopes = [line.split(':', 1)[1].strip() for line in block if line.startswith('INSTANCE:')]
        points = [line for line in block[1:] if not line.startswith(('INSTANCE:', 'ANNOTATION:'))]
        # Historical point blocks, including redundant points inside a selected IP,
        # keep their original annotation rules. Only whole-root blocks use this policy.
        if points or not any(owned(scope, roots) for scope in scopes):
            continue
        need(len(scopes) == 1 and scopes[0] in roots, 'Extra/multiple trusted whole scope')
        scope = scopes[0]
        need(scope not in actual, 'Duplicate trusted whole root: ' + scope)
        match = re.fullmatch(r'CHECKSUM:\s*"([0-9]+)"', block[0])
        need(match is not None and match[1] == roots[scope], 'Exact native whole module checksum')
        annotations = [line for line in block if line.startswith('ANNOTATION:')]
        need(annotations and all(re.fullmatch(r'ANNOTATION:\s*"' + re.escape(ANNOTATION) + r'"', line)
                                 for line in annotations), 'Missing/wrong trusted whole annotation')
        actual[scope] = match[1]
    need(actual == roots, 'Missing trusted whole roots')
    return actual


def whole_gate(text, config):
    roots = config['trusted_roots']
    whole_blocks(text, roots)
    other, masks = s.semantic(text)
    actual = {scope: checks for scope, checks, _, directive in other
              if directive == 'WHOLE_SCOPE' and owned(scope, roots)}
    need(actual == roots, 'Extra trusted whole descendants/checksums')
    retained = ({row for row in other if not owned(row[0], roots)},
                {key: value for key, value in masks.items() if not owned(key[0], roots)})
    need(s.semantic_seal(retained) == config['retained_EL_seal'], 'Inherited outside-subtree EL changed')


def terminal_markers(terminal, config, seal, gui, launcher):
    s.terminal_gate(terminal, config)
    need(terminal['config_seal'] == seal, 'Exact executed configuration')
    s.diagnostics(gui)
    s.diagnostics(launcher)
    lines = gui.splitlines()
    need(all(lines.count(marker) == 1 for marker in MARKERS), 'Each native/export marker exactly once')
    return {marker: lines.count(marker) for marker in MARKERS}


def gui_pins(output):
    directory = output / 'DVEfiles'
    main = directory / 'dve_gui.log'
    need(main.is_file(), 'Missing actual GUI log')
    paths = sorted(p for p in directory.rglob('*') if p.is_file() and p.suffix == '.log')
    need(main in paths, 'Recursive GUI log inventory incomplete')
    for path in paths:
        need(path.resolve().is_relative_to(output.resolve()), 'GUI log symlink escapes output')
    return {str(path): digest(path) for path in paths}


def prepare(directory):
    need(directory.parent == s.OUT and not directory.exists(), 'Fresh independent helper package')
    config = bound(OUT / 'config.json', CONFIG_SHA)
    review = bound(REVIEW, REVIEW_SHA)
    roots = {row['scope']: row['design_checksum'] for row in review['candidates']
             if row['scope'] in review['minimal_recommended_roots']}
    need(config['trusted_roots'] == roots and len(roots) == 577 and config['population'] == 797,
         'Exact system02 and sealed01')
    paths = [Path(__file__).resolve(), HERE / 'test_verify_trusted_ip797_readonly.py',
             Path(s.__file__).resolve(), Path(s.inventory.__file__).resolve(),
             Path(s.tools.__file__).resolve(), Path(s.life.__file__).resolve(),
             s.TCL, s.EXPORT, OUT / 'config.json', REVIEW]
    manifest = dict(schema='TRUSTED797_SEALED01_READONLY_SUPPLEMENT_V1', output=str(OUT),
                    config_sha256=CONFIG_SHA, review_sha256=REVIEW_SHA,
                    pins={str(path): digest(path) for path in paths}, annotation=ANNOTATION,
                    markers=list(MARKERS), whole_roots=577, EDA_started=False,
                    report_modified=False, native_qualification_claimed=False)
    directory.mkdir()
    target = directory / 'manifest.json'
    with target.open('x') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(manifest=str(target), seal=digest(target), status='PREPARED_READONLY_NOT_NATIVE_VERIFIED')))


def verify(manifest_path, manifest_seal):
    manifest = bound(manifest_path, manifest_seal)
    need(manifest['schema'] == 'TRUSTED797_SEALED01_READONLY_SUPPLEMENT_V1' and
         manifest['output'] == str(OUT) and manifest['config_sha256'] == CONFIG_SHA and
         manifest['annotation'] == ANNOTATION and manifest['markers'] == list(MARKERS), 'Exact helper manifest')
    for path, sha in manifest['pins'].items():
        need(digest(path) == sha, 'Frozen helper dependency: ' + path)
    config = bound(OUT / 'config.json', CONFIG_SHA)
    qp = OUT / 'qualification.json'
    qualification_sha = digest(qp)
    q = bound(qp, qualification_sha)
    need(q['status'] == 'TRUSTED_IP_INTEGRATION797_NATIVE_VERIFIED' and q['config_seal'] == CONFIG_SHA and
         q['population'] == 797 and q['trusted_roots'] == config['trusted_roots'], 'Completed sealed01 qualification')
    for path, sha in q['output_pins'].items():
        need(Path(path).resolve().is_relative_to(OUT.resolve()) and digest(path) == sha, 'Native output pin: ' + path)
    paths = [OUT / 'config.json', qp, OUT / 'terminal.json', OUT / 'execution.json', OUT / 'launcher.log']
    for stage in s.STAGES:
        path = OUT / s.EL_FILES[stage]
        if stage in ('raw', 'reset', 'final'):
            need(path.read_bytes() == b'', 'Global empty/reset EL')
        else:
            whole_gate(path.read_text(), config)
        paths.append(path)
    need((OUT / 'cleanup-empty.el').read_bytes() == b'', 'Cleanup empty')
    paths.append(OUT / 'cleanup-empty.el')
    selected = (OUT / 'selected_tests.txt').read_text().splitlines()
    s.membership(config['input_ledger'], selected, 797)
    need(selected == config['expected_selected'], 'Exact selected797 order')
    execution = json.loads((OUT / 'execution.json').read_bytes())
    need(execution['config_seal'] == CONFIG_SHA and execution['cwd'] == str(OUT), 'Exporter executed this output/seal')
    terminal = json.loads((OUT / 'terminal.json').read_bytes())
    logs = gui_pins(OUT)
    gui = (OUT / 'DVEfiles/dve_gui.log').read_text()
    markers = terminal_markers(terminal, config, CONFIG_SHA, gui, (OUT / 'launcher.log').read_text())
    pins = dict(q['output_pins'], **logs)
    pins.update({str(path): digest(path) for path in paths})
    for path, sha in pins.items():
        need(digest(path) == sha, 'Read-end evidence drift: ' + path)
    need(digest(qp) == qualification_sha, 'Qualification changed during read')
    return dict(status='TRUSTED797_SEALED01_READONLY_SUPPLEMENT_PASS', config_sha256=CONFIG_SHA,
                qualification_sha256=qualification_sha, helper_manifest_sha256=manifest_seal,
                roots=577, stages=list(s.STAGES), annotation_exact=True, duplicate_whole_roots=False,
                inherited_annotations_not_reclassified=True, markers=markers,
                launcher_export_process_returncode=terminal['returncode'], timeout=terminal['timeout'],
                dedicated_exporter_returncode_available=False,
                exporter_success_basis='Strict owning process terminal0 plus exact export DONE and no exporter FAILED',
                recursive_GUI_log_pins=logs, output_pins=pins, EDA_started=False, report_modified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify'))
    parser.add_argument('--package', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        need(args.package is not None and args.receipt is None, 'Explicit independent package')
        prepare(args.package.resolve())
    else:
        need(args.manifest is not None and args.seal is not None, 'Frozen helper manifest/seal')
        result = verify(args.manifest.resolve(), args.seal)
        text = json.dumps(result, indent=2) + '\n'
        if args.receipt:
            target = args.receipt.resolve()
            need(not target.is_relative_to(OUT.resolve()), 'Receipt must not modify sealed report directory')
            with target.open('x') as stream:
                stream.write(text)
        print(text, end='')
