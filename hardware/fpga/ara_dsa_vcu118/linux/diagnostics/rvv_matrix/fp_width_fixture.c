#include <stdint.h>
#include <stdio.h>
#include "softfloat.h"
#include "input_bits.h"
#ifndef SMALL_SEW
#define SMALL_SEW 32
#endif
int main(void){
    const unsigned modes[]={0,1,2,3,4};
    printf("[");
    for(unsigned rm=0;rm<5;++rm){if(rm)printf(",");printf("[");
        for(unsigned op=0;op<3;++op){if(op)printf(",");printf("[");
            for(unsigned i=0;i<32;++i){if(i)printf(",");
                softfloat_roundingMode=op==2 ? softfloat_round_odd:modes[rm];
                softfloat_exceptionFlags=0;uint64_t bits;
#if SMALL_SEW == 16
                if(op==0){float16_t a={(uint16_t)input_bits[0][i%16]};bits=f16_to_f32(a).v;}
                else{float32_t a={(uint32_t)input_bits[1][i%16]};bits=f32_to_f16(a).v;}
#else
                if(op==0){float32_t a={(uint32_t)input_bits[0][i%16]};bits=f32_to_f64(a).v;}
                else{float64_t a={input_bits[1][i%16]};bits=f64_to_f32(a).v;}
#endif
                printf("[%llu,%u]",(unsigned long long)bits,(unsigned)softfloat_exceptionFlags);
            }
            printf("]");
        }
        printf("]");
    }
    puts("]");return 0;
}
