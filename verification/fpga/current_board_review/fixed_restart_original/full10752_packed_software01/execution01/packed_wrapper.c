#include <string.h>
#include "host_api.h"
#define __builtin_memcpy host_copy
#define fixed_full_main packed_main
#include "../generated01/case.c"
#undef __builtin_memcpy

void packed_reset(void) {
    memset(a,0,sizeof a); memset(b,0,sizeof b); memset(out,0,sizeof out);
    memset(mask,0,sizeof mask); checks=elements=errors=0; accumulator_trial=0;
}
State packed_state(void) { return (State){a,b,out,mask,checks,elements,errors}; }
unsigned packed_gold_byte(unsigned call,unsigned offset) {
    unsigned row=fixed_expected_index[call];
    unsigned id=fixed_expected_rows[row][offset/64];
    return (unsigned)((fixed_expected_blocks[id][(offset%64)/8] >> (8*(offset%8))) & 255);
}
unsigned packed_gold_sat(unsigned call) { return fixed_expected_sat[call]; }
void packed_probe_init(uint8_t *p) { fixed_initialize(p); }
unsigned packed_probe_check(unsigned call,const uint8_t *p) { return fixed_mismatch(call,p); }
