"""Exact scoped derivation of the sealed native driver; ROI text is unchanged."""
from contract import require


def once(text,before,after):
    require(text.count(before)==1,'Frozen driver structure changed: '+before)
    return text.replace(before,after)


def roi_source(text):
    first=text.index('    uint64_t start = cycles();')
    last=text.index('    uintptr_t fc,vc;',first)
    return text[first:last]


def derive(text):
    old_roi=roi_source(text)
    begin=text.index('static uint64_t extensions_quant_hash(void) {')
    end=text.index('#include "native_prefix.h"',begin)
    text=text[:begin]+'#include "compare.h"\n#include "fixture.h"\nextern const unsigned char quantkv_expected_begin[],quantkv_expected_end[];\n'+text[end:]
    text=once(text,'  const uint64_t original_hash = extensions_quant_hash();',
        '  const quantkv_bytes_t initial=quantkv_compare_bytes(fixture_begin,quantkv_expected_begin,QUANTKV_BYTES);\n'
        '  printf("QKC_INITIAL bytes=%u checked=%lu first_fail=%ld state_errors=%u\\n",QUANTKV_BYTES,\n'
        '      (unsigned long)initial.checked,initial.first_fail,initial.state_errors);\n'
        '  if (initial.checked!=QUANTKV_BYTES || initial.first_fail!=-1 || initial.state_errors) return 1;')
    text=once(text,'    printf("EXT_QUANT_STATE trial=%u vstart=%lu inputs=%u\\n", trial, (unsigned long)vs, (unsigned)(extensions_quant_hash() == original_hash));',
        '    const quantkv_bytes_t bytecheck=quantkv_compare_bytes(fixture_begin,quantkv_expected_begin,QUANTKV_BYTES);\n'
        '    printf("QKC_BYTES trial=%u bytes=%u checked=%lu first_fail=%ld state_errors=%u\\n",trial,QUANTKV_BYTES,\n'
        '        (unsigned long)bytecheck.checked,bytecheck.first_fail,bytecheck.state_errors);\n'
        '    unsigned checked=0,guards=0; long first_fail=-1;')
    text=once(text,'    unsigned errors = vs != 0 || extensions_quant_hash() != original_hash || status != AKV_QUANT_OK',
        '    unsigned errors = vs != 0 || bytecheck.checked!=QUANTKV_BYTES || bytecheck.first_fail!=-1 ||\n'
        '      bytecheck.state_errors || status != AKV_QUANT_OK')
    text=once(text,'        errors += !isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);',
        '        const unsigned mismatch=!isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);\n'
        '        errors+=mismatch; ++checked;\n'
        '        if (mismatch && first_fail<0) first_fail=(long)(row*DIM+d);')
    text=once(text,'      for (unsigned d=DIM; d<STRIDE; ++d) errors += bits(output.data[row][d])!=0xa5a5a5a5u;',
        '      for (unsigned d=DIM; d<STRIDE; ++d) { errors += bits(output.data[row][d])!=0xa5a5a5a5u; guards+=4; }')
    text=once(text,'    for(unsigned i=0;i<64;++i) errors += output.before[i]!=0xa5 || output.after[i]!=0xa5;',
        '    for(unsigned i=0;i<64;++i) { errors += output.before[i]!=0xa5 || output.after[i]!=0xa5; guards+=2; }')
    text=once(text,'fcsr=%lu vcsr=%lu errors=%u hex=',
        'fcsr=%lu vcsr=%lu vstart=%lu checked=%u first_fail=%ld guards=%u errors=%u hex=')
    text=once(text,'      (unsigned long)fc,(unsigned long)vc,errors);',
        '      (unsigned long)fc,(unsigned long)vc,(unsigned long)vs,checked,first_fail,guards,errors);')
    text=once(text,'    for(unsigned row=0;row<ROWS;++row) for(unsigned d=0;d<DIM;++d) printf("%08x",bits(output.data[row][d]));',
        '    for(unsigned d=0;d<64;++d) printf("%08x",bits(output.data[0][d]));')
    require(roi_source(text)==old_roi and 'extensions_quant_hash' not in text,'ROI changed / FNV retained')
    return text
