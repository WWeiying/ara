// Four original-source NF2 trial derivatives, not Linux signal-frame replay.
#include "fixture.h"
#ifdef MX_HOST
#include <stdio.h>
int main(void) {
  for(unsigned c=0;c<MX_N;++c) for(unsigned p=1;p<=2;++p) {
    for(unsigned r=0;r<4;++r) for(unsigned i=0;i<64;++i)
      printf("V %u %u %u %u %u %04x\n",c,p,r,i,partial_vector(c,p,r,i),vector_gold(c,p,r,i));
    for(unsigned h=0;h<4096;++h)
      printf("D %u %u %u %u %04x\n",c,p,h,partial_memory(c,p,h),memory_gold(c,p,h));
  }
  return 0;
}
#else
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern void mx_handler(void),mx_enter_s(uint64_t,uint64_t),mx_snapshot(volatile struct snapshot *);
extern char mx_segment_load[],mx_segment_store[],mx_ecall[];
static const void *const sites[]={mx_segment_load,mx_segment_store};
asm(".pushsection .bss.mx_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl mx_guard_lo\nmx_guard_lo:.zero 64\n"
    ".globl mx_pages\nmx_pages:.zero 20480\n"
    ".globl mx_guard_hi\nmx_guard_hi:.zero 64\n.popsection\n");
extern volatile uint64_t mx_pages[5][512],mx_guard_lo[8],mx_guard_hi[8];
#define ROOT mx_pages[2]
#define MID mx_pages[3]
#define LEAF mx_pages[4]
volatile struct snapshot mx_seed[MX_N],mx_fault[MX_N],mx_result[MX_N];
volatile uint16_t mx_out[MX_N][130];
volatile uint8_t mx_mask[MX_N][16];
volatile uint64_t mx_records[MX_N][2][12],mx_post[MX_N][5];
volatile uint64_t mx_count[MX_N],mx_marker[MX_N],mx_case_checks[MX_N];
volatile uint64_t mx_current,mx_restart,mx_args[2],mx_satp,mx_phase,mx_completed;
volatile uint64_t mx_checks,mx_errors,mx_unexpected;
static uint64_t pte(const volatile void *p,uint64_t flags) { return ((uint64_t)p>>12<<10)|flags; }
static volatile uint16_t *physical(unsigned off) { return (volatile uint16_t *)((volatile uint8_t *)mx_pages+off); }
static void check(uint64_t got,uint64_t want) {
  ++mx_checks;
  if(got!=want) {
    if(!mx_errors) replay_mismatch(mx_current,mx_checks,want,got);
    ++mx_errors;
  }
}
static void checksnap(unsigned c,unsigned phase,volatile struct snapshot *b) {
  for(unsigned i=0;i<8;++i) { check(b->lo[i],MX_G); check(b->hi[i],MX_G); }
  for(unsigned r=0;r<4;++r) for(unsigned i=0;i<64;++i)
    if(!partial_vector(c,phase,r,i)) check(b->v[r][i],vector_gold(c,phase,r,i));
}
__attribute__((noinline)) void mx_checkpoint(void) { asm volatile("" : : : "memory"); }
static void check_memory(unsigned c,unsigned phase) {
  uint64_t bad=0;
  for(unsigned h=0;h<4096;++h) {
    uint16_t got=*physical(h*2),want=memory_gold(c,phase,h);
    if(partial_memory(c,phase,h) && got==seed(c,1,5)) continue;
    bad|=got^want;
  }
  check(bad,0);
  bad=0;
  for(unsigned w=0;w<512;++w) {
    bad|=ROOT[w]^(w==1 ? pte(MID,1):w==2 ? UINT64_C(0x200000cf):0);
    bad|=MID[w]^(w==0 ? pte(LEAF,1):0);
    uint64_t value=w==0 || (w==1 && phase==2) ? pte(mx_pages[w],0xc7):0;
    bad|=LEAF[w]^value;
  }
  check(bad,0);
  for(unsigned i=0;i<8;++i) { check(mx_guard_lo[i],MX_G); check(mx_guard_hi[i],MX_G); }
  mx_phase=phase;
  mx_checkpoint();
}
int mx_trap(void) {
  unsigned c=(unsigned)mx_current;
  uint64_t e[12];
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(vl,e[5]); READ(vtype,e[6]); READ(vstart,e[7]);
  READ(fcsr,e[8]); READ(vcsr,e[9]); e[10]=mx_marker[c]; e[11]=LEAF[1];
  uint64_t n=mx_count[c]++;
  if(n>=2) { ++mx_unexpected; return 1; }
  for(unsigned i=0;i<12;++i) mx_records[c][n][i]=e[i];
  unsigned fault=n==0;
  const uint64_t want[12]={fault ? (configs[c].store ? 15:13):9,
    (uint64_t)(fault ? sites[configs[c].store]:mx_ecall),
    fault ? MX_VA+offset(c,5,configs[c].fault_field):0,
    0x800,mx_satp,8,8,fault ? 5:0,117,5,fault ? 0:1,
    fault ? 0:pte(mx_pages[1],0xc7)};
  for(unsigned i=0;i<12;++i) {
    // The original segment oracle permits either protected field address.
    if(fault && i==2 && c<2 && e[i]==MX_VA+offset(c,5,1)) continue;
    check(i==3 ? e[i]&MX_TRAP_MASK:e[i],want[i]);
  }
  if(mx_errors) { ++mx_unexpected; return 1; }
  if(!fault) return 1;
  mx_restart=e[7];
  mx_snapshot(&mx_fault[c]);
  checksnap(c,1,&mx_fault[c]);
  check_memory(c,1);
  if(mx_errors) { ++mx_unexpected; return 1; }
  LEAF[1]=pte(mx_pages[1],0xc7);
  asm volatile("fence rw,rw\n.global mx_repair_sfence\nmx_repair_sfence:\n"
               "sfence.vma %0,zero" : : "r"(MX_VA+4096) : "memory");
  for(unsigned i=0;i<5;++i) if(active(i)) for(unsigned f=0;f<2;++f) {
    unsigned off=offset(c,i,f);
    *physical(off)=(configs[c].store ? seed(c,f+1,i):original(off/2))^0x5b;
  }
  asm volatile("fence rw,rw" : : : "memory");
  return 0;
}
static void check_case(unsigned c) {
  check(mx_unexpected,0); check(mx_count[c],2); check(mx_marker[c],1);
  const uint64_t post[5]={8,8,0,117,5};
  for(unsigned i=0;i<5;++i) check(mx_post[c][i],post[i]);
  checksnap(c,2,&mx_result[c]);
  for(unsigned i=0;i<130;++i)
    check(mx_out[c][i],i && i<=128 ? vector_gold(c,2,1+(i-1)/64,(i-1)%64):0x5b);
  for(unsigned i=0;i<16;++i) check(mx_mask[c][i],0x24);
  check_memory(c,2);
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
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5);
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,mx_handler);
  for(unsigned p=2;p<5;++p) for(unsigned w=0;w<512;++w) mx_pages[p][w]=0;
  for(unsigned i=0;i<8;++i) mx_guard_lo[i]=mx_guard_hi[i]=MX_G;
  ROOT[1]=pte(MID,1); ROOT[2]=UINT64_C(0x200000cf); MID[0]=pte(LEAF,1);
  mx_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  for(unsigned c=0;c<MX_N;++c) {
    volatile struct snapshot *bufs[3]={&mx_seed[c],&mx_fault[c],&mx_result[c]};
    for(unsigned b=0;b<3;++b) {
      volatile uint64_t *p=(volatile uint64_t *)bufs[b];
      for(unsigned i=0;i<80;++i) p[i]=MX_G;
    }
    for(unsigned r=0;r<4;++r) for(unsigned i=0;i<64;++i) mx_seed[c].v[r][i]=seed(c,r,i);
    for(unsigned i=0;i<130;++i) mx_out[c][i]=0x5b;
    for(unsigned i=0;i<16;++i) mx_mask[c][i]=0x24;
    for(unsigned n=0;n<2;++n) for(unsigned j=0;j<12;++j) mx_records[c][n][j]=UINT64_MAX;
    for(unsigned j=0;j<5;++j) mx_post[c][j]=UINT64_MAX;
  }
  const uint64_t s_status=(status&~(MX_TRAP_MASK|UINT64_C(0x7e602)))|0x2a00;
  for(unsigned c=0;c<MX_N && !mx_errors;++c) {
    mx_current=c;
    uint64_t before=mx_checks;
    for(unsigned h=0;h<4096;++h) *physical(h*2)=original(h);
    LEAF[0]=pte(mx_pages[0],0xc7); LEAF[1]=0;
    mx_args[0]=MX_VA+configs[c].base; mx_args[1]=(uint64_t)sites[configs[c].store];
    mx_enter_s(s_status,mx_satp);
    WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
    check_case(c);
    mx_case_checks[c]=mx_checks-before;
    // A failed case stops before the next case's memory initialization.
  }
  for(unsigned c=0;c<MX_N;++c) {
    for(unsigned r=0;r<4;++r) for(unsigned i=0;i<64;++i) check(mx_seed[c].v[r][i],seed(c,r,i));
    for(unsigned i=0;i<8;++i) { check(mx_seed[c].lo[i],MX_G); check(mx_seed[c].hi[i],MX_G); }
  }
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
  mx_completed=UINT64_C(0x7365677376333904);
  WRITE(mstatus,status);
  replay_text(mx_errors ? "SEGMENT_SV39_FAIL\n":"SEGMENT_SV39_PASS\n");
  return mx_errors!=0;
}
#endif
