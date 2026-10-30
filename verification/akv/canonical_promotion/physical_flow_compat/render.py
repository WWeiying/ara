#!/usr/bin/env python3
"""Prepare four prospective source changes; no EDA, library access or application."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
GLOBAL = 'backend/syn/ara_soc/v1-dc/global_scripts/dc.tcl'
STANDALONE = 'verification/akv/synthesis/akv_engine_dc.tcl'
PREFLIGHT = 'hardware/scripts/akv/check-synthesis-preflight.py'
COLLECTOR = 'hardware/scripts/akv/collect-synthesis-results.py'
TARGETS = (GLOBAL, STANDALONE, PREFLIGHT, COLLECTOR)


def text(path):
    # dc.tcl has mixed line endings: never normalize unrelated bytes.
    return path.read_bytes().decode('utf-8')


class Changes:
    def __init__(self, original):
        self.original = self.value = original
        self.edits = []

    def replace(self, before, after):
        if self.value.count(before) != 1:
            raise ValueError('Changed/ambiguous source anchor: ' + before[:120])
        self.value = self.value.replace(before, after, 1)
        self.edits.append((before, after))

    def block(self, first, following, replacement):
        if self.value.count(first) != 1 or self.value.count(following) != 1:
            raise ValueError('Changed block boundary')
        start, end = self.value.index(first), self.value.index(following)
        if end <= start:
            raise ValueError('Reversed source block')
        self.replace(self.value[start:end], replacement)

    def finish(self):
        restored = self.value
        for before, after in reversed(self.edits):
            if restored.count(after) != 1:
                raise ValueError('Ambiguous inverse')
            restored = restored.replace(after, before, 1)
        if restored != self.original:
            raise ValueError('Out-of-scope source change')
        return self.value


def metric_block(integrated):
    prefix = 'akv_' if integrated else ''
    engine = '*/i_akv_engine' if integrated else 'i_akv_engine'
    empty = ''
    if integrated:
        # Global DC also serves configurations without AKV. Not an accepted AKV report.
        empty = ('  {0 0 0 0 0 0 0} {\n    set akv_organization not_instantiated\n'
                 '    set akv_v1_macro_count 0\n    set akv_v2_macro_count 0\n'
                 '    set akv_capacity_bits 0\n  }')
    return text(HERE / 'metrics.tcl.in').replace('__P__', prefix).replace(
        '__ENGINE__', engine).replace('__EMPTY__', empty) + '\n'


def render_tcl(source, integrated):
    c = Changes(source)
    if integrated:
        c.block('set akv_v1_macro_ref ', '# A design object has no area attribute', metric_block(True))
        stream, prefix = 'physical_summary', 'akv_'
    else:
        library = ('set q_sram_library "/home/wangwy/ara/backend/library/mem/'
                   'ts1n28hpcpuhdsvtb64x256m1swbso_170a/DB/'
                   'ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.db"\n')
        anchor = 'set context_sram_library '
        c.replace(anchor, library + anchor)
        c.replace('$context_sram_library $kv_sram_library $synthetic_library] {',
                  '$context_sram_library $kv_sram_library $q_sram_library $synthetic_library] {')
        c.replace('"* $std_library $context_sram_library $kv_sram_library $synthetic_library"',
                  '"* $std_library $context_sram_library $kv_sram_library $q_sram_library $synthetic_library"')
        c.block('set v1_macro_ref ', 'set macro_area 0.0', metric_block(False))
        stream, prefix = 'report_file', ''
    anchor = f'puts ${stream} "akv_sram_macro_count=${prefix}macro_count"\n'
    c.replace(anchor, f'puts ${stream} "akv_sram_organization=${prefix}organization"\n' + anchor +
              f'puts ${stream} "akv_q_sram_macro_count=${prefix}q_macro_count"\n')
    c.replace(f'puts ${stream} "physical_sram_capacity_bits=[expr {{(${prefix}v1_macro_count * 96 + ${prefix}v2_macro_count * 128) * 256}}]"',
              f'puts ${stream} "physical_sram_capacity_bits=${prefix}capacity_bits"')
    return c.finish()


def render_collector(source):
    c = Changes(source)
    c.replace('# Keep historical reports readable without accepting mixed macro organizations.\n'
              'AKV_SRAM_ORGANIZATIONS = {(20, 4, 16): 327680, (10, 2, 8): 311296}\n',
              text(HERE / 'organization.py.inc'))
    c.replace('def library_inputs(source_inputs: tuple[Path, ...]) -> list[Path]:',
              'def library_inputs(source_inputs: tuple[Path, ...], organization: str | None = None) -> list[Path]:')
    c.replace('    return sorted(libraries, key=lambda path: str(path.resolve()))\n',
              '    if organization == "unified_q64x256_kv128x256" and not all(\n'
              '        any(shape in name for name in names) for shape in ("64x256", "128x256")\n'
              '    ):\n        raise CollectionError("unified AKV requires independent Q64 and KV128 DBs")\n'
              '    return sorted(libraries, key=lambda path: str(path.resolve()))\n')
    c.block('    organization = (macro_count, v1_count, v2_count)\n', '    report_total, report_macro =',
            '    organization, q_count = validate_sram_organization(values, "physical_sram_capacity_bits")\n\n')
    c.replace('        "akv_sram_macro_count": macro_count,\n',
              '        "akv_sram_organization": organization,\n'
              '        "akv_q_sram_macro_count": q_count,\n        "akv_sram_macro_count": macro_count,\n')
    c.replace('    libraries = library_inputs(spec.source_inputs)\n',
              '    values = read_key_values(spec.summary_rpt)\n'
              '    organization, _ = validate_sram_organization(values, "physical_sram_capacity_bits")\n'
              '    libraries = library_inputs(spec.source_inputs, organization)\n')
    c.replace('    values = read_key_values(spec.summary_rpt)\n    metrics = validate_metrics',
              '    metrics = validate_metrics')
    c.replace('    observed_libraries = library_inputs(source_inputs)\n',
              '    metrics = summary.get("metrics", {})\n'
              '    organization, _ = validate_sram_organization(metrics, "akv_sram_capacity_bits")\n'
              '    observed_libraries = library_inputs(source_inputs, organization)\n')
    c.block('    metrics = summary.get("metrics", {})\n    organization = (metrics.get(',
            '        raise CollectionError("synthesis summary metrics violate',
            '    if (\n        float(metrics.get("design_total_area_um2", 0)) <= 0\n'
            '        or float(metrics.get("design_logic_area_um2", 0)) <= 0\n    ):\n')
    return c.finish()


def render_preflight(source):
    c = Changes(source)
    c.replace('class PreflightError(ValueError):', text(HERE / 'preflight.py.inc') + '\n\nclass PreflightError(ValueError):')
    c.replace('    qbs_sram_db: Path = DEFAULT_QBS_SRAM_DB\n',
              '    qbs_sram_db: Path = DEFAULT_QBS_SRAM_DB\n'
              '    akv_q_sram_db: Path = DEFAULT_AKV_Q_SRAM_DB\n'
              '    akv_storage_organization: str = SPLIT_AKV_ORGANIZATION\n')
    c.replace('    defines, sources = _filelist_entries(filelist_text)\n',
              '    defines, sources = _filelist_entries(filelist_text)\n'
              '    unified_storage = check_storage_selection(options, sources)\n')
    c.replace('        _require_sources(sources, (AKV_SRAM_BLACKBOX,))\n',
              '        _require_sources(sources, (AKV_Q_SRAM_BLACKBOX if unified_storage else AKV_SRAM_BLACKBOX,))\n')
    c.replace('        if not options.sram_db.is_file():\n'
              '            raise PreflightError(f"missing AKV SRAM DB: {options.sram_db}")\n'
              '        if str(options.sram_db) not in setup_text:\n'
              '            raise PreflightError("DC setup does not include the AKV 96x256 SRAM DB")\n',
              '        akv_db = options.akv_q_sram_db if unified_storage else options.sram_db\n'
              '        akv_shape = "64x256 Q" if unified_storage else "96x256"\n'
              '        if not akv_db.is_file():\n'
              '            raise PreflightError(f"missing AKV {akv_shape} SRAM DB: {akv_db}")\n'
              '        if str(akv_db) not in setup_text:\n'
              '            raise PreflightError(f"DC setup does not include the AKV {akv_shape} SRAM DB")\n')
    c.replace('        "filelist": str(options.filelist),\n',
              '        "filelist": str(options.filelist),\n'
              '        "akv_storage_organization": options.akv_storage_organization,\n')
    c.replace('    parser.add_argument("--sram-db", type=Path, default=DEFAULT_AKV_SRAM_DB)\n',
              '    parser.add_argument("--sram-db", type=Path, default=DEFAULT_AKV_SRAM_DB)\n'
              '    parser.add_argument("--akv-q-sram-db", type=Path, default=DEFAULT_AKV_Q_SRAM_DB)\n'
              '    parser.add_argument("--akv-storage-organization",\n'
              '                        choices=(SPLIT_AKV_ORGANIZATION, UNIFIED_AKV_ORGANIZATION),\n'
              '                        default=SPLIT_AKV_ORGANIZATION)\n')
    return c.finish()


def render(name, source):
    if name in (GLOBAL, STANDALONE):
        return render_tcl(source, name == GLOBAL)
    if name == COLLECTOR:
        return render_collector(source)
    if name == PREFLIGHT:
        return render_preflight(source)
    raise ValueError('Out-of-scope target')


def prepare(root, output):
    originals = {name: text(root / name) for name in TARGETS}
    changed = {name: render(name, value) for name, value in originals.items()}
    output.mkdir(parents=True, exist_ok=False)
    patch = ''
    sha = lambda data: hashlib.sha256(data).hexdigest()
    for name in TARGETS:
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(changed[name].encode())
        patch += ''.join(difflib.unified_diff(originals[name].splitlines(keepends=True),
                    changed[name].splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name))
    (output / 'physical_flow.patch').write_bytes(patch.encode())
    for name in TARGETS:
        if text(root / name) != originals[name]:
            raise ValueError('Input changed during proposal generation')
    own = [p for p in HERE.iterdir() if p.is_file()]
    receipt = dict(state='STATIC_PHYSICAL_FLOW_COMPATIBILITY_NOT_APPLIED',
                   compiler_invoked=False, libraries_measured=False, ppa_closed=False,
                   inputs={str(root / name): sha(value.encode()) for name, value in originals.items()},
                   after={name: sha(value.encode()) for name, value in changed.items()},
                   helper_pins={str(p): sha(p.read_bytes()) for p in own}, patch_sha256=sha(patch.encode()))
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source_root.resolve(strict=True), args.output.resolve())
