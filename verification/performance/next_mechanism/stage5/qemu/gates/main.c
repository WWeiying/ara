#include <stdint.h>
#include <stddef.h>
#include "akv_abi.h"
#include "fixture.h"

typedef struct { uint64_t armed,epc,cause,tval,count,got_epc,got_cause,got_tval,status,fatal; } trap_state;
volatile trap_state gate_traps;
_Static_assert(sizeof(trap_state)==80,"Trap assembly offsets");
#define DECLARE(n) extern uint64_t gate_##n(uint64_t,uint64_t); extern const unsigned char gate_##n##_pc[];
DECLARE(full) DECLARE(refill) DECLARE(release) DECLARE(v1full) DECLARE(v1refill)
DECLARE(row64) DECLARE(row96) DECLARE(row128) DECLARE(column) DECLARE(panel)
DECLARE(qk) DECLARE(pv) DECLARE(bad_rd) DECLARE(bad_source) DECLARE(alias)
DECLARE(bad_full) DECLARE(info)
#define NAMES(m) m(full),m(refill),m(release),m(v1full),m(v1refill),m(row64),m(row96),m(row128),m(column),m(panel),m(qk),m(pv),m(bad_rd),m(bad_source),m(alias),m(bad_full),m(info)
#define FUNCTION(n) gate_##n
#define PC(n) gate_##n##_pc
static uint64_t (*const functions[])(uint64_t,uint64_t)={NAMES(FUNCTION)};
static const unsigned char *const pcs[]={NAMES(PC)};
extern void gate_vectors(const void *,const void *);
extern void gate_capture(void *,void *,unsigned,unsigned,unsigned,unsigned);
static akv_descriptor_t descriptor;
static uint16_t queries[8][128] __attribute__((aligned(64)));
static uint16_t keys[65][128] __attribute__((aligned(64)));
static uint16_t values[65][128] __attribute__((aligned(64)));
static unsigned char actual[512] __attribute__((aligned(64)));
static unsigned char outside[3584] __attribute__((aligned(64)));

void *memset(void *p,int v,size_t n) { unsigned char *b=p;for(size_t i=0;i<n;++i)b[i]=(unsigned char)v;return p; }
void *memcpy(void *p,const void *q,size_t n) { unsigned char *b=p;const unsigned char *s=q;for(size_t i=0;i<n;++i)b[i]=s[i];return p; }
static void byte(char c) { *(volatile unsigned char *)(uintptr_t)0xc0000000=(unsigned char)c; }
static void text(const char *s) { while(*s)byte(*s++); }
static void number(uint64_t v) { char s[24];unsigned n=0;do{s[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)byte(s[--n]); }
static void hex(uint64_t v) { for(int i=15;i>=0;--i)byte("0123456789abcdef"[(v>>(i*4))&15]); }
static void dec(const char *key,uint64_t v) { byte(' ');text(key);byte('=');number(v); }
static void hx(const char *key,uint64_t v) { byte(' ');text(key);byte('=');hex(v); }
static uint64_t hash(const unsigned char *p,size_t n) { uint64_t h=UINT64_C(14695981039346656037);for(size_t i=0;i<n;++i)h=(h^p[i])*UINT64_C(1099511628211);return h; }
static uint32_t read_bits(const unsigned char *p,unsigned width) { uint32_t v=(unsigned)p[0]|(unsigned)p[1]<<8;if(width==32)v|=(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;return v; }

static void initialize(const gate_case *c)
{
    if(c->init) {
        memset(&descriptor,0,sizeof(descriptor));
        descriptor.version=1;descriptor.element_format=1;descriptor.q_rows=(uint8_t)c->rows;
        descriptor.head_dim=(uint16_t)c->d;descriptor.kv_length=(uint16_t)c->length;
        descriptor.q_row_stride_bytes=descriptor.k_token_stride_bytes=descriptor.v_token_stride_bytes=256;
        descriptor.q_base=(uintptr_t)queries;descriptor.k_base=(uintptr_t)keys;descriptor.v_base=(uintptr_t)values;
        for(unsigned h=0;h<8;++h)for(unsigned d=0;d<128;++d)
            queries[h][d]=c->init==1?(uint16_t)(0x2000+h*128+d):(h%2?0x4000:0x3c00);
        for(unsigned t=0;t<65;++t)for(unsigned d=0;d<128;++d) {
            keys[t][d]=c->init==1?(uint16_t)(0x3000+t*33+d):0x2400;
            values[t][d]=c->init==1?(uint16_t)(0x4000+t*19+d):c->init==3?0x3c00:0x3000;
        }
        if(c->init==4)queries[7][0]=0x7c01;
    }
    if(c->mutate&1)memset(queries,0xff,sizeof(queries));
    if(c->mutate&2)memset(&descriptor,0,sizeof(descriptor));
    if(c->mutate&4){keys[0][0]=0x7777;values[0][0]=0x6666;}
    if(c->mutate&8)for(unsigned d=0;d<128;++d){keys[64][d]=(uint16_t)(0x5100+d);values[64][d]=(uint16_t)(0x5200+d);}
    if(c->fault==1)descriptor.flags=1;
    if(c->fault==2)descriptor.k_base=UINT64_MAX-31;
    if(c->fault==3)descriptor.q_base=UINT64_C(0x80ffffe0);
    if(c->fault==4)descriptor.v_base=UINT64_C(0x10000000);
    if(c->fault==5) {
        descriptor.v_base=UINT64_C(0x80ffc000);
        for(unsigned t=0;t<64;++t)for(unsigned d=0;d<c->d;++d)
            *(volatile uint16_t *)(uintptr_t)(descriptor.v_base+t*256+d*2)=values[t][d];
    }
    if(c->fault==8)descriptor.head_dim=256;
}

int main(void)
{
    uint64_t errors=0;
    text("GATE_START");dec("mode",GATE_MODE);dec("cases",GATE_CASES);byte('\n');
    text("GATE_ADDRESS");hx("descriptor",(uintptr_t)&descriptor);hx("q",(uintptr_t)queries);
    hx("k",(uintptr_t)keys);hx("v",(uintptr_t)values);byte('\n');
    for(unsigned i=0;i<GATE_CASES;++i) {
        const gate_case *c=&gate_cases[i];
        initialize(c);memset(actual,0xa5,sizeof(actual));
        gate_vectors(gate_initial,gate_payloads[c->payload]);
        if(c->vill) __asm__ volatile("li t0,-1\nvsetvl zero,zero,t0":::"t0","memory");
        else __asm__ volatile("vsetivli zero,0,e8,m1,ta,ma":::"memory");
        uint64_t initial=(uint64_t)c->frm*32+8;
        __asm__ volatile("csrw fcsr,%0\ncsrwi vcsr,5\ncsrw vstart,%1"::"r"(initial),"r"((uintptr_t)c->vstart):"memory");
        gate_traps.armed=c->cause!=0;gate_traps.epc=(uintptr_t)pcs[c->op];
        gate_traps.cause=c->cause;gate_traps.tval=c->tval;
        const uint64_t previous=gate_traps.count;
        uint64_t a=c->a,b=c->b;
        if(c->op==0 || c->op==3 || c->op==15) {
            a=(uintptr_t)&descriptor;b=c->b;
            if(c->fault==6)a=UINT64_C(0x10000000);
            if(c->fault==7)++a;
        }
        uint64_t mask=((c->off&1)?UINT64_C(0x6000):0)|((c->off&2)?UINT64_C(0x600):0);
        __asm__ volatile("csrc mstatus,%0"::"r"(mask):"memory");
        uint64_t scalar=functions[c->op](a,b),status;
        __asm__ volatile("csrr %0,mstatus\nli t0,0x6600\ncsrs mstatus,t0":"=r"(status)::"t0","memory");
        uint64_t fcsr,vcsr,start,vl,vtype;
        __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart\ncsrr %3,vl\ncsrr %4,vtype"
                         :"=r"(fcsr),"=r"(vcsr),"=r"(start),"=r"(vl),"=r"(vtype)::"memory");
        gate_traps.armed=0;
        __asm__ volatile("csrwi frm,0\ncsrwi vstart,0":::"memory");
        gate_capture(actual,outside,c->width,c->op==10?c->t:c->d,c->h,c->active);
        uint64_t local=(gate_traps.count-previous!=(uint64_t)(c->cause!=0))||vcsr!=5||start!=c->vstart||
            vl!=0||vtype!=(c->vill?(UINT64_C(1)<<63):UINT64_C(0xc0));
        local+=hash(outside,sizeof(outside))!=c->outside;
        for(unsigned j=0;j<sizeof(outside);++j) {
            unsigned offset=j+512;
            unsigned char expected=offset>=1024&&offset<1792?gate_payloads[c->payload][offset-1024]:gate_initial[offset];
            local+=outside[j]!=expected;
        }
        text("GATE_CASE");dec("id",i);hx("pc",(uintptr_t)pcs[c->op]);hx("a",a);hx("b",b);
        dec("fcsr",fcsr);dec("vcsr",vcsr);dec("vstart",start);dec("vl",vl);hx("vtype",vtype);
        dec("traps",gate_traps.count-previous);dec("errors",local);byte('\n');
        if(c->cause) {
            text("GATE_TRAP");dec("id",i);hx("pc",gate_traps.got_epc);dec("cause",gate_traps.got_cause);
            hx("tval",gate_traps.got_tval);hx("mstatus",gate_traps.status);byte('\n');
        }
        if(c->op==16&&!c->cause){text("GATE_INFO");dec("id",i);dec("index",c->a);hx("value",scalar);hx("mstatus",status);byte('\n');}
        for(unsigned j=0;j<c->count;++j) {
            unsigned offset=c->active?(j/(c->count/c->h))*256+(j%(c->count/c->h))*(c->width/8):j*4;
            uint32_t bits=read_bits(actual+offset,c->width);local+=bits!=gate_golden[c->begin+j];
            text("GATE_OUT");dec("id",i);dec("index",j);hx("bits",bits);byte('\n');
        }
        text("GATE_MEMORY");dec("id",i);hx("outside",hash(outside,sizeof(outside)));dec("errors",local);byte('\n');
        errors+=local;
    }
    uint32_t ordinary[4]={1,7,23,81};
    __asm__ volatile("vsetivli zero,4,e32,m1,ta,ma\nvle32.v v4,(%0)\nvadd.vi v4,v4,7\nvse32.v v4,(%0)\nfence rw,rw"
                     ::"r"(ordinary):"v4","memory");
    for(unsigned i=0;i<4;++i)errors+=ordinary[i]!=(uint32_t[]){8,14,30,88}[i];
    text("GATE_RVV");dec("errors",errors);byte('\n');
    text("GATE_DONE");dec("mode",GATE_MODE);dec("cases",GATE_CASES);dec("traps",gate_traps.count);dec("errors",errors);byte('\n');
    return errors!=0;
}
