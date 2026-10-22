#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *mode;
static unsigned calls;
extern int original_e16_mf4_main(void);
unsigned long capacity(void) {return 16;}
long replay_write(long n,long fd,long ptr,long len) {
    if(n!=64 || fd!=1 || len<0) exit(91);
    return (long)fwrite((void *)ptr,1,(size_t)len,stdout);
}
static void require(int ok) {if(!ok) exit(92);}
unsigned long op_0(const void *a,const void *b,void *c,unsigned long vl,
                   unsigned long cap,const void *m,unsigned long rm,unsigned long sticky) {
    const uint16_t *input=a,*seed=b;
    const uint8_t *mask=m;
    uint8_t *dst=c;
    require(++calls==1 && vl==8 && cap==16 && rm==0 && sticky==0);
    for(unsigned i=0;i<16;i++) require(input[i]==(i%2?0xfc00:0x7c00));
    for(unsigned i=0;i<64;i++) require(seed[i]==0x7c00 && mask[i]==0x24);
    for(int i=-8;i<136;i++) require(dst[i]==0x5b);
    puts("HOST_SETUP_FULL_PASS");
    dst[0]=0; dst[1]=0x7e;
    unsigned long result=16UL<<32;
    if(!strcmp(mode,"missing_nv")) result=0;
    else if(!strcmp(mode,"extra_flag")) result=17UL<<32;
    else if(!strcmp(mode,"wrong_nan")) dst[0]=1;
    else if(!strcmp(mode,"vstart")) result|=1;
    else if(!strcmp(mode,"left_guard")) dst[-8]=0;
    else if(!strcmp(mode,"right_guard")) dst[128]=0;
    else if(!strcmp(mode,"last_guard")) dst[135]=0;
    else if(!strcmp(mode,"first_tail")) dst[2]=0;
    else if(!strcmp(mode,"last_tail")) dst[127]=0;
    else if(!strcmp(mode,"wrong_type")) {dst[1]=0;dst[2]=0xc0;dst[3]=0x7f;}
    else if(!strcmp(mode,"bank0")) {dst[1]=0x7c;result=0;}
    else if(!strcmp(mode,"missing_write")) {dst[0]=0x5b;dst[1]=0x5b;}
    else require(!strcmp(mode,"positive"));
    return result;
}
unsigned long op_1(const void *a,const void *b,void *c,unsigned long d,
                   unsigned long e,const void *f,unsigned long g,unsigned long h) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;exit(93);
}
unsigned long op_2(const void *a,const void *b,void *c,unsigned long d,
                   unsigned long e,const void *f,unsigned long g,unsigned long h) {
    return op_1(a,b,c,d,e,f,g,h);
}
int main(int argc,char **argv) {
    require(argc==2); mode=argv[1];
    int rc=original_e16_mf4_main(); require(calls==1); return rc;
}
