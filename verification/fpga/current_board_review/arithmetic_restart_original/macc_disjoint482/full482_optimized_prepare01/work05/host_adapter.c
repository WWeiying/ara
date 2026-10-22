/* Independent arithmetic model and lossless per-call Host capture only. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint8_t word;
static unsigned calls, mutation, injected;
static FILE *capture;
extern int macc_main(void);
extern unsigned host_accumulator(void);
unsigned long capacity(void) { return 512; }
long replay_write(long n,long fd,long p,long size) {
    if(n!=64 || fd!=1 || size<0)abort();
    return fwrite((const void *)p,1,(size_t)size,stdout);
}
static void bytes(const void *p,size_t n) {
    if(fwrite(p,1,n,capture)!=n)abort();
}
static unsigned selected(const uint8_t *mask,unsigned i) {
    return (mask[i/8]>>(i%8))&1;
}
static unsigned long apply(unsigned op,const word *a,const word *b,word *out,
        unsigned long vl,unsigned long cap,const uint8_t *mask,unsigned long start,unsigned long rm) {
    if(op || cap!=512 || vl>cap || calls>=482 || rm || out[-1]!=91 || out[cap]!=91)abort();
    uint64_t args[]={calls,op,vl,cap,start,rm,host_accumulator()};
    bytes(args,sizeof(args));bytes(a,512);bytes(b,512);bytes(mask,128);bytes(out-1,514);
    word old[512];
    for(unsigned i=0;i<512;++i)old[i]=out[i];
    for(unsigned i=0;i<512;++i)
        if(i>=start && i<vl && selected(mask,i))
            out[i]=(word)((unsigned)old[i]+(unsigned)a[i]*(unsigned)b[i]);
    bytes(out-1,514);
    ++calls;
    if(!injected) {
        if((mutation>=1 && mutation<=4) || mutation==9) {
            for(unsigned i=0;i<512;++i) {
                unsigned active=i>=start && i<vl && selected(mask,i);
                unsigned eligible=mutation==1 ? active : mutation==2 ? start>0 && start<vl && i<start :
                    mutation==3 ? i>=start && i<vl && !selected(mask,i) :
                    mutation==4 ? start<vl && i>=vl : active && old[i]!=0;
                if(eligible) {
                    if(mutation==9)out[i]=(word)((unsigned)a[i]*(unsigned)b[i]);
                    else out[i]^=1;
                    injected=1;break;
                }
            }
        }
        if(mutation==5){out[-1]^=1;injected=1;}
        if(mutation==6){out[cap]^=1;injected=1;}
        if(mutation==7){injected=1;return 1;}
        if(mutation==8){injected=1;return UINT64_C(1)<<32;}
        if(mutation==10){out[511]^=1;injected=1;}
        if(mutation==11){out[513]^=1;injected=1;}
    }
    return 0;
}
#define OP(n) unsigned long op_##n(const word *a,const word *b,word *o,unsigned long v,unsigned long c,const uint8_t *m,unsigned long s,unsigned long r) { return apply(n,a,b,o,v,c,m,s,r); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7)
int main(int argc,char **argv) {
    if(argc!=3)return 97;
    capture=fopen(argv[1],"wbx");if(!capture)return 96;
    mutation=(unsigned)strtoul(argv[2],0,0);
    int result=macc_main();
    if(fclose(capture))return 95;
    printf("HOST_END calls=%u injected=%u result=%d\n",calls,injected,result);
    if(calls!=482 || (mutation && injected!=1))return 98;
    return result;
}
