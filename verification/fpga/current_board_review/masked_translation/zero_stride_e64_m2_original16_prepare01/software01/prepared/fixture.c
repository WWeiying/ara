#include <stdint.h>
#define CAP 32
#define ALLOC 256
#define MASK_BYTES 32
#define VTYPE 25
#define VA UINT64_C(0x40000000)
#define GUARD UINT64_C(0xe370697ce370697c)
#define DONE UINT64_C(0x7a65726f31360001)
#define STATUS_MASK UINT64_C(0x8000031888)
static unsigned mask_value(unsigned mode) { return mode==0?255:mode==1?170:mode==2?36:0; }
static unsigned first(unsigned mode) { return mode<3?mode:8; }
static uint64_t original(unsigned word) { return 37*(uint64_t)word+11; }
#ifdef HOST_ORACLE
#include <stdio.h>
int main(void) {
  for(unsigned c=0;c<16;++c) {
    unsigned mode=c%4,store=(c/4)%2;
    printf("C %u %u %u %u %u\n",c,c/8,store,mask_value(mode),first(mode));
    for(unsigned i=0;i<CAP;++i)
      printf("V %u %u %lu\n",c,i,store?UINT64_C(101):i<8 && ((mask_value(mode)>>i)&1)?original(512):UINT64_C(91));
    for(unsigned i=0;i<1024;++i)
      printf("D %u %u %lu\n",c,i,store && mode<3 && i==512?UINT64_C(101):original(i));
  }
  return 0;
}
#else
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern unsigned long capacity(void);
extern void mx_handler(void),mx_enter_s(uint64_t,uint64_t),mx_snapshot(void *),mx_bootstrap(void);
extern char fault_0_pc[],fault_1_pc[],mx_ecall[];
asm(".pushsection .bss.mx_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl mx_guard_lo\nmx_guard_lo:.zero 64\n.globl mx_pages\nmx_pages:.zero 20480\n"
    ".globl mx_guard_hi\nmx_guard_hi:.zero 64\n.popsection\n");
extern volatile uint64_t mx_pages[5][512],mx_guard_lo[8],mx_guard_hi[8];
#define ROOT mx_pages[2]
#define MID mx_pages[3]
#define LEAF mx_pages[4]
struct snapshot { uint64_t lo[8],v[CAP],hi[8]; };
volatile struct snapshot mx_fault,mx_result;
volatile uint64_t mx_input[ALLOC],mx_offsets[ALLOC],mx_out[ALLOC+2];
volatile uint8_t mx_mask[MASK_BYTES];
volatile int64_t mx_stride;
volatile uint64_t mx_records[16][2][12],mx_post[16][6];
volatile uint64_t mx_case,mx_phase,mx_store,mx_unmapped,mx_mode,mx_count,mx_marker,mx_restart;
volatile uint64_t mx_satp,mx_completed,mx_checks,mx_errors,mx_unexpected,mx_return,mx_signals;
volatile uint64_t mx_action_source[3],mx_action_copy[3];
static uint64_t pte(const volatile void *p,uint64_t f) { return ((uint64_t)p>>12<<10)|f; }
static volatile uint64_t *physical(unsigned word) { return &mx_pages[word/512][word%512]; }
static unsigned active(unsigned i) { return (mx_mask[i/8]>>(i%8))&1; }
__attribute__((noinline)) void check(uint64_t got,uint64_t want) {
  ++mx_checks;
  if(got!=want) { if(!mx_errors) replay_mismatch(mx_case,mx_checks,want,got); ++mx_errors; }
}
__attribute__((noinline)) void mx_checkpoint(void) { asm volatile("" : : : "memory"); }
static void checkpoint(unsigned p) { mx_phase=p; mx_checkpoint(); }
__attribute__((noinline)) void mx_refill_page(void) {
  for(unsigned i=0;i<512;++i) mx_pages[1][i]=original(512+i);
}
static void restore_page(void) {
  LEAF[1]=pte(mx_pages[1],0xc7);
  asm volatile("fence rw,rw\n.global mx_repair_sfence\nmx_repair_sfence:\n"
               "sfence.vma %0,zero" : : "r"(VA+4096) : "memory");
  if(mx_unmapped) mx_refill_page();
}
int mx_trap(void) {
  uint64_t e[12];
  /* Match the kernel's vector-CSR observation before any diagnostic RVV. */
  READ(vstart,e[7]); READ(vtype,e[6]); READ(vl,e[5]);
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(fcsr,e[8]); READ(vcsr,e[9]); e[10]=mx_marker; e[11]=LEAF[1];
  unsigned n=mx_count++;
  if(n>=2) { ++mx_unexpected; return 1; }
  for(unsigned i=0;i<12;++i) mx_records[mx_case][n][i]=e[i];
  unsigned finish=e[0]==9,expected_n=mx_mode==3?0:1;
  uint64_t want[12]={finish?9:mx_store?15:13,
    (uint64_t)(finish?mx_ecall:mx_store?fault_1_pc:fault_0_pc),finish?0:VA+4096,
    0x800,mx_satp,finish?CAP:8,VTYPE,finish?0:first(mx_mode),0,0,finish?1:0,
    finish && mx_mode!=3?pte(mx_pages[1],0xc7):mx_unmapped?0:pte(mx_pages[1],1)};
  check(n,finish?expected_n:0);
  for(unsigned i=0;i<12;++i) check(i==3?e[i]&STATUS_MASK:e[i],want[i]);
  if(mx_errors) { ++mx_unexpected; return 1; }
  if(finish) return 1;
  ++mx_signals; mx_restart=e[7];
  mx_snapshot((void *)&mx_fault);
  for(unsigned i=0;i<8;++i) { check(mx_fault.lo[i],GUARD); check(mx_fault.hi[i],GUARD); }
  /* The original signal oracle constrains only the prestart prefix. */
  for(unsigned i=0;i<first(mx_mode) && i<8;++i)
    check(mx_fault.v[i],mx_store?mx_input[i]:active(i)?original(512):0x5b);
  checkpoint(1);
  restore_page();
  for(unsigned i=0;i<first(mx_mode) && i<8;++i)
    if(active(i)) *physical(512)=mx_store?(mx_input[i]^0x5b):(original(512)^0x5b);
  asm volatile("fence rw,rw" : : : "memory");
  checkpoint(2);
  return 0;
}
static unsigned logical_element(unsigned word) {
  for(unsigned i=0;i<8;++i)
    if(512+i*mx_stride/8==word && active(i)) return i;
  return 8;
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
  WRITE(vstart,0); check(capacity(),CAP);
  /* Original compiler's three RVV sigaction initialization instructions. */
  mx_action_source[0]=(uint64_t)mx_handler; mx_action_source[1]=4; mx_action_source[2]=0;
  mx_bootstrap();
  WRITE(fcsr,0); WRITE(vcsr,0); WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,mx_handler);
  for(unsigned p=2;p<5;++p) for(unsigned w=0;w<512;++w) mx_pages[p][w]=0;
  for(unsigned i=0;i<8;++i) mx_guard_lo[i]=mx_guard_hi[i]=GUARD;
  ROOT[1]=pte(MID,1); ROOT[2]=UINT64_C(0x200000cf); MID[0]=pte(LEAF,1);
  mx_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  for(unsigned c=0;c<16;++c) for(unsigned n=0;n<2;++n) for(unsigned j=0;j<12;++j) mx_records[c][n][j]=UINT64_MAX;
  for(unsigned c=0;c<16;++c) for(unsigned j=0;j<6;++j) mx_post[c][j]=UINT64_MAX;
  const uint64_t s_status=(status&~(STATUS_MASK|UINT64_C(0x7e602)))|0x2a00;
  for(mx_unmapped=0;mx_unmapped<2;++mx_unmapped) for(mx_store=0;mx_store<2;++mx_store)
  for(mx_mode=0;mx_mode<4;++mx_mode) {
    mx_case=8*mx_unmapped+4*mx_store+mx_mode;
    for(unsigned w=0;w<1024;++w) *physical(w)=original(w);
    mx_stride=0;
    for(unsigned i=0;i<CAP;++i) mx_input[i]=101;
    for(unsigned i=0;i<ALLOC;++i) mx_offsets[i]=8*(i<8?(i+1)%8:i);
    for(unsigned i=0;i<ALLOC+2;++i) mx_out[i]=0x5b;
    for(unsigned i=0;i<MASK_BYTES;++i) mx_mask[i]=mask_value(mx_mode);
    for(unsigned i=0;i<CAP+16;++i) { ((volatile uint64_t *)&mx_fault)[i]=GUARD; ((volatile uint64_t *)&mx_result)[i]=GUARD; }
    mx_count=mx_marker=mx_restart=mx_return=0;
    LEAF[0]=pte(mx_pages[0],0xc7); LEAF[1]=mx_unmapped?0:pte(mx_pages[1],1);
    checkpoint(0);
    mx_enter_s(s_status,mx_satp);
    WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
    check(mx_unexpected,0); check(mx_count,mx_mode==3?1:2); check(mx_marker,1); check(mx_return,0);
    const uint64_t post[6]={CAP,VTYPE,0,0,0,0};
    for(unsigned j=0;j<6;++j) check(mx_post[mx_case][j],post[j]);
    checkpoint(3);
    if(mx_mode==3) restore_page();
    for(unsigned i=0;i<CAP;++i) {
      uint64_t wanted=mx_store?mx_input[i]:i<8 && active(i)?original(512):0x5b;
      check(mx_out[i+1],wanted); check(mx_result.v[i],wanted);
    }
    /* Keep the original per-address, per-logical-element full-memory oracle. */
    for(unsigned w=0;w<1024;++w) {
      uint64_t wanted=original(w); unsigned j=logical_element(w);
      if(mx_store && j<8) { if(active(j)) wanted=mx_mode<3 && j<first(mx_mode)?mx_input[j]^0x5b:mx_input[j]; }
      else if(!mx_store && mx_mode<3 && j<first(mx_mode)) { if(active(j)) wanted^=0x5b; }
      check(*physical(w),wanted);
    }
    check(mx_out[0],0x5b); check(mx_out[CAP+1],0x5b);
    checkpoint(4);
    LEAF[0]=LEAF[1]=0;
    asm volatile("sfence.vma zero,zero" : : : "memory");
  }
  check(mx_signals,12); check(mx_case,15);
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
  replay_text(mx_errors?"ZERO_STRIDE_ORIGINAL16_FAIL\n":"ZERO_STRIDE_ORIGINAL16_PASS cases=16 faults=12 errors=0\n");
  return mx_errors!=0;
}
#endif

