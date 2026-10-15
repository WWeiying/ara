#include <string.h>
#include "host_api.h"
#define fixed_full_main original_main
#include "../generated01/original_port.c"

/* These invoke the untouched original functions, never the Python model. */
uint8_t original_value(unsigned op, uint8_t x, uint8_t y, unsigned rm, unsigned *sat) {
    return extra_value(op,x,y,rm,sat);
}
unsigned original_selected(unsigned mode,unsigned i) { return selected(mode,i); }
void original_reset(void) {
    memset(a,0,sizeof a); memset(b,0,sizeof b); memset(out,0,sizeof out);
    memset(mask,0,sizeof mask); checks=elements=errors=0; accumulator_trial=0;
}
State original_state(void) { return (State){a,b,out,mask,checks,elements,errors}; }

/* Original statements with after-store recording only; source audit strips
 * source_note calls and matches the exact hash-bound original fragments. */
void original_seed(unsigned seed) {
    const unsigned cap=512;
        uint64_t random=UINT64_C(0x937ad68de41c725f)^seed;
        for(unsigned i=0;i<cap;++i) {
            random^=random<<13;random^=random>>7;random^=random<<17;
            a[i]=random;source_note('a',i,a[i]);b[i]=random>>19;source_note('b',i,b[i]);
            switch(i%8) {
            case 0:a[i]=0;source_note('a',i,a[i]);b[i]=0;source_note('b',i,b[i]);break;
            case 1:a[i]=(word)-1;source_note('a',i,a[i]);b[i]=1;source_note('b',i,b[i]);break;
            case 2:a[i]=(word)(UINT64_C(1)<<(SEW-1));source_note('a',i,a[i]);b[i]=(word)-1;source_note('b',i,b[i]);break;
            case 3:b[i]=SEW;source_note('b',i,b[i]);break;
            }
        }
}
void original_mask(unsigned mode) {
    const unsigned cap=512;
                for(unsigned i=0;i<128;++i){mask[i]=0;source_note('z',i,mask[i]);}
                for(unsigned i=0;i<cap;++i)
                    if(selected(mode,i)){mask[i/8]|=1u<<(i%8);source_note('m',i/8,mask[i/8]);}
}
