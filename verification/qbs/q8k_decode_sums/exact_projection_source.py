"""Generate a successor with exact weight comparisons; timing body unchanged."""


def once(text,old,new):
    if text.count(old)!=1: raise ValueError('Source structure drift: '+old[:60])
    return text.replace(old,new,1)


def generate(text,kind):
    text=once(text,'#include "integrity_words.h"','#include "integrity_equal.h"')
    text=once(text,'unsigned errors=q8k_integrity_selftest();',
              'unsigned errors=q8k_integrity_equal_selftest();')
    if kind=='projection':
        text=once(text,'    if (count>=16384) return q8k_integrity_words(data,count);\n','')
        text=once(text,'extern const unsigned char projection_weights[];',
                  'extern const unsigned char projection_weights[],projection_weights_expected[];')
        check='!q8k_integrity_equal(projection_weights,projection_weights_expected,1536*6*144)'
        text=once(text,'    const uint64_t weight_hash=hash_bytes(projection_weights,1536*6*144);',
                  '    errors += '+check+';\n    errors += (uintptr_t)projection_weights==(uintptr_t)projection_weights_expected;')
        text=once(text,'weight_hash!=hash_bytes(projection_weights,1536*6*144)',check)
    elif kind=='qkv':
        text=once(text,'    if (bytes>=16384) return q8k_integrity_words(data,bytes);\n','')
        text=once(text,'extern const unsigned char q_weights[], k_weights[], v_weights[];',
                  'extern const unsigned char q_weights[], k_weights[], v_weights[];\n'
                  'extern const unsigned char q_weights_expected[],k_weights_expected[],v_weights_expected[];')
        text=once(text,'    const uint64_t ih=hash(qkv_input,1536*4),qh=hash(q_weights,1536*6*sizeof(block_q4_K));\n'
                  '    const uint64_t kh=hash(k_weights,256*6*sizeof(block_q4_K)),vh=hash(v_weights,256*6*sizeof(block_q6_K));',
                  '    const uint64_t ih=hash(qkv_input,1536*4);\n'+''.join(
                  f'    errors += !q8k_integrity_equal({n}_weights,{n}_weights_expected,{rows}*6*sizeof(block_{typ}));\n'
                  f'    errors += (uintptr_t){n}_weights==(uintptr_t){n}_weights_expected;\n'
                  for n,rows,typ in (('q',1536,'q4_K'),('k',256,'q4_K'),('v',256,'q6_K'))).rstrip())
        for n,rows,typ,h in (('q',1536,'q4_K','qh'),('k',256,'q4_K','kh'),('v',256,'q6_K','vh')):
            text=once(text,f'hash({n}_weights,{rows}*6*sizeof(block_{typ}))!={h}',
                      f'!q8k_integrity_equal({n}_weights,{n}_weights_expected,{rows}*6*sizeof(block_{typ}))')
    else: raise ValueError('Unknown experiment')
    return text
