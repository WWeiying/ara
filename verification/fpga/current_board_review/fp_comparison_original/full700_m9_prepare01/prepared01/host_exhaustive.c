#include <stdint.h>
#include <stdio.h>
#include <assert.h>
typedef uint16_t word;
struct fixture {unsigned bit, flags;};
#include "fixtures.h"
#include "tables.h"

int main(void) {
    unsigned n=0, flags_checks=0;
    unsigned lengths[]={0,1,2,3,256,511,512};
    unsigned long long byte_checks=0, input_checks=0;
    for(unsigned seed=0;seed<32;++seed)for(unsigned op=0;op<10;++op)
    for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
    for(unsigned sticky=0;sticky<2;++sticky) {
        const struct packed_case *c=&packed_cases[n];
        unsigned vl=lengths[l], flags=sticky;
        assert(c->seed==seed && c->op==op && c->vl==vl && c->mode==mode && c->sticky==sticky);
        for(unsigned i=0;i<512;++i) {
            unsigned ai=(i+seed+7*(seed/16))%16;
            unsigned bi=op<4 ? (i*3+seed*5+seed/16)%16 : seed%16;
            unsigned av=(input_rows[c->ai][i/4]>>(16*(i%4)))&65535;
            unsigned bv=(input_rows[c->bi][i/4]>>(16*(i%4)))&65535;
            assert(av==inputs[ai] && bv==inputs[bi]);
            input_checks+=2;
            if(i<vl) flags|=expected[op<4 ? op:op-4][ai][bi].flags;
        }
        assert(flags==c->flags);
        ++flags_checks;
        /* Exhaust every byte value, not merely the chosen Spike result. */
        for(unsigned j=0;j<64;++j)for(unsigned value=0;value<256;++value) {
            unsigned original_bad=0;
            for(unsigned b=0;b<8;++b) {
                unsigned i=8*j+b, actual=(value>>b)&1;
                unsigned ai=(i+seed+7*(seed/16))%16;
                unsigned bi=op<4 ? (i*3+seed*5+seed/16)%16 : seed%16;
                unsigned wanted=expected[op<4 ? op:op-4][ai][bi].bit;
                unsigned old=(inputs[(i/16+seed+7*(seed/16))%16]>>(i%16))&1;
                if(i<vl) original_bad|=actual!=wanted;
                else if(vl==0) original_bad|=actual!=old;
                else original_bad|=actual!=old && actual!=1 && actual!=wanted;
            }
            unsigned packed_bad=(value&c->zero[j])|((~value)&c->one[j]);
            assert((!!packed_bad)==(!!original_bad));
            ++byte_checks;
        }
        if(++n==700)goto done;
    }
done:
    assert(n==700 && input_checks==716800 && byte_checks==11468800);
    printf("HOST_PASS calls=%u inputs=%llu exhaustive_bytes=%llu flags=%u\n",
           n,input_checks,byte_checks,flags_checks);
}
