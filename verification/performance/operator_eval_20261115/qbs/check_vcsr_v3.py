#!/usr/bin/env python3
"""Exact RVV saturation decoding, retaining the sealed VCSR/numeric audit."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
import check_vcsr_v2 as old

HERE = Path(__file__).resolve().parent
ENCODING = Path('/home/wangwy/openproject/ara/toolchain/riscv-isa-sim/riscv/encoding.h')
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
DEFAULT_PINS = OUT/'operator_qbs_prepare_20261115_vcsr_contract_v3_01/source-pins.json'
SATURATING = {
    'VSADDU_VV': 0x80000057, 'VSADDU_VX': 0x80004057, 'VSADDU_VI': 0x80003057,
    'VSADD_VV': 0x84000057, 'VSADD_VX': 0x84004057, 'VSADD_VI': 0x84003057,
    'VSSUBU_VV': 0x88000057, 'VSSUBU_VX': 0x88004057,
    'VSSUB_VV': 0x8c000057, 'VSSUB_VX': 0x8c004057,
    'VSMUL_VV': 0x9c000057, 'VSMUL_VX': 0x9c004057,
    'VNCLIPU_WV': 0xb8000057, 'VNCLIPU_WX': 0xb8004057, 'VNCLIPU_WI': 0xb8003057,
    'VNCLIP_WV': 0xbc000057, 'VNCLIP_WX': 0xbc004057, 'VNCLIP_WI': 0xbc003057,
}
MASK = 0xfc00707f


def is_saturating(word):
    return word & MASK in SATURATING.values()


def verify_encoding():
    text = ENCODING.read_text()
    for name, match in SATURATING.items():
        for field, expected in (('MATCH', match), ('MASK', MASK)):
            found = re.findall(r'^#define '+field+'_'+name+r' (0x[0-9a-f]+)$', text, re.M)
            old.require(len(found) == 1 and int(found[0], 16) == expected,
                        'Independent Spike saturation encoding mismatch: '+name)
    for word in (0x9e003057, 0x9e00b057, 0x9e01b057, 0x9e03b057, 0x9e7032d7):
        old.require(not is_saturating(word), 'Whole-register move classified as saturating')
    return dict(source=str(ENCODING), sha256=old.digest(ENCODING), mask=f'{MASK:08x}',
                exact_matches={name:f'{word:08x}' for name,word in SATURATING.items()})


def inventory(path):
    pins = old.verify_audit_pins(path)
    for file in (Path(__file__).resolve(), HERE/'test_vcsr_v3.py', ENCODING):
        old.require(pins.get(str(file)) == old.digest(file), 'V3 source/test/spec identity missing')
    return pins


def audit(args):
    old.verify_parser_delta()
    pins = inventory(args.audit_pins)
    encoding = verify_encoding()
    original = args.original_result or args.log.parent/'numerical.json'
    callback = old.is_saturating
    old.is_saturating = is_saturating
    try:
        if not args.fresh:
            result = old.audit_run(args.log, args.build, args.commit, original, args.audit_pins)
        else:
            old.require(not original.exists(), 'Fresh checker cannot bypass existing numerical evidence')
            build, build_path, build_pins = old.verify_build(args.build)
            data = build_path.parent/'data'
            packed = 'expected_q8.bin' if build['case']['backend']=='rvv' else 'expected_packed.bin'
            evidence = {str(p):old.digest(p) for p in (args.log, args.commit, build_path)}
            result = old.parse_log(args.log.read_text(), build, (data/'expected.bin').read_bytes(),
                (data/'expected_q8.bin').read_bytes(), (data/packed).read_bytes())
            proof = old.parse_commit(args.commit, build, result, old.elf_proof(build, build_pins))
            result.update(audit_kind='FRESH_STRICT_VCSR_CHECK', vcsr_evidence=proof,
                          original_worker_reclassified=False, build=str(build_path),
                          checked_input_hashes=evidence)
            for name, expected in {**build_pins, **evidence}.items():
                old.require(old.digest(name)==expected, 'Fresh evidence drift: '+name)
    finally:
        old.is_saturating = callback
    inventory(args.audit_pins)
    result.update(successor_v3_sha256=old.digest(__file__), exact_saturation_encoding=encoding,
        checker_correction='Final VCSR=2 after quantizer; exact RVV match/mask distinguishes vmvNr.v from vsmul; all numeric/guard/phase/CSR lineage gates retained',
        independent_protocol_checked=False)
    return result


def seal(directory):
    old.require(not directory.exists() and directory.parent == OUT, 'Fresh owned seal directory required')
    verify_encoding()
    pins = json.loads(old.DEFAULT_AUDIT_PINS.read_text())
    for name, expected in pins.items():
        old.require(old.digest(name)==expected, 'Sealed predecessor source drift: '+name)
    for file in (Path(__file__).resolve(), HERE/'test_vcsr_v3.py', ENCODING, old.DEFAULT_AUDIT_PINS):
        pins[str(file)] = old.digest(file)
    directory.mkdir()
    with (directory/'tests.log').open('x') as stream:
        subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_vcsr_v2', 'test_vcsr_v3'],
            cwd=HERE, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
    (directory/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (directory/'result.json').write_text(json.dumps(dict(state='HOST_CHECKER_TESTS_PASS_NOT_RTL',
        scope='Exact ISA decoder, strict predecessor gates, checker mutations; no simulator rerun',
        source_pins_sha256=old.digest(directory/'source-pins.json'),
        tests_log_sha256=old.digest(directory/'tests.log')),indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path)
    p.add_argument('--log',type=Path)
    p.add_argument('--commit',type=Path)
    p.add_argument('--original-result',type=Path)
    p.add_argument('--audit-pins',type=Path,default=DEFAULT_PINS)
    p.add_argument('--fresh',action='store_true')
    p.add_argument('--output',type=Path)
    p.add_argument('--seal',type=Path)
    a=p.parse_args()
    if a.seal:
        seal(a.seal.resolve()); return 0
    old.require(a.build and a.log and a.output and not a.output.exists(), 'Fresh audit output required')
    a.commit = a.commit or a.log.parent/'commit.csv'
    try:
        result = audit(a)
    except Exception as exc:
        result = dict(state='FAIL',error=repr(exc),original_worker_reclassified=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('metrics','vcsr_evidence')}))
    return result['state'] != 'PASS'


if __name__=='__main__':
    raise SystemExit(main())
