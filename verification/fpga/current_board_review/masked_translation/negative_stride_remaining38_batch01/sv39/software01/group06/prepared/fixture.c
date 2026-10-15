#include "fixture.h"
#ifdef HOST_ORACLE
#include <stdio.h>
int main(void) {
  for(unsigned c=0;c<NCASES;++c) for(unsigned p=0;p<4;++p) {
    for(unsigned r=0;r<3;++r) for(unsigned i=0;i<64;++i)
      printf("V %u %u %u %u %u\n",c,p,r,i,vector_gold(&ns_cases[c],p,r,i));
    for(unsigned h=0;h<4096;++h)
      printf("D %u %u %u %u %u\n",c,p,h,memory_gold(&ns_cases[c],p,h),pending_memory(&ns_cases[c],p,h));
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
extern char fault_0_pc[],fault_1_pc[],mx_ecall[];
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
volatile int64_t mx_stride;
volatile uint64_t mx_records[2][12],mx_post[6],mx_prefix[8];
volatile uint64_t mx_case,mx_count,mx_marker,mx_restart,mx_satp,mx_phase,mx_completed;
volatile uint64_t mx_checks,mx_errors,mx_unexpected,mx_return,mx_base,mx_store,mx_cases_done;
static uint64_t pte(const volatile void *p,uint64_t f) { return ((uint64_t)p>>12<<10)|f; }
static volatile uint16_t *physical(unsigned off) { return (volatile uint16_t *)((volatile uint8_t *)mx_pages+off); }
static uint64_t protected_pte(const struct ns_case *t) { return t->unmapped ? 0:pte(mx_pages[0],0xc9); }
__attribute__((noinline)) static void check(uint64_t got,uint64_t want) {
  ++mx_checks;
  if(got!=want) { if(!mx_errors) replay_mismatch(mx_case,mx_checks,want,got); ++mx_errors; }
}
static void checksnap(unsigned phase,volatile struct snapshot *b) {
  const struct ns_case *t=&ns_cases[mx_case];
  for(unsigned i=0;i<8;++i) { check(b->lo[i],GUARD); check(b->hi[i],GUARD); }
  for(unsigned r=0;r<3;++r) for(unsigned i=0;i<64;++i) {
    uint16_t value=b->v[r][i];
    // The archived handler constrains the completed prefix, not unfinished active elements.
    if(phase==1 && t->faults && !t->store && r==1 && i<8 && i>=(unsigned)t->start && active(t,i)) continue;
    check(value,vector_gold(t,phase,r,i));
  }
}
__attribute__((noinline)) void mx_checkpoint(void) { asm volatile("" : : : "memory"); }
static void check_memory(unsigned phase) {
  const struct ns_case *t=&ns_cases[mx_case];
  for(unsigned h=0;h<4096;++h) {
    uint16_t value=*physical(h*2);
    if(!pending_memory(t,phase,h)) check(value,memory_gold(t,phase,h));
  }
  uint64_t bad=0;
  for(unsigned w=0;w<512;++w) {
    bad|=ROOT[w]^(w==1 ? pte(MID,1):w==2 ? UINT64_C(0x200000cf):0);
    bad|=MID[w]^(w==0 ? pte(LEAF,1):0);
    uint64_t value=w==1 ? pte(mx_pages[1],0xc7):w==0 ? (phase>=2 ? pte(mx_pages[0],0xc7):protected_pte(t)):0;
    bad|=LEAF[w]^value;
  }
  check(bad,0);
  for(unsigned i=0;i<8;++i) { check(mx_guard_lo[i],GUARD); check(mx_guard_hi[i],GUARD); }
  mx_phase=phase; mx_checkpoint();
}
__attribute__((noinline)) void mx_refill_page(void) {
  for(unsigned h=0;h<2048;++h) *physical(2*h)=original(h);
}
__attribute__((noinline)) void mx_repair(void) {
  const struct ns_case *t=&ns_cases[mx_case];
  LEAF[0]=pte(mx_pages[0],0xc7);
  asm volatile("fence rw,rw\n.global mx_repair_sfence\nmx_repair_sfence:\n"
               "sfence.vma %0,zero" : : "r"(VA) : "memory");
  if(t->unmapped) mx_refill_page();
  if(t->faults) for(unsigned i=0;i<(unsigned)t->start;++i) if(active(t,i))
    *physical(address(t,i))=(t->store ? mx_input[i]:original(address(t,i)/2))^0x5b;
  asm volatile("fence rw,rw" : : : "memory");
  check_memory(2);
}
int mx_trap(void) {
  const struct ns_case *t=&ns_cases[mx_case];
  uint64_t e[12];
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(vl,e[5]); READ(vtype,e[6]); READ(vstart,e[7]);
  READ(fcsr,e[8]); READ(vcsr,e[9]); e[10]=mx_marker; e[11]=LEAF[0];
  uint64_t n=mx_count++;
  if(n>=(unsigned)(1+t->faults)) { ++mx_unexpected; return 1; }
  for(unsigned i=0;i<12;++i) mx_records[n][i]=e[i];
  unsigned done=n==(unsigned)t->faults;
  const uint64_t want[12]={done ? 9:(t->store ? 15:13),
    (uint64_t)(done ? mx_ecall:t->store ? fault_1_pc:fault_0_pc),
    done ? 0:VA+address(t,t->start),0x800,mx_satp,done ? 64:8,8,
    done ? 0:(unsigned)t->start,117,5,done ? 1:0,
    done && t->faults ? pte(mx_pages[0],0xc7):protected_pte(t)};
  for(unsigned i=0;i<12;++i) check(i==3 ? e[i]&STATUS_MASK:e[i],want[i]);
  if(mx_errors) { ++mx_unexpected; return 1; }
  if(done) return 1;
  // Completed stores must be observable before the snapshot's fence/page repair.
  if(t->store) for(unsigned i=0;i<(unsigned)t->start;++i) if(active(t,i)) {
    mx_prefix[i]=*physical(address(t,i)); check(mx_prefix[i],mx_input[i]);
  }
  mx_restart=e[7];
  mx_snapshot(&mx_fault); checksnap(1,&mx_fault); check_memory(1);
  if(mx_errors) { ++mx_unexpected; return 1; }
  mx_repair();
  return mx_errors!=0;
}
static void one_case(uint64_t s_status) {
  const struct ns_case *t=&ns_cases[mx_case];
  mx_count=mx_marker=mx_restart=mx_return=0;
  mx_base=VA+t->base; mx_stride=t->stride; mx_store=t->store;
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5); check(capacity(),64);
  for(unsigned p=2;p<5;++p) for(unsigned w=0;w<512;++w) mx_pages[p][w]=0;
  for(unsigned i=0;i<8;++i) mx_guard_lo[i]=mx_guard_hi[i]=GUARD;
  ROOT[1]=pte(MID,1); ROOT[2]=UINT64_C(0x200000cf); MID[0]=pte(LEAF,1);
  mx_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  volatile struct snapshot *bufs[3]={&mx_seed,&mx_fault,&mx_result};
  for(unsigned b=0;b<3;++b) {
    volatile uint64_t *p=(volatile uint64_t *)bufs[b];
    for(unsigned i=0;i<64;++i) p[i]=GUARD;
  }
  for(unsigned r=0;r<3;++r) for(unsigned i=0;i<64;++i) mx_seed.v[r][i]=vector_gold(t,0,r,i);
  for(unsigned i=0;i<128;++i) {
    mx_input[i]=i<64 ? (uint16_t)(101+13*i):0;
    unsigned b=t->boundary;
    unsigned slot=i<b ? (i+1)%b:i<8 ? b+(i-b+1)%(8-b):i;
    mx_offsets[i]=(uint16_t)(slot*2);
  }
  for(unsigned i=0;i<130;++i) mx_out[i]=0x5b;
  for(unsigned i=0;i<16;++i) mx_mask[i]=t->mask;
  for(unsigned n=0;n<2;++n) for(unsigned j=0;j<12;++j) mx_records[n][j]=UINT64_MAX;
  for(unsigned j=0;j<6;++j) mx_post[j]=UINT64_MAX;
  for(unsigned j=0;j<8;++j) mx_prefix[j]=UINT64_MAX;
  for(unsigned h=0;h<4096;++h) *physical(2*h)=original(h);
  LEAF[0]=protected_pte(t); LEAF[1]=pte(mx_pages[1],0xc7);
  check_memory(0);
  mx_enter_s(s_status,mx_satp);
  WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
  check(mx_unexpected,0); check(mx_count,1+t->faults); check(mx_marker,1); check(mx_return,0);
  const uint64_t post[6]={64,8,0,117,5,0};
  for(unsigned i=0;i<6;++i) check(mx_post[i],post[i]);
  checksnap(3,&mx_result);
  for(unsigned i=0;i<64;++i) check(mx_out[i+1],vector_gold(t,3,1,i));
  check(mx_out[0],0x5b); check(mx_out[65],0x5b);
  for(unsigned i=66;i<130;++i) check(mx_out[i],0x5b);
  for(unsigned i=0;i<16;++i) check(mx_mask[i],t->mask);
  if(!t->faults) { check_memory(1); mx_repair(); }
  check_memory(3); checksnap(0,&mx_seed);
  ++mx_cases_done;
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
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,mx_handler);
  const uint64_t s_status=(status&~(STATUS_MASK|UINT64_C(0x7e602)))|0x2a00;
  for(mx_case=0;mx_case<NCASES && !mx_errors;++mx_case) one_case(s_status);
  check(mx_cases_done,NCASES);
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
  replay_text(mx_errors ? "NEGATIVE_STRIDE_BATCH_FAIL\n":"NEGATIVE_STRIDE_BATCH_PASS\n");
  return mx_errors!=0;
}
#endif
