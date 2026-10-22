#!/usr/bin/env python3
"""Instantiate the accepted cap512 six-event checker, retaining full scalar oracle."""
import difflib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
H = HERE.parent
TEMPLATE = H / 'e8_m4_ops3_prefix66_event_recovery01/checker.py'
PREPARATION = H / 'vi0_missing2_prefix112_prepare03'


def generate(kind):
    ready_path = PREPARATION / kind / 'READY.json'
    ready = json.loads(ready_path.read_text())
    ref = Path(ready.get('original_artifact_root', str(ready_path.parent)))
    out = HERE / kind
    out.mkdir()
    sew, lmul = ready['sew'], ready['lmul']
    width, regs, vtype = sew // 8, int(lmul[1:]), (2 if sew == 8 else 11)
    scope = (ref / 'scope.py').read_text() + f'''
SOURCE_LABEL = {ready['source_label']!r}
SOC_ELF_SHA = {ready['soc_elf']['sha256']!r}
LOGICAL_MASK_BYTES = 64
SETUP_BYTES = {ready['setup_bytes_per_call']}
ENDPOINT = [0,2,0,6,3,3]
'''
    (out / 'newscope.py').write_text(scope)
    text = TEMPLATE.read_text()
    old_root = H / 'e8_m4_ops3_prefix66_vcs_m6_plan01'
    replacements = [
        (str(old_root), str(HERE)),
        ("REF = HERE.parent / 'e8_m4_ops3_prefix66_prepare01'", f'REF = Path({str(ref)!r})'),
        ("result['input'][31] == 177", f"result['input'][0] == {185 if sew == 8 else 61881}"),
        ("RUNTIME_ID + '_op_3'", "RUNTIME_ID + '_op_2'"),
        ('e8,m4,tu,mu', f'e{sew},{lmul},tu,mu'),
        ('308fbc57', '30803c57'),
        ("capacity['insn'] == '0022f557'", f"capacity['insn'] == '{vtype:03x}2f557'"),
        ('RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0',
         f'RVV_GATHER_PREFIX_PASS sew={sew} cases=112 errors=0'),
        ("addresses['output']+1", f"addresses['output']+{width}"),
        ("('input', expected['input'], 1), ('indices', expected['indices'], 1)",
         f"('input', expected['input'], {width}), ('indices', expected['indices'], {width})"),
        ("('output', [91]*(CAP+2), 1)", f"('output', [91]*(CAP+2), {width})"),
        ('(insn >> 15) & 31 == 31', '(insn >> 15) & 31 == 0'),
        ('Unsigned immediate31', 'Unsigned immediate0'),
        ("scalar=0, immediate=31, source31=expected['input'][31]", "scalar=0, immediate=0, source0=expected['input'][0]"),
        ("addresses['output']+CAP+2", f"addresses['output']+{width}*(CAP+2)"),
        ('(insn >> 12) & 7 == 4', f'(insn >> 12) & 7 == {4 if width == 1 else 5}'),
        ('rmask == 1 << (address % 8)', f'rmask == {((1 << width)-1)} << (address % 8)'),
        ("k = address-addresses['output']", f"require((address-addresses['output'])%{width} == 0, 'Oracle alignment')\n            k = (address-addresses['output'])//{width}"),
        ('PASS_RAW66_M4_FULL_SETUP_SCALAR_ORACLE', f'PASS_RAW112_{lmul.upper()}_VI0_FULL_SETUP_SCALAR_ORACLE'),
    ]
    for before, after in replacements:
        assert before in text, before
        text = text.replace(before, after)
    (out / 'checker.py').write_text(text)
    (out / 'checker.diff').write_text(''.join(difflib.unified_diff(
        TEMPLATE.read_text().splitlines(True), text.splitlines(True))))
    return ready_path, ref


def load(kind):
    folder = HERE / kind
    ready = json.loads((PREPARATION / kind / 'READY.json').read_text())
    ref = Path(ready.get('original_artifact_root', str(PREPARATION / kind)))
    previous = {name: sys.modules.get(name) for name in ('scope', 'newscope')}
    try:
        for name, path in (('scope', ref / 'scope.py'), ('newscope', folder / 'newscope.py')):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        spec = importlib.util.spec_from_file_location('owned_checker_' + kind, folder / 'checker.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, prior in previous.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
