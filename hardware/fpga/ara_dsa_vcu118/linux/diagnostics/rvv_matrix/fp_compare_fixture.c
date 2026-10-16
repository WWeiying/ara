/* Host-only comparison bits and flags from Berkeley SoftFloat. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "softfloat.h"
#include "compare_inputs.h"
#define COMPARE(W) do { \
    float##W##_t a={(uint##W##_t)raw[i]},b={(uint##W##_t)raw[j]}; \
    switch(op) { \
    case 0:result=f##W##_eq(a,b);break; \
    case 1:result=!f##W##_eq(a,b);break; \
    case 2:result=f##W##_lt(a,b);break; \
    case 3:result=f##W##_le(a,b);break; \
    case 4:result=f##W##_lt(b,a);break; \
    default:result=f##W##_le(b,a);break; \
    } \
} while(0)
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    unsigned width=strtoul(argv[1],0,10);
    if(width!=16 && width!=32 && width!=64)return 2;
    const uint64_t *raw=width==16 ? raw16:width==32 ? raw32:raw64;
    putchar('[');
    for(unsigned op=0;op<6;++op) {
        if(op)putchar(',');putchar('[');
        for(unsigned i=0;i<16;++i) {
            if(i)putchar(',');putchar('[');
            for(unsigned j=0;j<16;++j) {
                if(j)putchar(',');
                unsigned result;
                softfloat_exceptionFlags=0;
                if(width==16){COMPARE(16);}
                else if(width==32){COMPARE(32);}
                else{COMPARE(64);}
                printf("[%u,%u]",result,(unsigned)softfloat_exceptionFlags);
            }
            putchar(']');
        }
        putchar(']');
    }
    puts("]");return 0;
}
