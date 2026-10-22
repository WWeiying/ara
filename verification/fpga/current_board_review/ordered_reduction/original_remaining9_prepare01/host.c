#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if SEW == 16
typedef uint16_t word;
#define INF 0x7c00u
#define NAN_BITS 0x7e00u
#else
typedef uint32_t word;
#define INF 0x7f800000u
#define NAN_BITS 0x7fc00000u
#endif
extern int CASE_MAIN(void);
static unsigned calls;
static const char *mode;
static void require(int ok) { if (!ok) exit(92); }
unsigned long capacity(void) { return CAP1024; }
long replay_write(long n,long fd,long p,long len) {
    require(n==64 && fd==1 && len>=0);
    return (long)fwrite((void *)p,1,(size_t)len,stdout);
}
unsigned long op_0(const void *a,const void *b,void *c,unsigned long vl,
                   unsigned long cap,const void *m,unsigned long rm,unsigned long sticky) {
    const word *input=a,*seed=b;
    const uint8_t *mask=m;
    uint8_t *dst=c;
    require(++calls==1 && vl==CAP1024/2 && cap==CAP1024 && !rm && !sticky);
    for(unsigned i=0;i<CAP1024;i++) require(input[i]==(INF|(i%2 ? (1u<<(SEW-1)):0)));
    for(unsigned i=0;i<64;i++) require(seed[i]==INF && mask[i]==0x24);
    for(int i=-8;i<136;i++) require(dst[i]==0x5b);
    puts("HOST_SETUP_FULL_PASS");
    word result=NAN_BITS;
    memcpy(dst,&result,sizeof(result));
    unsigned long status=16UL<<32;
    if(!strcmp(mode,"missing_nv")) status=0;
    else if(!strcmp(mode,"extra_flag")) status=17UL<<32;
    else if(!strcmp(mode,"wrong_nan")) dst[0]=1;
    else if(!strcmp(mode,"vstart")) status|=1;
    else if(!strcmp(mode,"left_guard")) dst[-8]=0;
    else if(!strcmp(mode,"right_guard")) dst[128]=0;
    else if(!strcmp(mode,"last_guard")) dst[135]=0;
    else if(!strcmp(mode,"first_tail")) dst[sizeof(word)]=0;
    else if(!strcmp(mode,"last_tail")) dst[127]=0;
    else if(!strcmp(mode,"wrong_type")) {dst[1]=0x7e;dst[2]=0x5b;dst[3]=0x5b; if(SEW==16)dst[1]=0;}
    else if(!strcmp(mode,"bank0")) status=0; /* Wrong bank/flags despite equal NaN in larger shapes. */
    else if(!strcmp(mode,"missing_write")) memset(dst,0x5b,sizeof(word));
    else require(!strcmp(mode,"positive"));
    return status;
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
    require(argc==2);mode=argv[1];int rc=CASE_MAIN();require(calls==1);return rc;
}
