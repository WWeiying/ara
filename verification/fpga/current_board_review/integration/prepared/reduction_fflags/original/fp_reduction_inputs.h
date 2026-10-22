#include <stdint.h>
#include "input_bits.h"
static uint64_t reduction_seed(unsigned scenario){
    const unsigned seeds[]={1,14,2,12,2,8,1,12};
    return input_bits[seeds[scenario]];
}
static uint64_t reduction_input(unsigned scenario,unsigned i,unsigned width){
    uint64_t sign=UINT64_C(1)<<(width-1);
    switch(scenario){
    case 0:return input_bits[i%2];
    case 1:return input_bits[14];
    case 2:return input_bits[i%2 ? 2:15];
    case 3:return input_bits[i%2 ? 13:12];
    case 4:{const unsigned indices[]={2,7,3,7,11,11};
        return input_bits[indices[i%6]]^((i%6==3 || i%6==5) ? sign:0);}
    case 5:{const unsigned indices[]={8,9,10,8,9,10};
        return input_bits[indices[i%6]]^(i%6>=3 ? sign:0);}
    case 6:return input_bits[i%2 ? 15:2];
    default:return input_bits[i%2 ? 7:2];
    }
}
static inline unsigned reduction_selected(unsigned mode,unsigned i){
    const unsigned masks[]={255,0,0x55,0x24};
    return (masks[mode]>>(i%8))&1;
}
