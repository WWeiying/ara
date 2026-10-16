#include <stdint.h>
#include "operations.h"
#if SEW == 8
typedef uint8_t word;typedef uint16_t wide;
#elif SEW == 16
typedef uint16_t word;typedef uint32_t wide;
#else
typedef uint32_t word;typedef uint64_t wide;
#endif
static word a[1024],b[1024];
static wide wa[1024],out[1026];
static uint8_t mask[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,long,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static __int128 sign(uint64_t x,unsigned width){uint64_t s=UINT64_C(1)<<(width-1);return (int64_t)((x^s)-s);}
static __int128 round_value(__int128 x,unsigned shift,unsigned rm){
    if(!shift)return x;
    unsigned __int128 bits=x,low=((unsigned __int128)1<<shift)-1;
    unsigned half=(bits>>(shift-1))&1,odd=(bits>>shift)&1;
    unsigned inc=rm==0 ? half:rm==1 ? half && ((bits&(low>>1)) || odd):rm==2 ? 0:!odd && (bits&low);
    return (x>>shift)+inc;
}
static wide expected(unsigned op,unsigned i,unsigned rm,unsigned *sat){
    __int128 sx=sign(a[i],SEW),sy=sign(b[i],SEW),z;
    switch(op){
    case 0:return (wide)a[i]+b[i];case 1:return sx+sy;
    case 2:return (wide)a[i]-b[i];case 3:return sx-sy;
    case 4:return (wide)a[i]*b[i];case 5:return sx*sy;
    case 6:return sx*b[i];case 7:return a[i];case 8:return sx;
    case 9:return wa[i]>>(b[i]&(2*SEW-1));
    case 10:return sign(wa[i],2*SEW)>>(b[i]&(2*SEW-1));
    default:z=round_value(op==11 ? (__int128)(uint64_t)wa[i]:sign(wa[i],2*SEW),b[i]&(2*SEW-1),rm);
    }
    __int128 lo=op==11 ? 0:-((__int128)1<<(SEW-1));
    __int128 hi=op==11 ? (word)-1:-lo-1;
    if(z<lo){*sat=1;return lo;}if(z>hi){*sat=1;return hi;}return z;
}
void probe_main(void){
    unsigned cap=capacity(),errors=0,cases=0;
    if(!cap || cap>1024){text("RVV_WIDTH_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed){
        uint64_t rng=UINT64_C(0x35ab712975ccd817)^seed;
        for(unsigned i=0;i<cap;++i){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;a[i]=rng;b[i]=rng>>19;wa[i]=rng;
            if(i%8==0){a[i]=(word)-1;b[i]=(word)-1;wa[i]=(wide)-1;}
            if(i%8==1){a[i]=(word)(1UL<<(SEW-1));b[i]=1;wa[i]=(wide)(UINT64_C(1)<<(2*SEW-1));}}
        for(unsigned op=0;op<13;++op)for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)for(unsigned rm=0;rm<4;++rm){
            unsigned vl=lengths[l],sat=0;
            for(unsigned i=0;i<128;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
            for(unsigned i=0;i<1026;++i)out[i]=(wide)UINT64_C(0x5b5b5b5b5b5b5b5b);
            unsigned long result=functions[op](op<9 ? (void *)a:(void *)wa,b,out+1,vl,cap,mask,0,rm);
            if((uint32_t)result)++errors;
            for(unsigned i=0;i<cap;++i){unsigned active=i<vl && ((mask[i/8]>>(i%8))&1);
                wide wanted=active ? expected(op,i,rm,&sat):(wide)UINT64_C(0x5b5b5b5b5b5b5b5b);
                if(op<9 ? out[i+1]!=wanted:((word *)(out+1))[i]!=(word)wanted)++errors;}
            if((result>>32)!=sat)++errors;
            if(out[0]!=(wide)UINT64_C(0x5b5b5b5b5b5b5b5b) || out[1025]!=(wide)UINT64_C(0x5b5b5b5b5b5b5b5b))++errors;
            ++cases;
        }
    }
    text(errors ? "RVV_WIDTH_FAIL sew=":"RVV_WIDTH_PASS sew=");num(SEW);text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
