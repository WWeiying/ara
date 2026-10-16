/* Host-only ordered reduction reference, using Berkeley SoftFloat. */
#include <stdio.h>
#include <stdlib.h>
#include "softfloat.h"
#include "fp_reduction_inputs.h"
static uint64_t combine(unsigned width,unsigned op,uint64_t a,uint64_t b){
#define COMBINE(W) do { \
    float##W##_t x={(uint##W##_t)a},y={(uint##W##_t)b},z; \
    z=op==0 ? f##W##_add(x,y):op==1 ? f##W##_min(x,y):f##W##_max(x,y); \
    return z.v; \
} while(0)
    if(width==16){COMBINE(16);}
    if(width==32){COMBINE(32);}
    COMBINE(64);
}
int main(int argc,char **argv){
    if(argc!=3)return 2;
    unsigned width=strtoul(argv[1],0,10),cap=strtoul(argv[2],0,10);
    if((width!=16 && width!=32 && width!=64) || !cap || cap>512)return 2;
    const unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    unsigned first=1;
    printf("[");
    for(unsigned scenario=0;scenario<8;++scenario)for(unsigned l=0;l<7;++l)
    for(unsigned mode=0;mode<4;++mode)for(unsigned rm=0;rm<5;++rm)for(unsigned op=0;op<3;++op){
        softfloat_roundingMode=rm;softfloat_exceptionFlags=0;
        uint64_t result=reduction_seed(scenario);
        for(unsigned i=0;i<lengths[l];++i)if(reduction_selected(mode,i))
            result=combine(width,op,result,reduction_input(scenario,i,width));
        if(first)first=0;else printf(",");
        printf("[%llu,%u]",(unsigned long long)result,(unsigned)softfloat_exceptionFlags);
    }
    puts("]");return 0;
}
