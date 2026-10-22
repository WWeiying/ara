#include "fixture.h"
#ifdef HOST_ORACLE
#include <stdio.h>
int main(void) {
  for(unsigned p=0;p<4;++p) {
    for(unsigned r=0;r<3;++r) for(unsigned i=0;i<64;++i)
      printf("V %u %u %u %04x\n",p,r,i,vector_gold(p,r,i));
    for(unsigned h=0;h<4096;++h) printf("D %u %u %04x\n",p,h,memory_gold(p,h));
  }
  return 0;
}
#else
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern unsigned long capacity(void);
extern void mx_handler(void),mx_enter_s(uint64_t,uint64_t),mx_snapshot(volatile struct snapshot *);
extern char fault_1_pc[],mx_ecall[];
asm(".pushsection .bss.mx_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl mx_guard_lo\nmx_guard_lo:.zero 64\n.globl mx_pages\nmx_pages:.zero 20480\n"
    ".globl mx_guard_hi\nmx_guard_hi:.zero 64\n.popsection\n");
extern volatile uint64_t mx_pages[5][512],mx_guard_lo[8],mx_guard_hi[8];
#define ROOT mx_pages[2]
#define MID mx_pages[3]
#define LEAF mx_pages[4]
volatile struct snapshot mx_seed,mx_fault,mx_result;
volatile uint16_t mx_input[128],mx_offsets[128],mx_out[130];
volatile uint8_t mx_mask[16];
volatile int64_t mx_stride=-8;
volatile uint64_t mx_records[2][12],mx_post[6];
volatile uint64_t mx_count,mx_marker,mx_restart,mx_satp,mx_phase,mx_completed;
volatile uint64_t mx_checks,mx_errors,mx_unexpected,mx_return;
volatile uint64_t mx_prefix_observed;
static uint64_t pte(const volatile void *p,uint64_t flags) { return ((uint64_t)p>>12<<10)|flags; }
static volatile uint16_t *physical(unsigned off) { return (volatile uint16_t *)((volatile uint8_t *)mx_pages+off); }
__attribute__((noinline)) static void check(uint64_t got,uint64_t want) {
  ++mx_checks;
  if(got!=want) { if(!mx_errors) replay_mismatch(mx_phase,mx_checks,want,got); ++mx_errors; }
}
static void checksnap(unsigned phase,volatile struct snapshot *b) {
  for(unsigned i=0;i<8;++i) { check(b->lo[i],GUARD); check(b->hi[i],GUARD); }
  for(unsigned r=0;r<3;++r) for(unsigned i=0;i<64;++i) check(b->v[r][i],vector_gold(phase,r,i));
}
__attribute__((noinline)) void mx_checkpoint(void) { asm volatile("" : : : "memory"); }
static void check_memory(unsigned phase) {
  for(unsigned h=0;h<4096;++h) check(*physical(h*2),memory_gold(phase,h));
  uint64_t bad=0;
  for(unsigned w=0;w<512;++w) {
    bad|=ROOT[w]^(w==1 ? pte(MID,1):w==2 ? UINT64_C(0x200000cf):0);
    bad|=MID[w]^(w==0 ? pte(LEAF,1):0);
    uint64_t value=w==1 || (w==0 && phase>=2) ? pte(mx_pages[w],0xc7):0;
    bad|=LEAF[w]^value;
  }
  check(bad,0);
  for(unsigned i=0;i<8;++i) { check(mx_guard_lo[i],GUARD); check(mx_guard_hi[i],GUARD); }
  mx_phase=phase; mx_checkpoint();
}
__attribute__((noinline)) void mx_refill_page(void) {
  for(unsigned h=0;h<2048;++h) *physical(2*h)=original(h);
}
int mx_trap(void) {
  uint64_t e[12];
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(vl,e[5]); READ(vtype,e[6]); READ(vstart,e[7]);
  READ(fcsr,e[8]); READ(vcsr,e[9]); e[10]=mx_marker; e[11]=LEAF[0];
  uint64_t n=mx_count++;
  if(n>=2) { ++mx_unexpected; return 1; }
  for(unsigned i=0;i<12;++i) mx_records[n][i]=e[i];
  const uint64_t want[12]={n ? 9:15,(uint64_t)(n ? mx_ecall:fault_1_pc),
    n ? 0:VA+4078,0x800,mx_satp,n ? 64:8,8,n ? 0:5,117,5,n ? 1:0,
    n ? pte(mx_pages[0],0xc7):0};
  for(unsigned i=0;i<12;++i) check(i==3 ? e[i]&STATUS_MASK:e[i],want[i]);
  if(mx_errors) { ++mx_unexpected; return 1; }
  if(n) return 1;
  // Observe the completed store before snapshot fences or page repair.
  uint64_t prefix;
  asm volatile(".global mx_fault_prefix_read\nmx_fault_prefix_read:\n"
               "lhu %0,0(%1)" : "=r"(prefix) : "r"(physical(address(2))) : "memory");
  mx_prefix_observed=prefix; check(prefix,127);
  mx_restart=e[7];
  mx_snapshot(&mx_fault); checksnap(1,&mx_fault); check_memory(1);
  if(mx_errors) { ++mx_unexpected; return 1; }
  LEAF[0]=pte(mx_pages[0],0xc7);
  asm volatile("fence rw,rw\n.global mx_repair_sfence\nmx_repair_sfence:\n"
               "sfence.vma %0,zero" : : "r"(VA) : "memory");
  mx_refill_page();
  for(unsigned i=0;i<5;++i) if(active(i)) *physical(address(i))=mx_input[i]^0x5b;
  asm volatile("fence rw,rw" : : : "memory");
  check_memory(2);
  return 0;
}
int main(void) {
  uint64_t status,mie,mtvec,mepc,mcause,mtval,satp,medeleg,mideleg;
  uint64_t vl,vtype,vstart,vcsr,fcsr,actual;
  READ(mstatus,status); WRITE(mstatus,status&~UINT64_C(8));
  READ(mie,mie); WRITE(mie,0); READ(mtvec,mtvec); READ(mepc,mepc);
  READ(mcause,mcause); READ(mtval,mtval); READ(satp,satp);
  READ(medeleg,medeleg); READ(mideleg,mideleg);
  READ(vl,vl); READ(vtype,vtype); READ(vstart,vstart); READ(vcsr,vcsr); READ(fcsr,fcsr);
  READ(vlenb,actual); check(actual,128); check(satp,0); check((uint64_t)mx_pages&4095,0);
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5); check(capacity(),64);
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,mx_handler);
  for(unsigned p=2;p<5;++p) for(unsigned w=0;w<512;++w) mx_pages[p][w]=0;
  for(unsigned i=0;i<8;++i) mx_guard_lo[i]=mx_guard_hi[i]=GUARD;
  ROOT[1]=pte(MID,1); ROOT[2]=UINT64_C(0x200000cf); MID[0]=pte(LEAF,1);
  mx_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  volatile struct snapshot *bufs[3]={&mx_seed,&mx_fault,&mx_result};
  for(unsigned b=0;b<3;++b) {
    volatile uint64_t *p=(volatile uint64_t *)bufs[b];
    for(unsigned i=0;i<64;++i) p[i]=GUARD;
  }
  for(unsigned r=0;r<3;++r) for(unsigned i=0;i<64;++i) mx_seed.v[r][i]=vector_gold(0,r,i);
  for(unsigned i=0;i<64;++i) mx_input[i]=(uint16_t)(101+13*i);
  for(unsigned i=0;i<128;++i) {
    unsigned slot=i<3 ? (i+1)%3:i<8 ? 3+(i-3+1)%5:i;
    mx_offsets[i]=(uint16_t)(slot*2);
  }
  for(unsigned i=0;i<130;++i) mx_out[i]=0x5b;
  for(unsigned i=0;i<16;++i) mx_mask[i]=0x24;
  for(unsigned n=0;n<2;++n) for(unsigned j=0;j<12;++j) mx_records[n][j]=UINT64_MAX;
  for(unsigned j=0;j<6;++j) mx_post[j]=UINT64_MAX;
  for(unsigned h=0;h<4096;++h) *physical(2*h)=original(h);
  LEAF[0]=0; LEAF[1]=pte(mx_pages[1],0xc7);
  check_memory(0);
  const uint64_t s_status=(status&~(STATUS_MASK|UINT64_C(0x7e602)))|0x2a00;
  mx_enter_s(s_status,mx_satp);
  WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
  check(mx_unexpected,0); check(mx_count,2); check(mx_marker,1); check(mx_return,0);
  const uint64_t post[6]={64,8,0,117,5,0};
  for(unsigned i=0;i<6;++i) check(mx_post[i],post[i]);
  checksnap(3,&mx_result);
  for(unsigned i=0;i<64;++i) check(mx_out[i+1],vector_gold(3,1,i));
  check(mx_out[0],0x5b); check(mx_out[65],0x5b);
  for(unsigned i=66;i<130;++i) check(mx_out[i],0x5b);
  for(unsigned i=0;i<16;++i) check(mx_mask[i],0x24);
  check_memory(3); checksnap(0,&mx_seed);
  WRITE(satp,satp); asm volatile("sfence.vma zero,zero" : : : "memory");
  asm volatile("vsetvl zero,%0,%1" : : "r"(vl),"r"(vtype) : "memory");
  WRITE(vstart,vstart); WRITE(vcsr,vcsr); WRITE(fcsr,fcsr);
  WRITE(mtvec,mtvec); WRITE(mepc,mepc); WRITE(mcause,mcause); WRITE(mtval,mtval);
  WRITE(medeleg,medeleg); WRITE(mideleg,mideleg); WRITE(mie,mie);
#define RESTORE(c) do { READ(c,actual); check(actual,c); } while(0)
  RESTORE(satp); RESTORE(mtvec); RESTORE(mepc); RESTORE(mcause); RESTORE(mtval);
  RESTORE(medeleg); RESTORE(mideleg); RESTORE(mie); RESTORE(vl); RESTORE(vtype);
  RESTORE(vstart); RESTORE(vcsr); RESTORE(fcsr);
  WRITE(mstatus,status&~UINT64_C(8)); READ(mstatus,actual); check(actual,status&~UINT64_C(8));
  mx_completed=DONE; WRITE(mstatus,status);
  replay_text(mx_errors ? "NEGATIVE_STRIDE_STORE_SINGLE_FAIL\n":"NEGATIVE_STRIDE_STORE_SINGLE_PASS\n");
  return mx_errors!=0;
}
#endif
