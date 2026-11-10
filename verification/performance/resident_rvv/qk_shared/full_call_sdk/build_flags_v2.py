#!/usr/bin/env python3
"""Narrow PV counter-boundary successor; never changes build01 or live helpers."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE = OUT/'stage3_attention_sdk_build_20261110_01'
BASE_SHA = 'c722d476cc1f73f14711e1b9cc24b111b0609d9ba42574b868aa2ee3ad054653'
BASE_PINS_SHA = '1d506a9b106f640c6c0eabf36a0d346f9a80598165a92fc066f830c49e3784ff'
ORIGINALS = ('main.c','fixture.py','build.py','check.py','test_sdk.py','README.md')
NEW = ('build_flags_v2.py','test_flags_v2.py')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(pins):
    for path,value in pins.items():
        need(sha(path)==value,'Identity drift: '+path)


def replace_once(text,before,after):
    need(text.count(before)==1,'Successor source anchor changed: '+before[:72])
    return text.replace(before,after,1)


def sources(original):
    result = dict(original)
    result['fixture.py'] = replace_once(result['fixture.py'],
        "            a.phase = (head,start,'PV')\n            half_alpha =",
        "            a.phase = (head,start,'PV_PREP')\n            half_alpha =")
    result['fixture.py'] = replace_once(result['fixture.py'],
        "            coefficients = [a.cast(32,16,x) for x in scores]\n            for token, coefficient",
        "            coefficients = [a.cast(32,16,x) for x in scores]\n            a.phase = (head,start,'PV')\n            for token, coefficient")
    result['fixture.py'] = replace_once(result['fixture.py'],
        '    receipt = dict(cases=list(CASES), results=results, memory=memory,',
        "    require(results[2]['expf_samples'] == [dict(input=0,output=0x3f800000,fflags=0)]*6,\n"
        "            'New derived expf inputs require target-libm portability evidence')\n"
        '    receipt = dict(cases=list(CASES), results=results, memory=memory,\n'
        "        counter_semantics=dict(PV_PREP='Software cast/rescale/coefficient flags only',\n"
        "            PV='Token-ordered hardware FMA flags only; excludes prep and incoming sticky'),\n"
        "        scalar_expf_portability=dict(derived='All six inputs +0: expf(+0)=1 exactly, flags=0; no host/target approximation assumption',\n"
        "            original='Existing original tile64 golden SHA regression only; NOT a general glibc/newlib equivalence proof'),")
    result['test_sdk.py'] = replace_once(result['test_sdk.py'],
        "if __name__ == '__main__':\n    unittest.main()",
        "from test_flags_v2 import FlagsTest\n\n\nif __name__ == '__main__':\n    unittest.main()")
    own = "OWN = ('main.c','fixture.py','build.py','check.py','test_sdk.py','README.md')"
    result['build.py'] = replace_once(result['build.py'],own,
        own+" + ('test_flags_v2.py','flags-v2-contract.json')")
    result['build.py'] = replace_once(result['build.py'],
        '        for name in OWN:\n            builder.pin(HERE/name)',
        "        contract = json.loads((HERE/'flags-v2-contract.json').read_text())\n"
        "        verify(contract['source_inputs'])\n"
        "        verify(contract['generated_sources'])\n"
        "        builder.pins.update(contract['source_inputs'])\n"
        "        builder.pins.update(contract['generated_sources'])\n"
        '        for name in OWN:\n            builder.pin(HERE/name)')
    result['build.py'] = replace_once(result['build.py'],'host_tests=15,host_tests_log=',
                                    'host_tests=18,host_tests_log=')
    result['README.md'] += (
        '\n## PV Counter Boundary Successor\n\n'
        'This explicit successor preserves build01 and all original helpers. PV_PREP\n'
        'contains software alpha cast, seed rescale and probability casts. PV contains\n'
        'only token-ordered hardware FMAs; hardware probes exclude both preparation\n'
        'and incoming sticky flags. Whole-call natural flags/outputs are unchanged.\n'
        'The six derived scalar expf inputs must all be +0, yielding exact1 and flags0;\n'
        'any other derived sample stops preparation pending target-libm evidence.\n'
        'Original golden SHA regression is not general glibc/newlib equivalence.\n'
        'Use test_sdk.py for all18 tests (including the new phase/mutation tests).\n')
    return result


def prepare(output):
    output = Path(output).resolve()
    need(output.parent==OUT and re.fullmatch(r'stage3_attention_sdk_build_\d{8}_\w+',output.name)
         and not output.exists(),'Fresh owned build output required')
    bundle = OUT/output.name.replace('_build_','_flags_sources_')
    need(not bundle.exists(),'Preserve previous source bundles')
    need(sha(BASE/'build.json')==BASE_SHA and sha(BASE/'source-pins.json')==BASE_PINS_SHA,
         'Frozen build01 receipt changed')
    meta = json.loads((BASE/'build.json').read_text())
    original_pins = json.loads((BASE/'source-pins.json').read_text())
    need(meta['state']=='BUILT_NOT_EXECUTED' and meta['source_pins_sha256']==BASE_PINS_SHA,
         'Unexpected predecessor state')
    verify(original_pins)
    verify(meta['artifacts'])
    original = {name:(BASE/'inputs/fixture'/name).read_text() for name in ORIGINALS}
    updated = sources(original)
    bundle.mkdir()
    inputs = {str(BASE/'build.json'):BASE_SHA,str(BASE/'source-pins.json'):BASE_PINS_SHA}
    inputs.update({str(BASE/'inputs/fixture'/name):sha(BASE/'inputs/fixture'/name) for name in ORIGINALS})
    inputs.update({str(HERE/name):sha(HERE/name) for name in NEW})
    patch = ''.join(''.join(difflib.unified_diff(original[name].splitlines(True),
                      updated[name].splitlines(True),fromfile='a/'+name,tofile='b/'+name))
                    for name in ORIGINALS)
    (bundle/'flags-v2.patch').write_text(patch)
    inputs[str(bundle/'flags-v2.patch')] = sha(bundle/'flags-v2.patch')
    for name,text in updated.items():
        (bundle/name).write_text(text)
    shutil.copyfile(HERE/'test_flags_v2.py',bundle/'test_flags_v2.py')
    generated = {str(bundle/name):sha(bundle/name) for name in (*ORIGINALS,'test_flags_v2.py')}
    contract = dict(schema='sdk-pv-counter-boundary-v2',source_inputs=inputs,generated_sources=generated,
        scope='Test-side phase attribution only; unchanged firmware/production and scalar expf zero-input proof')
    (bundle/'flags-v2-contract.json').write_text(json.dumps(contract,indent=2,sort_keys=True)+'\n')
    report = dict(state='FAIL',source_bundle=str(bundle),build=str(output),rtl_executed=False,
                  predecessor=str(BASE),predecessor_unchanged=True,simulator_launched=False)
    try:
        verify(inputs)
        with (bundle/'build.stdout.log').open('x') as stream:
            command = [sys.executable,'-B',str(bundle/'build.py'),'--output',str(output)]
            proc = subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=300,check=False)
        need(proc.returncode==0,'Successor host/firmware build failed; preserve logs')
        receipt = json.loads((output/'build.json').read_text())
        need(receipt['state']=='BUILT_NOT_EXECUTED' and receipt['host_tests']==18,'Successor build incomplete')
        for index in range(3):
            need(sha(output/('golden_%d.bin'%index))==sha(BASE/('golden_%d.bin'%index)),
                 'Counter-only correction changed numerical golden')
        need([r['natural_flags'] for r in receipt['fixture']['results']]==[3,3,3] and
             [r['expected_fcsr'] for r in receipt['fixture']['results']]==[3,11,3],
             'Counter-only correction changed whole-call flags')
        verify(inputs)
        verify(generated)
        verify(original_pins)
        report.update(state='BUILT_NOT_EXECUTED',host_tests=18,elf_sha256=receipt['elf_sha256'],
            source_pins_sha256=receipt['source_pins_sha256'],build_sha256=sha(output/'build.json'),
            numerical_golden_unchanged=True,whole_call_flags_unchanged=True,
            elf_identical_to_build01=receipt['elf_sha256']==meta['elf_sha256'],
            scalar_expf_portability=receipt['fixture']['scalar_expf_portability'],post_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    (bundle/'prepare.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    report = prepare(args.output)
    print(json.dumps(report,indent=2))
    raise SystemExit(int(report['state']!='BUILT_NOT_EXECUTED'))
