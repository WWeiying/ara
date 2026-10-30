#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern const uint32_t exp_inputs[768],newlib_outputs[768];
static float (*volatile actual_expf)(float)=expf;

int main(void) {
    unsigned errors=0,differences=0;
    puts("EXP_REPLAY_CAP calls=768 library=linked_linux_libm performance=not_measured");
    for(unsigned i=0;i<768;++i) {
        float x,y;uint32_t result;unsigned flags;
        memcpy(&x,exp_inputs+i,sizeof(x));errno=123;
        __asm__ volatile("csrwi fcsr,0":::"memory");
        y=actual_expf(x);
        __asm__ volatile("frcsr %0":"=r"(flags)::"memory");
        const int error=errno;
        memcpy(&result,&y,sizeof(result));
        errors+=result>UINT32_C(0x3f800000) || (flags&~3u) || (error!=123 && error!=ERANGE);
        differences+=result!=newlib_outputs[i];
        printf("EXP_REPLAY i=%u input=%08x result=%08x flags=%u errno=%d\n",
               i,exp_inputs[i],result,flags,error);
    }
    printf("EXP_REPLAY_RESULT calls=768 differences=%u errors=%u\n",differences,errors);
    return errors ? 1:0;
}
