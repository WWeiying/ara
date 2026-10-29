#!/usr/bin/env python3
"""Check the isolated whole-executor candidate against existing reference tests."""
import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from value_cache_sources import generate, replace_once, HERE, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = generate(out)
    fixture = HERE / 'test_execute.c'
    raw = fixture.read_text()
    # qbs_ref_execute reports one command's flags and clears host flags first.
    # The host command adapter must emulate architectural sticky accumulation.
    raw = replace_once(raw, '  float packed[128];qbs_ref_result_t report;',
        '  float packed[128];qbs_ref_result_t report;\n'
        '  int saved_flags=fetestexcept(FE_ALL_EXCEPT);')
    raw = replace_once(raw, '  for(unsigned row=0;row<m;++row) memcpy(out+',
        '  feraiseexcept(saved_flags);\n'
        '  for(unsigned row=0;row<m;++row) memcpy(out+')
    raw = replace_once(raw, '  bindings.execute=multi_execute;bindings.executor_context=NULL;',
        '  bindings.execute=multi_execute;bindings.executor_context=NULL;\n'
        '  feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);')
    raw = replace_once(raw, '  // Invalid last query',
        '  observed_flags[observed_count++]=fetestexcept(FE_ALL_EXCEPT);\n'
        '  assert(observed_flags[observed_count-1]&FE_DIVBYZERO);\n'
        '  // Invalid last query')
    body = raw[raw.index('int main(void)'):]
    body = body.replace('int main(void)', 'static void candidate_tests(void)')
    body = body.replace('scratch', 'candidate_scratch')
    body = body.replace('quant_prefill_execute(', 'vcache_execute(')
    body = '\n'.join(line.replace('&report)', '&report,decode)')
                     if 'vcache_execute(' in line else line for line in body.split('\n'))
    body = replace_once(body, 'report.native.value_decodes==260', 'report.native.value_decodes==196')
    body = body.replace('PREFILL_EXECUTE_PASS', 'PREFILL_VCACHE_EXECUTE_PASS')
    # Original fixture compares every output bit with separate per-query runs,
    # including untouched padding and partial writes after command failure.
    text = '#include <fenv.h>\nstatic int observed_flags[2];\nstatic unsigned observed_count;\n'
    text += raw.replace('int main(void)', 'static void original_tests(void)')
    text += '\n#include "value_cache_execute.h"\nstatic vcache_workspace_t candidate_scratch;\n' + body
    text += r'''
int main(void) {
  original_tests();
  submitted=fail_on=0; fail_after_group=NULL;
  candidate_tests();
  assert(observed_count==2 && observed_flags[0]==observed_flags[1]);
  quant_prefill_report_t report;
  akv_quant_native_bindings_t bindings={quantize,decode,scale,mad,multi_execute,NULL};
  submitted=quant_calls=decode_calls=0;
  /* No capability means rejection even before reading request tensors. */
  assert(vcache_execute(NULL,&bindings,&candidate_scratch,sizeof(candidate_scratch),
                        &report,NULL)==AKV_QUANT_NATIVE_FALLBACK);
  assert(!submitted && !quant_calls && !decode_calls);
  printf("PREFILL_VCACHE_PAIR_PASS production_unchanged=1 decoder_optin=1 host_flags_equal=1\n");
  return 0;
}
'''
    (out / 'test.c').write_text(text)
    command = ['/usr/bin/clang', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
        '-fno-fast-math', '-ffp-contract=off', '-fsanitize=address,undefined',
        '-fno-sanitize-recover=all', '-I'+str(out), '-I'+str(HERE), '-I'+str(ROOT),
        '-I'+str(ROOT/'software/qbs/include'), str(out/'test.c'),
        str(ROOT/'software/akv/experimental/quantized_kv/runtime.c'),
        str(ROOT/'software/qbs/src/qbs_runtime.c'), str(ROOT/'verification/qbs/qbs_ref.c'),
        '-lm', '-o', str(out/'test')]
    pins = {}
    def pin(path):
        path = Path(path).resolve(strict=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if str(path) in pins and pins[str(path)] != digest:
            raise ValueError('Input drift: '+str(path))
        pins[str(path)] = digest
    for path in inputs + [fixture, Path(__file__)]:
        pin(path)
    sources = [arg for arg in command if arg.endswith('.c')]
    common = [arg for arg in command[:command.index('-o')] if arg not in sources and arg != '-lm']
    for source in sources:
        deps = subprocess.check_output([*common, '-M', '-MT', 'object', source], text=True, timeout=60)
        for path in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1]):
            pin(path)
    with (out/'build.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (out/'test.log').open('x') as log:
        subprocess.run([out/'test'], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    for path, digest in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Input drift: '+path)
    (out/'result.json').write_text(json.dumps(dict(state='PASS',
        scope='host complete executor reference, not real RVV decoder or RTL performance',
        source_pins=pins, command=command), indent=2)+'\n')
    print((out/'test.log').read_text())


if __name__ == '__main__':
    main()
