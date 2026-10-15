// NF2-derived trap/runtime infrastructure, NF7 whole-register snapshot adapter.
// NF8 source-derived Sv39 adaptation, not execution of the archived Linux ELF.
#include "fixture.h"
#ifdef NA_HOST
#include <stdio.h>
int main(void) {
  for(unsigned t=0;t<192;++t) {
    struct config c=config(t);
    printf("C %u %u %u %u %u %u %u %u %u %u %u\n",t,c.unmapped,c.store,c.boundary,c.mode,c.gap,c.split,c.mask,c.base,c.start,c.stride);
    for(unsigned p=1;p<=2;++p) {
      for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) {
        int strict; uint32_t v=vector_gold(c,p,r,i,&strict);
        printf("V %u %u %u %u %u %u\n",t,p,r,i,strict,v);
      }
      for(unsigned i=0;i<2048;++i) {
        int strict; uint32_t v=memory_gold(c,p,i*4,&strict);
        printf("M %u %u %u %u %u\n",t,p,i,strict,v);
      }
    }
  }
  return 0;
}
#else
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern void na_handler(void),na_enter_s(uint64_t,uint64_t),na_snapshot(volatile struct snapshot *);
extern char replay_0[],replay_1[],fault_0_pc[],fault_1_pc[],na_ecall[];
asm(".pushsection .bss.na_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl na_guard_lo\nna_guard_lo:.zero 64\n"
    ".globl na_pages\nna_pages:.zero 20480\n"
    ".globl na_guard_hi\nna_guard_hi:.zero 64\n.popsection\n");
extern volatile uint64_t na_pages[5][512],na_guard_lo[8],na_guard_hi[8];
#define ROOT na_pages[2]
#define MID na_pages[3]
#define LEAF na_pages[4]
volatile struct snapshot na_seed,na_fault,na_result;
volatile uint32_t na_input[1024],na_output[1026];
volatile uint8_t na_mask[16];
volatile uint64_t na_stride;
volatile uint64_t na_records[2][12],na_post[6],na_args[2];
volatile uint64_t na_current,na_phase,na_restart,na_satp,na_count,na_marker;
volatile uint64_t na_checks,na_errors,na_unexpected,na_completed,na_cases_done;
volatile uint64_t na_firsterror[6],na_case_checks[4];
static uint32_t gold[2048];
static uint8_t strict_memory[2048];
static uint64_t pte(const volatile void *p,uint64_t flags) { return ((uint64_t)p>>12<<10)|flags; }
static volatile uint32_t *physical(unsigned off) {
  return (volatile uint32_t *)((volatile uint8_t *)na_pages+off);
}
static uint64_t denied(struct config c) { return c.unmapped ? 0:pte(na_pages[1],0xc9); }
__attribute__((noinline)) static void check(unsigned kind,unsigned index,uint64_t got,uint64_t want) {
  ++na_checks;
  if(got==want) return;
  if(!na_errors) {
    na_firsterror[0]=na_current; na_firsterror[1]=na_phase;
    na_firsterror[2]=kind; na_firsterror[3]=index;
    na_firsterror[4]=got; na_firsterror[5]=want;
    replay_mismatch(na_current,(na_phase<<32)|((uint64_t)kind<<16)|index,want,got);
  }
  ++na_errors;
}
__attribute__((noinline)) void na_checkpoint(void) { asm volatile("" : : : "memory"); }
static void checksnap(struct config c,unsigned phase,volatile struct snapshot *b) {
  for(unsigned i=0;i<8;++i) { check(2,320+i,b->lo[i],NA_G); check(2,328+i,b->hi[i],NA_G); }
  for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) {
    int strict; uint32_t want=vector_gold(c,phase,r,i,&strict);
    if(strict) check(2,r*32+i,b->v[r][i],want);
  }
}
static void checkmemory(struct config c,unsigned phase) {
  for(unsigned w=0;w<2048;++w) { gold[w]=original(w*4); strict_memory[w]=1; }
  for(unsigned i=0;i<8;++i) for(unsigned f=0;f<8;++f) {
    if(!active(c,i)) continue;
    unsigned w=field_offset(c,i,f)/4;
    if(phase==1) {
      if(c.store && i<c.start) gold[w]=input(f,i);
      else if(c.store && i==c.start && w<1024) strict_memory[w]=0;
    } else {
      if(c.store) gold[w]=input(f,i);
      if(c.start<8 && i<c.start) gold[w]^=0x5b;
    }
  }
  unsigned bad=0;
  for(unsigned w=0;w<2048;++w) if(strict_memory[w] && *physical(w*4)!=gold[w]) {
    if(!bad) check(3,w,*physical(w*4),gold[w]);
    ++bad;
  }
  check(3,2048,bad,0);
  if(phase==1 && c.store) for(unsigned f=0;f<8;++f) {
    unsigned off=field_offset(c,c.start,f);
    if(off<4096) {
      uint32_t got=*physical(off);
      check(3,2049+f,got==original(off) || got==input(f,c.start),1);
    }
  }
  uint64_t badpte=0;
  for(unsigned w=0;w<512;++w) {
    badpte|=ROOT[w]^(w==1 ? pte(MID,1):w==2 ? UINT64_C(0x200000cf):0);
    badpte|=MID[w]^(w==0 ? pte(LEAF,1):0);
    uint64_t v=w==0 ? pte(na_pages[0],0xc7):w==1 ?
      (phase==2 && c.start<8 ? pte(na_pages[1],0xc7):denied(c)):0;
    badpte|=LEAF[w]^v;
  }
  check(4,0,badpte,0);
  for(unsigned i=0;i<8;++i) { check(4,i+1,na_guard_lo[i],NA_G); check(4,i+9,na_guard_hi[i],NA_G); }
}
int na_trap(void) {
  struct config c=config((unsigned)na_current);
  uint64_t e[12];
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(vl,e[5]); READ(vtype,e[6]); READ(vstart,e[7]);
  READ(fcsr,e[8]); READ(vcsr,e[9]); e[10]=na_marker; e[11]=LEAF[1];
  uint64_t n=na_count++;
  if(n>=2) { ++na_unexpected; check(6,0,n,1); return 1; }
  for(unsigned i=0;i<12;++i) na_records[n][i]=e[i];
  unsigned fault=n==0 && c.start<8;
  na_phase=fault ? 1:2;
  uint64_t pc=(uint64_t)(fault ? (c.store ? fault_1_pc:fault_0_pc):na_ecall);
  const uint64_t want[12]={fault ? (c.store ? 15:13):9,pc,0,0x800,na_satp,
    fault ? 8:16,23,fault ? c.start:0,117,5,fault ? 0:1,
    !fault && c.start<8 ? pte(na_pages[1],0xc7):denied(c)};
  for(unsigned i=0;i<12;++i) if(i!=2) check(1,i,i==3 ? e[i]&NA_TM:e[i],want[i]);
  unsigned address_ok=!fault && e[2]==0;
  if(fault) for(unsigned f=0;f<8;++f) {
    unsigned off=field_offset(c,c.start,f);
    if(off>=4096 && e[2]==NA_VA+off) address_ok=1;
  }
  check(1,2,address_ok,1);
  if(na_errors || !fault) return 1;
  na_restart=e[7];
  na_snapshot(&na_fault);
  checksnap(c,1,&na_fault);
  checkmemory(c,1);
  na_checkpoint();
  if(na_errors) return 1;
  // MAPERR adaptation refills the remapped page; ACCERR preserves its contents.
  if(c.unmapped) for(unsigned w=1024;w<2048;++w) *physical(w*4)=original(w*4);
  LEAF[1]=pte(na_pages[1],0xc7);
  asm volatile("fence rw,rw\n.global na_repair_sfence\nna_repair_sfence:\n"
               "sfence.vma %0,zero" : : "r"(NA_VA+4096) : "memory");
  for(unsigned i=0;i<c.start;++i) if(active(c,i)) for(unsigned f=0;f<8;++f) {
    unsigned off=field_offset(c,i,f);
    *physical(off)=(c.store ? input(f,i):original(off))^0x5b;
  }
  asm volatile("fence rw,rw" : : : "memory");
  return 0;
}
static void checkbuffers(struct config c) {
  for(unsigned i=0;i<1024;++i) check(5,i,na_input[i],i<128 ? input(i/16,i%16):0);
  for(unsigned i=0;i<1026;++i) {
    uint32_t want=0x5b;
    if(i && i<=128) { int strict; want=vector_gold(c,2,2+(i-1)/16,(i-1)%16,&strict); }
    check(5,1024+i,na_output[i],want);
  }
  check(5,2050,na_stride,c.stride);
  for(unsigned i=0;i<16;++i) check(5,2051+i,na_mask[i],c.mask);
  for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) check(5,2067+r*32+i,na_seed.v[r][i],seed(r,i));
  for(unsigned i=0;i<8;++i) { check(5,2387+i,na_seed.lo[i],NA_G); check(5,2395+i,na_seed.hi[i],NA_G); }
  if(c.start==8) {
    volatile uint64_t *p=(volatile uint64_t *)&na_fault;
    for(unsigned i=0;i<176;++i) check(5,2403+i,p[i],NA_G);
    for(unsigned i=0;i<12;++i) check(5,2579+i,na_records[1][i],UINT64_MAX);
  }
}
int main(void) {
  uint64_t status,mie,mtvec,mepc,mcause,mtval,satp,medeleg,mideleg;
  uint64_t vl,vtype,vstart,vcsr,fcsr,actual;
  READ(mstatus,status); WRITE(mstatus,status&~UINT64_C(8));
  READ(mie,mie); WRITE(mie,0); READ(mtvec,mtvec); READ(mepc,mepc);
  READ(mcause,mcause); READ(mtval,mtval); READ(satp,satp);
  READ(medeleg,medeleg); READ(mideleg,mideleg);
  READ(vl,vl); READ(vtype,vtype); READ(vstart,vstart); READ(vcsr,vcsr); READ(fcsr,fcsr);
  READ(vlenb,actual); check(0,0,actual,128); check(0,1,satp,0); check(0,2,(uint64_t)na_pages&4095,0);
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5);
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,na_handler);
  for(unsigned p=2;p<5;++p) for(unsigned w=0;w<512;++w) na_pages[p][w]=0;
  for(unsigned i=0;i<8;++i) na_guard_lo[i]=na_guard_hi[i]=NA_G;
  ROOT[1]=pte(MID,1); ROOT[2]=UINT64_C(0x200000cf); MID[0]=pte(LEAF,1);
  na_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  const uint64_t s_status=(status&~(NA_TM|UINT64_C(0x7e602)))|0x2a00;
  // Reuse immutable seeds/input; every case still checks their complete contents.
  volatile uint64_t *seed_words=(volatile uint64_t *)&na_seed;
  for(unsigned i=0;i<176;++i) seed_words[i]=NA_G;
  for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) na_seed.v[r][i]=seed(r,i);
  for(unsigned i=0;i<1024;++i) na_input[i]=i<128 ? input(i/16,i%16):0;
  for(unsigned local=0;local<4 && !na_errors;++local) {
    na_current=NA_GROUP*4+local; na_phase=0;
    struct config c=config((unsigned)na_current);
    uint64_t before=na_checks;
    for(unsigned w=0;w<2048;++w) *physical(w*4)=original(w*4);
    volatile struct snapshot *bufs[2]={&na_fault,&na_result};
    for(unsigned b=0;b<2;++b) {
      volatile uint64_t *p=(volatile uint64_t *)bufs[b];
      for(unsigned i=0;i<176;++i) p[i]=NA_G;
    }
    for(unsigned i=0;i<1026;++i) na_output[i]=0x5b;
    na_stride=c.stride;
    for(unsigned i=0;i<16;++i) na_mask[i]=c.mask;
    for(unsigned n=0;n<2;++n) for(unsigned i=0;i<12;++i) na_records[n][i]=UINT64_MAX;
    for(unsigned i=0;i<6;++i) na_post[i]=UINT64_MAX;
    na_marker=na_count=0;
    LEAF[0]=pte(na_pages[0],0xc7); LEAF[1]=denied(c);
    na_args[0]=NA_VA+c.base; na_args[1]=(uint64_t)(c.store ? replay_1:replay_0);
    na_enter_s(s_status,na_satp);
    WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
    if(na_errors) break;
    na_phase=2;
    check(6,0,na_count,c.start<8 ? 2:1); check(6,1,na_marker,1); check(6,2,na_unexpected,0);
    const uint64_t post[6]={0,16,23,0,117,5};
    for(unsigned i=0;i<6;++i) check(1,12+i,na_post[i],post[i]);
    checksnap(c,2,&na_result); checkbuffers(c); checkmemory(c,2);
    na_checkpoint();
    na_case_checks[local]=na_checks-before;
    if(!na_errors) ++na_cases_done;
  }
  na_phase=3;
  WRITE(satp,satp); asm volatile("sfence.vma zero,zero" : : : "memory");
  asm volatile("vsetvl zero,%0,%1" : : "r"(vl),"r"(vtype) : "memory");
  WRITE(vstart,vstart); WRITE(vcsr,vcsr); WRITE(fcsr,fcsr);
  WRITE(mtvec,mtvec); WRITE(mepc,mepc); WRITE(mcause,mcause); WRITE(mtval,mtval);
  WRITE(medeleg,medeleg); WRITE(mideleg,mideleg); WRITE(mie,mie);
#define RESTORE(c,n) do { READ(c,actual); check(7,n,actual,c); } while(0)
  RESTORE(satp,0); RESTORE(mtvec,1); RESTORE(mepc,2); RESTORE(mcause,3); RESTORE(mtval,4);
  RESTORE(medeleg,5); RESTORE(mideleg,6); RESTORE(mie,7); RESTORE(vl,8); RESTORE(vtype,9);
  RESTORE(vstart,10); RESTORE(vcsr,11); RESTORE(fcsr,12);
  WRITE(mstatus,status&~UINT64_C(8)); READ(mstatus,actual); check(7,13,actual,status&~UINT64_C(8));
  check(6,3,na_cases_done,4);
  if(!na_errors) na_completed=NA_DONE;
  WRITE(mstatus,status);
  replay_text(na_errors ? "NA_SV39_FAIL\n":"NA_SV39_PASS\n");
  return na_errors!=0;
}
#endif
