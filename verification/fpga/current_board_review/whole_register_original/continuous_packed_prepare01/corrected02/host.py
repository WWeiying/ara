"""Generate bounded local differential tests from actual original/new C fragments."""
import json
import shutil
from prepare import HERE, OLD, read, save, sha, require, command


def run():
    out = HERE / 'host02'; out.mkdir()
    old = (OLD / 'case.c').read_text(); new = (HERE / 'case.c').read_text()
    start = old.index('            for(unsigned i=0;i<1088;++i){unsigned active=')
    end = old.index('            ++cases;', start)
    scalar = old[start:end].replace('i=0;i<1088', 'i=begin;i<end')
    start = new.index('            for(unsigned word=0;word<1088;word+=8){')
    end = new.index('            ++cases;', start)
    packed = new[start:end].replace('word=0;word<1088', 'word=begin;word<end')
    # Only the loop spans are parameterized; diagnostics and scalar byte body are literal source.
    signature = '(unsigned errors,unsigned op,unsigned mode,unsigned start,unsigned bytes,unsigned n,unsigned vlenb,unsigned begin,unsigned end)'
    prelude = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "packed.h"
static uint8_t input[1024] __attribute__((aligned(64)));
static uint8_t output[1088] __attribute__((aligned(64)));
static char diagnostic[4096];
static size_t diagnostic_size;
static void text(const char *s){size_t n=strlen(s);assert(diagnostic_size+n<sizeof diagnostic);
    memcpy(diagnostic+diagnostic_size,s,n+1);diagnostic_size+=n;}
static void num(uint64_t n){char b[32];snprintf(b,sizeof b,"%llu",(unsigned long long)n);text(b);}
'''
    functions = '\nstatic unsigned scalar_span' + signature + '{\n' + scalar + '\nreturn errors; }\n'
    functions += '\nstatic unsigned packed_span' + signature + '{\n' + packed + '\nreturn errors; }\n'
    cases = read(HERE / 'tuples.json')['cases']
    rows = ',\n'.join('{'+','.join(str(c[k]) for k in ('seed','op','mode','start','bytes','registers'))+'}' for c in cases)
    rest = r'''
struct Row {unsigned seed,op,mode,start,bytes,n;};
static const struct Row rows[] = {ROWS};
static unsigned long tests, corruption_tests, postinput_tests;
static unsigned compare(struct Row r,unsigned begin,unsigned end,unsigned initial){
    diagnostic_size=0;diagnostic[0]=0;
    unsigned a=scalar_span(initial,r.op,r.mode,r.start,r.bytes,r.n,128,begin,end);
    char expected[4096];memcpy(expected,diagnostic,diagnostic_size+1);
    diagnostic_size=0;diagnostic[0]=0;
    unsigned b=packed_span(initial,r.op,r.mode,r.start,r.bytes,r.n,128,begin,end);
    assert(a==b && strcmp(expected,diagnostic)==0);++tests;return a;
}
static unsigned status_errors(uint64_t status,unsigned start){
    unsigned errors=0;
    if((uint32_t)status || status>>32!=start)++errors;
    return errors;
}
int main(void){
    assert(sizeof rows/sizeof rows[0]==1134);
    for(unsigned c=0;c<1134;++c){
        struct Row r=rows[c];
        memset(input,0xa7,sizeof input);memset(output,0x13,sizeof output);
        packed_init(input,output,r.seed);
        for(unsigned i=0;i<1024;++i)assert(input[i]==(uint8_t)(i*37+r.seed*71+3));
        for(unsigned i=0;i<1088;++i)assert(output[i]==0x5b);
        unsigned lo=32+r.start*r.bytes,hi=32+r.n*128;
        for(unsigned i=lo;i<hi;++i)output[i]=input[i-32];
        assert(compare(r,0,1088,0)==0);
        for(unsigned word=0;word<1088;word+=8){
            uint64_t expected=0;
            for(unsigned j=0;j<8;++j){unsigned i=word+j;uint8_t byte=i>=lo&&i<hi?input[i-32]:0x5b;
                expected|=(uint64_t)byte<<(8*j);}
            assert(packed_expected(input,word,lo,hi)==expected);
            for(unsigned j=0;j<8;++j){
                output[word+j]^=(uint8_t)(1u<<j);
                const unsigned threshold[]={0,11,12};
                for(unsigned k=0;k<3;++k){assert(compare(r,word,word+8,threshold[k])==threshold[k]+1);++corruption_tests;}
                output[word+j]^=(uint8_t)(1u<<j);
            }
        }
        /* Cross-word guard errors plus a status error: exact threshold and order. */
        for(unsigned i=0;i<16;++i)output[i]^=1;
        assert(compare(r,0,16,1)==17);assert(compare(r,0,16,11)==27);
        for(unsigned i=0;i<16;++i)output[i]^=1;
        assert(status_errors((uint64_t)r.start<<32,r.start)==0);
        assert(status_errors(((uint64_t)r.start<<32)|1,r.start)==1);
        assert(status_errors((uint64_t)(r.start+1)<<32,r.start)==1);
        /* A changed CURRENT input must change expected, not be replaced by the seed ROM. */
        if(lo<hi){unsigned i=lo;input[i-32]^=0x80;
            assert(compare(r,i&~7u,(i&~7u)+8,0)==1);
            output[i]^=0x80;assert(compare(r,i&~7u,(i&~7u)+8,0)==0);++postinput_tests;}
    }
    /* Complete boundary masks, including cases not needing a partial high word in scope. */
    for(unsigned lo=32;lo<=40;++lo)for(unsigned hi=lo;hi<=40;++hi){
        uint64_t expected=0;for(unsigned j=0;j<8;++j)
            expected|=(uint64_t)(32+j>=lo&&32+j<hi?input[j]:0x5b)<<(8*j);
        assert(packed_expected(input,32,lo,hi)==expected);
    }
    printf("HOST_PACKED_EQUIVALENCE_PASS calls=1134 exclusions=366 tests=%lu corruptions=%lu postinput=%lu\n",tests,corruption_tests,postinput_tests);
    return 0;
}
'''.replace('ROWS', rows)
    with (out / 'locality.c').open('x') as f:f.write(prelude + functions + rest)
    cc = shutil.which('gcc'); require(cc, 'Host GCC')
    flags = ['-O2','-fno-tree-vectorize','-fno-tree-slp-vectorize','-fstrict-aliasing',
             '-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
             '-fno-sanitize-recover=all','-Wall','-Wextra','-Werror','-DDETAIL_BYTES=1']
    command([cc,*flags,'-I'+str(HERE),out/'locality.c','-o',out/'locality'],out/'compile.log',60)
    command([out/'locality'],out/'run.log',120)
    require('HOST_PACKED_EQUIVALENCE_PASS' in (out/'run.log').read_text(), 'Actual Host result')
    save(out/'result.json',dict(status='HOST_LOCAL_EQUIVALENCE_UBSAN_PASS_NOT_REFERENCE',
        original_fragment_sha256=__import__('hashlib').sha256(scalar.encode()).hexdigest(),
        actual_packed_fragment_sha256=__import__('hashlib').sha256(packed.encode()).hexdigest(),
        original_case_sha256=sha(OLD/'case.c'),case_sha256=sha(HERE/'case.c'),header_sha256=sha(HERE/'packed.h'),
        source=sha(out/'locality.c'),compiler=cc,compiler_sha256=sha(cc),
        run=read(out/'run.log.exit.json'),result=(out/'run.log').read_text(),
        method='1134 full positives; per-position corruption tests only the owning word, never repeat whole matrix',
        instruction_execution='Scalar Host only; RVV semantics require separate reference'))


if __name__ == '__main__':
    run()

