#!/usr/bin/env python3
"""Read-only uniqueness and wrong-routing sensitivity proof for frozen build01."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BUILD = OUT/'stage3_attention_sdk_build_20261110_01'
BUILD_SHA = 'c722d476cc1f73f14711e1b9cc24b111b0609d9ba42574b868aa2ee3ad054653'
PINS_SHA = '1d506a9b106f640c6c0eabf36a0d346f9a80598165a92fc066f830c49e3784ff'
SOURCE_SHA = '0d250640fab33a655da7c61a3431601ca8e7c1ede1fe0819d3c47609ed9fac23'
OWN = ('fixture_quality.py','test_fixture_quality.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def verify(pins):
    for path,value in pins.items():
        require(sha(path) == value,'Identity changed: '+path)


def baseline():
    require(sha(BUILD/'build.json') == BUILD_SHA and
            sha(BUILD/'source-pins.json') == PINS_SHA,'Frozen build01 identity')
    meta = json.loads((BUILD/'build.json').read_text())
    pins = json.loads((BUILD/'source-pins.json').read_text())
    require(meta['state'] == 'BUILT_NOT_EXECUTED' and meta['post_pins_match'] is True and
            meta['source_pins_sha256'] == PINS_SHA,'Frozen build01 state')
    verify(pins)
    verify(meta['artifacts'])
    source = BUILD/'inputs/fixture/fixture.py'
    require(sha(source) == SOURCE_SHA,'Not the frozen arithmetic/source mapping')
    spec = importlib.util.spec_from_file_location('sdk_quality_frozen_reference',source)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    data,used = fixture.inputs()
    used.update({str(BUILD/name):sha(BUILD/name) for name in
        ('build.json','source-pins.json','fixture.json','golden_0.bin','golden_1.bin','golden_2.bin')})
    used[str(source)] = SOURCE_SHA
    for role in ('query','key','value','mask'):
        path = BUILD/('fixture_2_'+role+'.bin')
        require(path.read_bytes() == data[2][role],'Frozen derived source view mismatch')
        used[str(path)] = sha(path)
    return fixture,meta,data,used,pins


def uniqueness(fixture,case,data,result):
    d,heads,groups = (case[k] for k in ('dimension','heads','kv_heads'))
    require((d,heads,groups,case['tokens'],case['capacity']) == (96,6,2,65,65),
            'Not the bounded derived shape')
    qhalf = bytes.fromhex(result['query_half'])
    fingerprints = dict(
        query_f32_active=[digest(data['query'][h*512:h*512+d*4]) for h in range(heads)],
        query_f16_active=[digest(qhalf[h*d*2:(h+1)*d*2]) for h in range(heads)],
        output_f32=[digest(fixture.pack(result['bits'][h*d:(h+1)*d],32)) for h in range(heads)])
    for name,values in fingerprints.items():
        require(len(values) == heads and len(set(values)) == heads,'Repeated derived row: '+name)
    for role in ('key','value'):
        active = [b''.join(data[role][(g*65+t)*256:(g*65+t)*256+d*2]
                           for t in range(65)) for g in range(groups)]
        require(len(set(active)) == groups,'Repeated active KV group: '+role)
        fingerprints[role+'_active_groups'] = list(map(digest,active))
    return fingerprints


def mutations(data):
    # Wrong local H1 base2->0 affects head2/head5, separately from global FULL.
    query = bytearray(data['query'])
    for dst,src in ((2,0),(5,3)):
        query[dst*512:(dst+1)*512] = data['query'][src*512:(src+1)*512]
    result = [('local_base2_uses_base0',dict(data,query=bytes(query)),[2,5])]
    query = data['query'][:3*512]*2
    result.append(('stale_full_query_group1',dict(data,query=query),[3,4,5]))
    for role in ('key','value'):
        changed = dict(data)
        changed[role] = data[role][:65*256]*2
        result.append(('stale_full_'+role+'_group1',changed,[3,4,5]))
    return result


def audit():
    fixture,meta,data,pins,original_pins = baseline()
    case = fixture.CASES[2]
    reference = fixture.reference(case,data[2])
    require(reference['bits'] == meta['fixture']['results'][2]['bits'] and
            fixture.pack(reference['bits'],32) == (BUILD/'golden_2.bin').read_bytes(),
            'Independent recomputation differs from frozen derived golden')
    fingerprints = uniqueness(fixture,case,data[2],reference)
    # Assert the exact bit permutations, including active row strides. Group
    # mapping is a token rotation of the 256-row capture, cropped to 65 tokens.
    q = fixture.unpack(data[0]['query'],32)
    wanted_q = fixture.pack([q[(h%2)*128+(d+7*h)%128]
                             for h in range(6) for d in range(128)],32)
    require(data[2]['query'] == wanted_q,'Query dimension-rotation provenance')
    for role in ('key','value'):
        wanted = b''.join(data[0][role][((t+64*g)%256)*256:((t+64*g)%256+1)*256]
                          for g in range(2) for t in range(65))
        require(data[2][role] == wanted,'KV token-rotation provenance: '+role)
    sensitivity = []
    for name,changed,expected_heads in mutations(data[2]):
        result = fixture.reference(case,changed)
        counts = [sum(a!=b for a,b in zip(reference['bits'][h*96:(h+1)*96],
                                         result['bits'][h*96:(h+1)*96])) for h in range(6)]
        require([h for h,count in enumerate(counts) if count] == expected_heads,
                'Wrong routing not detected in every affected head: '+name)
        sensitivity.append(dict(mutation=name,changed_heads=expected_heads,
            differing_f32_per_head=counts,golden_sha256=digest(fixture.pack(result['bits'],32)),
            fflags=result['natural_flags']))
        pins.update(result['oracle_pins'])
    verify(original_pins)
    require(sha(BUILD/'build.json') == BUILD_SHA,'Sealed run was changed')
    return dict(state='PASS',scope='Host-only derived-fixture routing sensitivity; no RTL execution',
        source_build=str(BUILD),source_build_sha256=BUILD_SHA,elf_sha256=meta['elf_sha256'],
        source_build_pins_sha256=PINS_SHA,calls=3,fixture_changed=False,
        original_d128_golden_sha256=sha(BUILD/'golden_0.bin'),
        derived_golden_sha256=sha(BUILD/'golden_2.bin'),fingerprints=fingerprints,
        mapping=dict(query='captured_Q[h%2,(d+7*h)%128], active d<96',
            key_value='captured_KV[(t+64*g)%256,d], active t<65,d<96; physical row128 F16',
            transforms='Raw-bit permutations; no sign or magnitude change',
            provenance='Deterministically derived six distinct rows/two distinct groups; '
                       'NOT six captured Qwen3 heads'),
        mutations=sensitivity,rtl_executed=False,performance_measured=False,
        original_build_post_pins_match=True),pins


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.parent == OUT and output.name.startswith('stage3_attention_sdk_fixture_quality_')
            and not output.exists(),'Fresh owned sidecar output required')
    output.mkdir()
    pins = {str(HERE/name):sha(HERE/name) for name in OWN}
    pins[str(Path(sys.executable).resolve())] = sha(Path(sys.executable).resolve())
    report = dict(state='FAIL',rtl_executed=False,performance_measured=False)
    try:
        with (output/'hosttests.log').open('x') as stream:
            proc = subprocess.run([sys.executable,'-B',HERE/'test_fixture_quality.py','-v'],
                stdout=stream,stderr=subprocess.STDOUT,timeout=60,check=False)
        require(proc.returncode == 0,'Fixture-quality host tests failed')
        report,used = audit()
        pins.update(used)
        verify(pins)
        (output/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
        report.update(host_tests=6,source_pins_sha256=sha(output/'source-pins.json'),post_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p):sha(p) for p in output.iterdir() if p.is_file()}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
