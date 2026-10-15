// Source-derived Sv39 adaptation, not execution of the archived Linux ELF.
#include "fixture.h"
#ifdef IX_HOST
#include <stdio.h>
int main(void) {
  for(unsigned t=0;t<96;++t) {
    struct config c=config(t);
    printf("C %u %u %u %u %u %u %u %u %u\n",t,c.unmapped,c.store,c.boundary,c.mode,c.split,c.mask,c.base,c.start);
    for(unsigned i=0;i<128;++i) printf("I %u %u %u\n",t,i,index_offset(c,i));
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
extern void ix_handler(void),ix_enter_s(uint64_t,uint64_t),ix_snapshot(volatile struct snapshot *);
extern char replay_0[],replay_1[],fault_0_pc[],fault_1_pc[],ix_ecall[];
asm(".pushsection .bss.ix_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl ix_guard_lo\nix_guard_lo:.zero 64\n"
    ".globl ix_pages\nix_pages:.zero 20480\n"
    ".globl ix_guard_hi\nix_guard_hi:.zero 64\n.popsection\n");
extern volatile uint64_t ix_pages[5][512],ix_guard_lo[8],ix_guard_hi[8];
#define ROOT ix_pages[2]
#define MID ix_pages[3]
#define LEAF ix_pages[4]
volatile struct snapshot ix_seed,ix_fault,ix_result;
volatile uint32_t ix_input[896],ix_output[898],ix_indices[128];
volatile uint8_t ix_mask[16];
volatile uint64_t ix_records[2][12],ix_post[6],ix_args[2];
volatile uint64_t ix_current,ix_phase,ix_restart,ix_satp,ix_count,ix_marker;
volatile uint64_t ix_checks,ix_errors,ix_unexpected,ix_completed,ix_cases_done;
volatile uint64_t ix_firsterror[6],ix_case_checks[4];
static uint32_t gold[2048];
static uint8_t strict_memory[2048];
static uint64_t pte(const volatile void *p,uint64_t flags) { return ((uint64_t)p>>12<<10)|flags; }
static volatile uint32_t *physical(unsigned off) {
  return (volatile uint32_t *)((volatile uint8_t *)ix_pages+off);
}
static uint64_t denied(struct config c) { return c.unmapped ? 0:pte(ix_pages[1],0xc9); }
__attribute__((noinline)) static void check(unsigned kind,unsigned index,uint64_t got,uint64_t want) {
  ++ix_checks;
  if(got==want) return;
  if(!ix_errors) {
    ix_firsterror[0]=ix_current; ix_firsterror[1]=ix_phase;
    ix_firsterror[2]=kind; ix_firsterror[3]=index;
    ix_firsterror[4]=got; ix_firsterror[5]=want;
    replay_mismatch(ix_current,(ix_phase<<32)|((uint64_t)kind<<16)|index,want,got);
  }
  ++ix_errors;
}
__attribute__((noinline)) void ix_checkpoint(void) { asm volatile("" : : : "memory"); }
static void checksnap(struct config c,unsigned phase,volatile struct snapshot *b) {
  for(unsigned i=0;i<8;++i) { check(2,320+i,b->lo[i],IX_G); check(2,328+i,b->hi[i],IX_G); }
  for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) {
    int strict; uint32_t want=vector_gold(c,phase,r,i,&strict);
    if(strict) check(2,r*32+i,b->v[r][i],want);
  }
}
static void checkmemory(struct config c,unsigned phase) {
  for(unsigned w=0;w<2048;++w) { gold[w]=original(w*4); strict_memory[w]=1; }
  for(unsigned i=0;i<8;++i) for(unsigned f=0;f<7;++f) {
    if(!active(c,i)) continue;
    unsigned w=field_offset(c,i,f)/4;
    if(phase==1) {
      if(c.store && i<c.start) gold[w]=input(f,i);
      else if(c.store && w<1024) strict_memory[w]=0;
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
  uint64_t badpte=0;
  for(unsigned w=0;w<512;++w) {
    badpte|=ROOT[w]^(w==1 ? pte(MID,1):w==2 ? UINT64_C(0x200000cf):0);
    badpte|=MID[w]^(w==0 ? pte(LEAF,1):0);
    uint64_t v=w==0 ? pte(ix_pages[0],0xc7):w==1 ?
      (phase==2 && c.start<8 ? pte(ix_pages[1],0xc7):denied(c)):0;
    badpte|=LEAF[w]^v;
  }
  check(4,0,badpte,0);
  for(unsigned i=0;i<8;++i) { check(4,i+1,ix_guard_lo[i],IX_G); check(4,i+9,ix_guard_hi[i],IX_G); }
}
int ix_trap(void) {
  struct config c=config((unsigned)ix_current);
  uint64_t e[12];
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(vl,e[5]); READ(vtype,e[6]); READ(vstart,e[7]);
  READ(fcsr,e[8]); READ(vcsr,e[9]); e[10]=ix_marker; e[11]=LEAF[1];
  uint64_t n=ix_count++;
  if(n>=2) { ++ix_unexpected; check(6,0,n,1); return 1; }
  for(unsigned i=0;i<12;++i) ix_records[n][i]=e[i];
  unsigned fault=n==0 && c.start<8;
  ix_phase=fault ? 1:2;
  uint64_t pc=(uint64_t)(fault ? (c.store ? fault_1_pc:fault_0_pc):ix_ecall);
  const uint64_t want[12]={fault ? (c.store ? 15:13):9,pc,0,0x800,ix_satp,
    fault ? 8:16,23,fault ? c.start:0,117,5,fault ? 0:1,
    !fault && c.start<8 ? pte(ix_pages[1],0xc7):denied(c)};
  for(unsigned i=0;i<12;++i) if(i!=2) check(1,i,i==3 ? e[i]&IX_TM:e[i],want[i]);
  unsigned address_ok=!fault && e[2]==0;
  if(fault) for(unsigned f=0;f<7;++f) {
    unsigned off=field_offset(c,c.start,f);
    if(off>=4096 && e[2]==IX_VA+off) address_ok=1;
  }
  check(1,2,address_ok,1);
  if(ix_errors || !fault) return 1;
  ix_restart=e[7];
  ix_snapshot(&ix_fault);
  checksnap(c,1,&ix_fault);
  checkmemory(c,1);
  ix_checkpoint();
  if(ix_errors) return 1;
  // MAPERR adaptation refills the remapped page; ACCERR preserves its contents.
  if(c.unmapped) for(unsigned w=1024;w<2048;++w) *physical(w*4)=original(w*4);
  LEAF[1]=pte(ix_pages[1],0xc7);
  asm volatile("fence rw,rw\n.global ix_repair_sfence\nix_repair_sfence:\n"
               "sfence.vma %0,zero" : : "r"(IX_VA+4096) : "memory");
  for(unsigned i=0;i<c.start;++i) if(active(c,i)) for(unsigned f=0;f<7;++f) {
    unsigned off=field_offset(c,i,f);
    *physical(off)=(c.store ? input(f,i):original(off))^0x5b;
  }
  asm volatile("fence rw,rw" : : : "memory");
  return 0;
}
static void checkbuffers(struct config c) {
  for(unsigned i=0;i<896;++i) check(5,i,ix_input[i],i<112 ? input(i/16,i%16):0x5b);
  for(unsigned i=0;i<898;++i) {
    uint32_t want=0x5b;
    if(i && i<=112) { int strict; want=vector_gold(c,2,2+(i-1)/16,(i-1)%16,&strict); }
    check(5,896+i,ix_output[i],want);
  }
  for(unsigned i=0;i<128;++i) check(5,1794+i,ix_indices[i],index_offset(c,i));
  for(unsigned i=0;i<16;++i) check(5,1922+i,ix_mask[i],c.mask);
  for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) check(5,1938+r*32+i,ix_seed.v[r][i],seed(r,i));
  for(unsigned i=0;i<8;++i) { check(5,2258+i,ix_seed.lo[i],IX_G); check(5,2266+i,ix_seed.hi[i],IX_G); }
  if(c.start==8) {
    volatile uint64_t *p=(volatile uint64_t *)&ix_fault;
    for(unsigned i=0;i<176;++i) check(5,2274+i,p[i],IX_G);
    for(unsigned i=0;i<12;++i) check(5,2450+i,ix_records[1][i],UINT64_MAX);
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
  READ(vlenb,actual); check(0,0,actual,128); check(0,1,satp,0); check(0,2,(uint64_t)ix_pages&4095,0);
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5);
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,ix_handler);
  for(unsigned p=2;p<5;++p) for(unsigned w=0;w<512;++w) ix_pages[p][w]=0;
  for(unsigned i=0;i<8;++i) ix_guard_lo[i]=ix_guard_hi[i]=IX_G;
  ROOT[1]=pte(MID,1); ROOT[2]=UINT64_C(0x200000cf); MID[0]=pte(LEAF,1);
  ix_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  const uint64_t s_status=(status&~(IX_TM|UINT64_C(0x7e602)))|0x2a00;
  for(unsigned local=0;local<4 && !ix_errors;++local) {
    ix_current=IX_GROUP*4+local; ix_phase=0;
    struct config c=config((unsigned)ix_current);
    uint64_t before=ix_checks;
    for(unsigned w=0;w<2048;++w) *physical(w*4)=original(w*4);
    volatile struct snapshot *bufs[3]={&ix_seed,&ix_fault,&ix_result};
    for(unsigned b=0;b<3;++b) {
      volatile uint64_t *p=(volatile uint64_t *)bufs[b];
      for(unsigned i=0;i<176;++i) p[i]=IX_G;
    }
    for(unsigned r=0;r<10;++r) for(unsigned i=0;i<32;++i) ix_seed.v[r][i]=seed(r,i);
    for(unsigned i=0;i<896;++i) ix_input[i]=i<112 ? input(i/16,i%16):0x5b;
    for(unsigned i=0;i<898;++i) ix_output[i]=0x5b;
    for(unsigned i=0;i<128;++i) ix_indices[i]=index_offset(c,i);
    for(unsigned i=0;i<16;++i) ix_mask[i]=c.mask;
    for(unsigned n=0;n<2;++n) for(unsigned i=0;i<12;++i) ix_records[n][i]=UINT64_MAX;
    for(unsigned i=0;i<6;++i) ix_post[i]=UINT64_MAX;
    ix_marker=ix_count=0;
    LEAF[0]=pte(ix_pages[0],0xc7); LEAF[1]=denied(c);
    ix_args[0]=IX_VA+c.base; ix_args[1]=(uint64_t)(c.store ? replay_1:replay_0);
    ix_enter_s(s_status,ix_satp);
    WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
    if(ix_errors) break;
    ix_phase=2;
    check(6,0,ix_count,c.start<8 ? 2:1); check(6,1,ix_marker,1); check(6,2,ix_unexpected,0);
    const uint64_t post[6]={0,16,23,0,117,5};
    for(unsigned i=0;i<6;++i) check(1,12+i,ix_post[i],post[i]);
    checksnap(c,2,&ix_result); checkbuffers(c); checkmemory(c,2);
    ix_checkpoint();
    ix_case_checks[local]=ix_checks-before;
    if(!ix_errors) ++ix_cases_done;
  }
  ix_phase=3;
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
  check(6,3,ix_cases_done,4);
  if(!ix_errors) ix_completed=IX_DONE;
  WRITE(mstatus,status);
  replay_text(ix_errors ? "IX_SV39_FAIL\n":"IX_SV39_PASS\n");
  return ix_errors!=0;
}
#endif
