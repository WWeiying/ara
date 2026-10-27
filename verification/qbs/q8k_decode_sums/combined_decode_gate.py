"""Build and independently check old/installed quantizer dispatch in model gate."""
import re


def sources(before):
    start=before.index('void quantize_row_q8_K(')
    end=before.index('//===================================== Dot products',start)
    prefix='#define GGML_COMMON_DECL_C\n#include "ggml-common.h"\n#include "ggml-quants.h"\n#include <riscv_vector.h>\n#include <math.h>\n#include <string.h>\n#include <assert.h>\n#define GGML_RESTRICT restrict\n'
    original=prefix+before[start:end].replace('void quantize_row_q8_K(','void decode_original(',1)
    wrapper=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
void decode_original(const float *,void *,int64_t);
void __real_quantize_row_q8_K(const float *,void *,int64_t);
static unsigned long old_calls,new_calls;
void __wrap_quantize_row_q8_K(const float *x,void *y,int64_t k) {
    const char *value=getenv("GGML_QBS_COMBINED_TEST");
    if(value && !strcmp(value,"0")) {
        ++old_calls;decode_original(x,y,k);
    } else if(value && !strcmp(value,"1")) {
        ++new_calls;__real_quantize_row_q8_K(x,y,k);
    } else abort();
}
__attribute__((destructor)) static void report(void) {
    const char *mode=getenv("GGML_QBS_COMBINED_TEST");
    printf("Q8K_COMBINED_DISPATCH mode=%s original=%lu installed=%lu\n",
           mode ? mode:"invalid",old_calls,new_calls);
}
'''
    return original,wrapper


def check_dispatch(text,activity):
    lines=[s for s in text.splitlines() if s.startswith('Q8K_COMBINED_DISPATCH ')]
    if len(lines)!=2:raise ValueError('Missing quantizer dispatch evidence')
    result=[]
    for mode,line in enumerate(lines):
        match=re.fullmatch(r'Q8K_COMBINED_DISPATCH mode=([01]) original=(\d+) installed=(\d+)',line)
        if not match or int(match[1])!=mode:raise ValueError('Quantizer dispatch identity')
        old,new=map(int,match.groups()[1:])
        expected=sum(g['calls'] for g in activity[str(mode)]['groups'] if g['m']==1)
        if expected<=0 or (old,new)!=((expected,0) if mode==0 else (0,expected)):
            raise ValueError('Quantizer dispatch does not reconcile with actual M1 preparations')
        result.append(dict(mode=mode,original=old,installed=new))
    return result
