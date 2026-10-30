#!/usr/bin/env python3
"""Static successor; imports the immutable v1 renderer, never applies a patch."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / 'physical_flow_compat'
spec = importlib.util.spec_from_file_location('physical_flow_v1', V1 / 'render.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
ROOT = old.ROOT
GLOBAL, STANDALONE, PREFLIGHT, COLLECTOR = old.TARGETS
MAKEFILE = 'hardware/Makefile'
TARGETS = (*old.TARGETS, MAKEFILE)
text = old.text
metric_block = old.metric_block
SPLIT = 'split_v1_96x256_v2_128x256'
UNIFIED = 'unified_q64x256_kv128x256'
MARKER = '# AKV_STANDALONE_STORAGE_SELECTION_V2'
CALLER_TARGET = 'verification/akv/Makefile'
PACKAGE = HERE.parent / 'standalone_package'
CALLER_INPUT = PACKAGE / CALLER_TARGET
PACKAGE_PATCH = PACKAGE / 'standalone_makefiles.patch'


def library(depth):
    stem = f'ts1n28hpcpuhdsvtb{depth}x256m1swbso_170a'
    return f'/home/wangwy/ara/backend/library/mem/{stem}/DB/{stem}_tt0p9v25c.db'


def declarations(organization):
    depth = {SPLIT: 96, UNIFIED: 64}[organization]
    name = 'context_sram_library' if organization == SPLIT else 'q_sram_library'
    return f'set {name} "{library(depth)}"\nset kv_sram_library "{library(128)}"\n'


def selection():
    return (MARKER + '\n'
        f'set selected_organization {SPLIT}\n'
        'if {[info exists ::env(AKV_STORAGE_ORGANIZATION)]} {\n'
        '  set selected_organization $::env(AKV_STORAGE_ORGANIZATION)\n}\n'
        'switch -- $selected_organization {\n'
        f'  {SPLIT} {{\n' + declarations(SPLIT) +
        '    set storage_libraries [list $context_sram_library $kv_sram_library]\n  }\n'
        f'  {UNIFIED} {{\n' + declarations(UNIFIED) +
        '    set storage_libraries [list $q_sram_library $kv_sram_library]\n  }\n'
        '  default {error "unsupported AKV_STORAGE_ORGANIZATION: $selected_organization"}\n}\n'
        '# END_AKV_STANDALONE_STORAGE_SELECTION_V2\n')


AGREEMENT = ('if {$organization ne $selected_organization} {\n'
             '  error "AKV SRAM selection/hierarchy mismatch: selected=$selected_organization actual=$organization"\n'
             '}\n\n')


def render(name, source):
    if name == MAKEFILE:
        if 'dc_akv_storage_organization' in source:
            raise ValueError('Makefile organization selection already present')
        c = old.Changes(source)
        c.replace('dc_preflight_locked: dc_flist_locked\n',
                  '# Promoted resource package; override explicitly for a legacy source graph.\n'
                  'dc_akv_storage_organization ?= $(if $(filter 1,$(akv) $(akv_v2)),unified_q64x256_kv128x256,split_v1_96x256_v2_128x256)\n\n'
                  'dc_preflight_locked: dc_flist_locked\n')
        c.replace('\t\t$(if $(filter 1,$(akv_v2)),--require-akv-v2,) \\\n',
                  '\t\t$(if $(filter 1,$(akv_v2)),--require-akv-v2,) \\\n'
                  '\t\t$(if $(filter 1,$(akv) $(akv_v2)),--akv-storage-organization $(dc_akv_storage_organization),) \\\n')
        return c.finish()
    result = old.render(name, source)
    c = old.Changes(result)
    if name == STANDALONE:
        c.block('set q_sram_library ', 'set synthetic_library ', selection())
        c.replace('foreach required_file [list $dc_filelist $wrapper $project_sdc $std_library \\\n'
                  '                            $context_sram_library $kv_sram_library $q_sram_library $synthetic_library] {',
                  'foreach required_file [concat [list $dc_filelist $wrapper $project_sdc $std_library $synthetic_library] $storage_libraries] {')
        c.replace('set_app_var link_library "* $std_library $context_sram_library $kv_sram_library $q_sram_library $synthetic_library"',
                  'set_app_var link_library [concat [list * $std_library] $storage_libraries [list $synthetic_library]]')
        c.replace('set macro_area 0.0\n', AGREEMENT + 'set macro_area 0.0\n')
    elif name == PREFLIGHT:
        c.replace('        if not options.require_akv_v2:\n'
                  '            raise PreflightError("unified storage requires --require-akv-v2")\n'
                  '        _require_sources(sources, UNIFIED_AKV_SOURCES)\n',
                  '        if not (options.require_akv or options.require_akv_v2):\n'
                  '            raise PreflightError("unified storage requires explicit AKV enablement")\n'
                  '        # Storage uses v2_context even when only legacy commands are enabled.\n'
                  '        _require_sources(sources, UNIFIED_AKV_SOURCES + AKV_V2_SOURCES)\n')
        c.replace('            required = options.require_akv_v2 if key == "akv_v2_sram_db" else options.require_qbs\n',
                  '            required = (options.require_akv_v2 or unified_storage) if key == "akv_v2_sram_db" else options.require_qbs\n')
    elif name == COLLECTOR:
        # Do not implement a Tcl parser or filter arbitrary library declarations.
        # Only this exact known selection block can discard its inactive branch.
        helper = ('def selected_standalone_libraries(text, organization):\n'
                  f'    marker = {MARKER!r}\n'
                  f'    block = {selection()!r}\n'
                  '    if marker not in text:\n        return text\n'
                  f'    branches = {{{SPLIT!r}: {declarations(SPLIT)!r}, {UNIFIED!r}: {declarations(UNIFIED)!r}}}\n'
                  '    if text.count(marker) != 1 or text.count(block) != 1 or organization not in branches:\n'
                  '        raise CollectionError("ambiguous standalone SRAM library selection")\n'
                  '    return text.replace(block, branches[organization], 1)\n\n\n')
        c.replace('def library_inputs(', helper + 'def library_inputs(')
        c.replace('        active = "\\n".join(\n',
                  '        text = selected_standalone_libraries(text, organization)\n'
                  '        active = "\\n".join(\n')
    return c.finish()


def render_caller(source):
    if 'dc_akv_storage_organization' in source:
        raise ValueError('Standalone caller organization already present')
    c = old.Changes(source)
    c.replace('synth-preflight: synth-wrapper-compile\n',
              'dc_akv_storage_organization ?= unified_q64x256_kv128x256\n\n'
              'synth-preflight: synth-wrapper-compile\n')
    c.replace('\t$(MAKE) -C $(ROOT)/hardware dc_preflight mc=1 qbs=1 akv_v2=1\n',
              '\t$(MAKE) -C $(ROOT)/hardware dc_preflight mc=1 qbs=1 akv_v2=1 dc_akv_storage_organization=$(dc_akv_storage_organization)\n')
    c.replace('\t\t--require-macro-sram --nr-lanes 4 --vlen 1024\n',
              '\t\t--require-macro-sram --nr-lanes 4 --vlen 1024 \\\n'
              '\t\t--akv-storage-organization $(dc_akv_storage_organization)\n')
    return c.finish()


def prepare(root, output):
    sha = lambda data: hashlib.sha256(data).hexdigest()
    helpers = [p for d in (HERE, V1) for p in d.iterdir() if p.is_file()]
    helpers += [CALLER_INPUT, PACKAGE_PATCH]
    pins = {str(p): sha(p.read_bytes()) for p in helpers}
    originals = {name: text(root / name) for name in TARGETS}
    changed = {name: render(name, value) for name, value in originals.items()}
    caller_before = text(CALLER_INPUT)
    caller_after = render_caller(caller_before)
    output.mkdir(parents=True, exist_ok=False)
    patch = ''
    for name in TARGETS:
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(changed[name].encode())
        patch += ''.join(difflib.unified_diff(originals[name].splitlines(keepends=True),
                      changed[name].splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name))
    (output / 'physical_flow.patch').write_bytes(patch.encode())
    caller_path = output / CALLER_TARGET
    caller_path.parent.mkdir(parents=True, exist_ok=True)
    caller_path.write_bytes(caller_after.encode())
    caller_patch = ''.join(difflib.unified_diff(caller_before.splitlines(keepends=True),
                          caller_after.splitlines(keepends=True),
                          fromfile='a/' + CALLER_TARGET, tofile='b/' + CALLER_TARGET))
    (output / 'standalone_caller.patch').write_bytes(caller_patch.encode())
    if any(text(root / name) != value for name, value in originals.items()):
        raise ValueError('Source changed during generation')
    if any(sha(Path(p).read_bytes()) != value for p, value in pins.items()):
        raise ValueError('Helper changed during generation')
    receipt = dict(state='STATIC_PHYSICAL_FLOW_COMPATIBILITY_V2_NOT_APPLIED',
                   compiler_invoked=False, libraries_measured=False, ppa_closed=False,
                   inputs={str(root / n): sha(v.encode()) for n, v in originals.items()},
                   after={n: sha(v.encode()) for n, v in changed.items()},
                   helper_pins=pins, patch_sha256=sha(patch.encode()),
                   standalone_default=SPLIT, standalone_opt_in=UNIFIED,
                   standalone_caller=dict(input=str(CALLER_INPUT), target=CALLER_TARGET,
                       before_sha256=sha(caller_before.encode()), after_sha256=sha(caller_after.encode()),
                       patch_sha256=sha(caller_patch.encode())),
                   patch_apply_order=[str(PACKAGE_PATCH), str(output / 'physical_flow.patch'),
                                      str(output / 'standalone_caller.patch')])
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source_root.resolve(strict=True), args.output.resolve())
