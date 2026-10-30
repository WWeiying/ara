#!/usr/bin/env python3
"""Isolate the remaining Prefill per-element nonfinite branch for comparison."""
import argparse
import hashlib
import json
import shlex
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=ROOT/'software/akv/experimental/quantized_kv/prefill/admission.h'


def candidate(text):
    old='          if((bits&0x7f800000u)==0x7f800000u) return AKV_QUANT_SELECT_NONFINITE;\n'
    anchor='        if(amax && (amax<0x03800000u || amax>0x4afde040u))'
    if text.count(old)!=1 or text.count(anchor)!=1:
        raise ValueError('Ambiguous admission body')
    text=text.replace(old,'').replace(anchor,
        '        if(amax>=0x7f800000u) return AKV_QUANT_SELECT_NONFINITE;\n'+anchor)
    return text.replace('quant_prefill_','candidate_prefill_').replace('QUANT_PREFILL_','CANDIDATE_PREFILL_')


TEST=r'''
#include "candidate.h"
static unsigned comparisons;
static void compare(quant_prefill_input_t *p) {
  quant_prefill_admission_t a;
  candidate_prefill_admission_t b;
  candidate_prefill_input_t request={p->tensors,p->mask_row_stride};
  memset(&a,0xa5,sizeof(a));memset(&b,0xa5,sizeof(b));
  feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);
  int before=fetestexcept(FE_ALL_EXCEPT);
  int ra=quant_prefill_admit(p,&a),fa=fetestexcept(FE_ALL_EXCEPT);
  int rb=candidate_prefill_admit(&request,&b),fb=fetestexcept(FE_ALL_EXCEPT);
  assert(ra==rb && fa==before && fb==before);
  if(ra==AKV_QUANT_SELECT_OK) {
    assert(a.queries==b.queries && !memcmp(a.visible,b.visible,sizeof(a.visible)));
    assert(a.common.group_heads==b.common.group_heads && a.common.kv_heads==b.common.kv_heads &&
      a.common.dim==b.common.dim && a.common.visible_tokens==b.common.visible_tokens &&
      a.common.key_profile==b.common.key_profile && a.common.key_row_bytes==b.common.key_row_bytes &&
      a.common.query_quant_row_bytes==b.common.query_quant_row_bytes);
  } else {
    for(size_t i=0;i<sizeof(a);++i) assert(((unsigned char *)&a)[i]==0xa5);
    for(size_t i=0;i<sizeof(b);++i) assert(((unsigned char *)&b)[i]==0xa5);
  }
  unchanged_output();++comparisons;
}
int main(void) {
  original_admission_tests();
  const uint32_t values[]={0,0x80000000,1,0x037fffff,0x03800000,0x4afde040,
    0x4afde041,0x7f7fffff,0x7f800000,0xff800000,0x7fc00000,0x7f800001,0xffc12345};
  for(unsigned row=0;row<4;++row) for(unsigned pos=0;pos<32;++pos)
    for(unsigned v=0;v<sizeof(values)/sizeof(values[0]);++v) {
      quant_prefill_input_t p=fixture();
      memset(multi_query[7][row]+96,0,32*4);
      memcpy(&multi_query[7][row][96+pos],&values[v],4);
      compare(&p);
    }
  uint32_t state=37;
  for(unsigned test=0;test<2000;++test) {
    quant_prefill_input_t p=fixture();
    for(unsigned i=0;i<32;++i) {
      state=state*1664525u+1013904223u;
      memcpy(&multi_query[7][test%4][96+i],&state,4);
    }
    compare(&p);
  }
  printf("PREFILL_QUERY_GUARD_PASS comparisons=%u\n",comparisons);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    raw=SOURCE.read_text()
    (out/'candidate.h').write_text(candidate(raw))
    fixture=(HERE/'test_admission.c').read_text()
    if fixture.count('int main(void)')!=1:raise ValueError('Fixture main')
    (out/'test.c').write_text(fixture.replace('int main(void)','void original_admission_tests(void)')+TEST)
    command=['/usr/bin/clang','-std=gnu11','-O2','-Wall','-Wextra','-Werror',
        '-fno-fast-math','-ffp-contract=off',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all',
        '-I'+str(out),'-I'+str(HERE),'-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),
        str(out/'test.c'),str(ROOT/'software/akv/experimental/quantized_kv/runtime.c'),
        str(ROOT/'software/qbs/src/qbs_runtime.c'),str(ROOT/'verification/qbs/qbs_ref.c'),
        '-lm','-o',str(out/'test')]
    pins={}
    def pin(path):
        path=Path(path).resolve(strict=True)
        value=hashlib.sha256(path.read_bytes()).hexdigest()
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('Source drift')
        pins[str(path)]=value
    for path in (SOURCE,Path(__file__),HERE/'test_admission.c',out/'candidate.h'):
        pin(path)
    sources=[v for v in command if v.endswith('.c')]
    common=[v for v in command[:command.index('-o')] if v not in sources and v!='-lm']
    for source in sources:
        dependencies=subprocess.check_output([*common,'-M','-MT','object',source],text=True,timeout=60)
        for path in shlex.split(dependencies.replace('\\\n',' ').split(':',1)[1]):pin(path)
    with (out/'build.log').open('x') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    with (out/'test.log').open('x') as log:
        subprocess.run([out/'test'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    for path,value in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=value:raise ValueError('Source drift: '+path)
    (out/'result.json').write_text(json.dumps(dict(state='PASS',scope='host admission equivalence only',
        source_pins=pins,command=command,production_modified=False),indent=2)+'\n')
    print((out/'test.log').read_text())


if __name__=='__main__':main()
