#include <stdint.h>
#include "rom.h"
#define FILL UINT64_C(0x5b5b5b5b5b5b5b5b)
#define MASK64 UINT64_MAX
volatile uint64_t mx_input[1024] __attribute__((aligned(64)));
volatile uint64_t mx_memory[1024] __attribute__((aligned(64)));
volatile uint64_t mx_output[1024] __attribute__((aligned(64)));
volatile uint64_t mx_expected[1024] __attribute__((aligned(64)));
volatile uint64_t mx_mask[16] __attribute__((aligned(64)));
struct scene { uint64_t phase,bad_index,expected,actual; };
volatile struct scene mx_scene;
volatile uint64_t mx_case,mx_return,mx_errors,mx_supported,mx_unsupported,mx_noactive;
volatile uint64_t mx_words_checked,mx_done,mx_fatal,mx_source_exit;
volatile uint64_t mx_args[9],mx_records[144][10],mx_post[144][4];
volatile uint64_t mx_current_target,mx_outcome,mx_satp;

__attribute__((noinline)) void mx_reset(unsigned c) {
    const struct config *p=&configs[c];
    const uint64_t *gold=rom_expected[p->oracle];
    mx_case=c;
    for(unsigned i=0;i<1024;++i) {
        mx_input[i]=rom_input[i];
        mx_memory[i]=(p->op&1)?FILL:rom_memory[i];
        mx_output[i]=FILL;
        mx_expected[i]=gold[i];
    }
    for(unsigned i=0;i<16;++i) mx_mask[i]=p->off?0:MASK64;
    mx_scene.phase=mx_scene.bad_index=mx_scene.expected=mx_scene.actual=0;
    mx_return=MASK64;mx_outcome=0;
    for(unsigned i=0;i<10;++i) mx_records[c][i]=MASK64;
    for(unsigned i=0;i<4;++i) mx_post[c][i]=MASK64;
}

/* Equal words still read every original byte; only mismatch decoding is bytewise. */
__attribute__((noinline)) uint64_t mx_compare(void) {
    const volatile uint64_t *actual=(configs[mx_case].op&1)?mx_memory:mx_output;
    uint64_t bad=mx_return!=0;
    for(unsigned i=0;i<1024;++i) {
        uint64_t a=actual[i],e=mx_expected[i];
        ++mx_words_checked;
        if(a!=e) for(unsigned b=0;b<8;++b) {
            unsigned av=(a>>(8*b))&255,ev=(e>>(8*b))&255;
            if(av!=ev) {
                if(!bad) { mx_scene.bad_index=8*i+b;mx_scene.expected=ev;mx_scene.actual=av; }
                ++bad;
            }
        }
    }
    return bad;
}

int mx_allowed(uint64_t cause,uint64_t pc,uint64_t phase) {
    const struct config *p=&configs[mx_case];
    return cause==((p->op&1)?6u:4u) && pc==mx_current_target &&
        p->offset && p->vl && !p->off && phase==1;
}

#ifndef HOST_ORACLE
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
extern uint64_t capacity(void);
extern void mx_handler(void),mx_enter_s(uint64_t,uint64_t),mx_ecall(void);
extern void replay_text(const char *);
typedef uint64_t (*operation)(const void *,void *,const void *,uint64_t,uint64_t,void *,int64_t,void *);
#include "operations.h"
static operation functions[]={FUNCTIONS};
extern const uint64_t mx_targets[];
volatile uint64_t mx_root[512] __attribute__((aligned(4096)));

__attribute__((noinline)) void mx_checkpoint(void) { asm volatile("" : : : "memory"); }
int mx_trap(void) {
    uint64_t r[10];
    READ(vstart,r[0]);READ(vtype,r[1]);READ(vl,r[2]);
    READ(mcause,r[3]);READ(mepc,r[4]);READ(mtval,r[5]);
    READ(mstatus,r[6]);READ(satp,r[7]);r[8]=mx_scene.phase;r[9]=mx_return;
    for(unsigned i=0;i<10;++i) mx_records[mx_case][i]=r[i];
    if(mx_outcome || (r[6]&0x1800)!=0x800 || r[7]!=mx_satp) mx_fatal=1;
    const struct config *p=&configs[mx_case];
    if(!mx_fatal && r[3]==9 && r[4]==(uint64_t)mx_ecall && r[8]==2 && r[9]==0 &&
       r[0]==0 && r[1]==9 && r[2]==((p->op&1)?p->vl:128)) mx_outcome=1;
    else if(!mx_fatal && mx_allowed(r[3],r[4],r[8])) mx_outcome=2;
    else { mx_fatal=1;mx_outcome=3; }
    return 1;
}

int main(void) {
    uint64_t status,mie,mtvec,satp,medeleg,mideleg,vl,vtype,vstart,vcsr,fcsr,vlenb;
    READ(mstatus,status);WRITE(mstatus,status&~UINT64_C(8));
    READ(mie,mie);WRITE(mie,0);READ(mtvec,mtvec);READ(satp,satp);
    READ(medeleg,medeleg);READ(mideleg,mideleg);READ(vl,vl);READ(vtype,vtype);
    READ(vstart,vstart);READ(vcsr,vcsr);READ(fcsr,fcsr);READ(vlenb,vlenb);
    if(vlenb!=128 || satp || capacity()!=128) return 2;
    for(unsigned i=0;i<512;++i) mx_root[i]=0;
    mx_root[2]=UINT64_C(0x200000cf);
    mx_satp=(UINT64_C(8)<<60)|((uint64_t)mx_root>>12);
    WRITE(medeleg,0);WRITE(mideleg,0);WRITE(mtvec,mx_handler);
    const uint64_t s_status=(status&~UINT64_C(0x8000031888))|UINT64_C(0x2a00);
    for(unsigned c=0;c<144;++c) {
        const struct config *p=&configs[c];
        mx_reset(c);
        mx_args[0]=(uint64_t)mx_input+64;mx_args[1]=(uint64_t)mx_output+64;
        mx_args[2]=(uint64_t)mx_mask;mx_args[3]=p->vl;mx_args[4]=128;
        mx_args[5]=(uint64_t)mx_memory+p->base;mx_args[6]=(uint64_t)p->stride;
        mx_args[7]=(uint64_t)&mx_scene;mx_args[8]=(uint64_t)functions[p->op];
        mx_current_target=mx_targets[p->op];
        mx_checkpoint();
        mx_enter_s(s_status,mx_satp);
        WRITE(satp,0);asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
        if(mx_fatal || (mx_outcome!=1 && mx_outcome!=2)) { ++mx_errors;break; }
        if(mx_outcome==2) {
            ++mx_unsupported;
            /* Terminated-child branch: no numerical checks or invented return. */
            WRITE(vstart,0);
        } else {
            uint64_t bad=mx_compare();
            if(bad) { ++mx_errors;break; }
            ++mx_supported;
            if(!p->vl || p->off) ++mx_noactive;
        }
        mx_checkpoint();
    }
    if(mx_supported+mx_unsupported!=144 || mx_noactive!=96) ++mx_errors;
    mx_source_exit=mx_errors?1:mx_unsupported?77:0;
    WRITE(satp,satp);asm volatile("sfence.vma zero,zero" : : : "memory");
    asm volatile("vsetvl zero,%0,%1" : : "r"(vl),"r"(vtype) : "memory");
    WRITE(vstart,vstart);WRITE(vcsr,vcsr);WRITE(fcsr,fcsr);
    WRITE(mtvec,mtvec);WRITE(medeleg,medeleg);WRITE(mideleg,mideleg);WRITE(mie,mie);
    mx_done=UINT64_C(0x7365673134340001);WRITE(mstatus,status);
    replay_text(mx_errors?"SEGMENT144_FAIL\n":mx_unsupported?"SEGMENT144_CAPABILITY_COMPLETE\n":"SEGMENT144_NUMERICAL_PASS\n");
    return (int)mx_source_exit;
}
#endif
