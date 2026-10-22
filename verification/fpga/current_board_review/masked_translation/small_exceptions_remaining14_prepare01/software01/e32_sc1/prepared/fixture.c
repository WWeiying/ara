#include "fixture.h"
#ifdef HOST_ORACLE
#include <stdio.h>
int main(void) {
  for(unsigned phase=0;phase<2;++phase)
    for(unsigned i=0;i<130;++i)
      printf("O %u %u %d %llu\n",phase,i,output_defined(phase,i),
             (unsigned long long)output_gold(phase,i));
  for(unsigned i=0;i<16;++i) printf("M %u %u\n",i,mask_gold(i));
  for(unsigned i=0;i<2560;++i)
    printf("P %u %llu\n",i,(unsigned long long)page_gold(UINT64_C(0x81000000),i));
  return 0;
}
#else
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern unsigned long capacity(void);
extern void fx_handler(void),fx_enter_s(uint64_t,uint64_t);
extern char fx_ecall[];
asm(".pushsection .bss.fx_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl fx_guard_lo\nfx_guard_lo:.zero 64\n.globl fx_pages\nfx_pages:.zero 20480\n"
    ".globl fx_guard_hi\nfx_guard_hi:.zero 64\n.popsection\n");
extern volatile uint64_t fx_pages[5][512],fx_guard_lo[8],fx_guard_hi[8];
volatile word fx_out[130];
volatile uint8_t fx_mask[16];
volatile uint64_t fx_records[10],fx_post[5];
volatile uint64_t fx_count,fx_marker,fx_satp,fx_phase,fx_completed;
volatile uint64_t fx_checks,fx_errors,fx_unexpected,fx_return;
__attribute__((noinline)) static void check(uint64_t got,uint64_t want) {
  ++fx_checks;
  if(got!=want) { if(!fx_errors) replay_mismatch(fx_phase,fx_checks,want,got); ++fx_errors; }
}
__attribute__((noinline)) void fx_checkpoint(void) { asm volatile("" : : : "memory"); }
__attribute__((noinline)) static void check_state(unsigned phase) {
  for(unsigned i=0;i<2560;++i)
    check(((volatile uint64_t *)fx_pages)[i],page_gold((uint64_t)fx_pages,i));
  for(unsigned i=0;i<8;++i) { check(fx_guard_lo[i],GUARD); check(fx_guard_hi[i],GUARD); }
  for(unsigned i=0;i<130;++i) if(output_defined(phase,i)) check(fx_out[i],output_gold(phase,i));
  for(unsigned i=0;i<16;++i) check(fx_mask[i],mask_gold(i));
  fx_phase=phase; fx_checkpoint();
}
void fx_trap(void) {
  uint64_t e[10];
  READ(mcause,e[0]); READ(mepc,e[1]); READ(mtval,e[2]); READ(mstatus,e[3]);
  READ(satp,e[4]); READ(vl,e[5]); READ(vtype,e[6]); READ(vstart,e[7]);
  READ(fcsr,e[8]); READ(vcsr,e[9]);
  ++fx_count;
  for(unsigned i=0;i<10;++i) fx_records[i]=e[i];
  if(e[0]!=9 || e[1]!=(uint64_t)fx_ecall || fx_count!=1 || fx_marker!=1) ++fx_unexpected;
  const uint64_t want[10]={9,(uint64_t)fx_ecall,0,0x800,fx_satp,8,TYPE,0,117,5};
  for(unsigned i=0;i<10;++i) check(i==3 ? e[i]&STATUS_MASK:e[i],want[i]);
}
int main(void) {
  uint64_t status,mie,mtvec,mepc,mcause,mtval,satp,medeleg,mideleg;
  uint64_t vl,vtype,vstart,vcsr,fcsr,actual;
  READ(mstatus,status); WRITE(mstatus,status&~UINT64_C(8));
  READ(mie,mie); WRITE(mie,0); READ(mtvec,mtvec); READ(mepc,mepc);
  READ(mcause,mcause); READ(mtval,mtval); READ(satp,satp);
  READ(medeleg,medeleg); READ(mideleg,mideleg);
  READ(vl,vl); READ(vtype,vtype); READ(vstart,vstart); READ(vcsr,vcsr); READ(fcsr,fcsr);
  READ(vlenb,actual); check(actual,128); check(satp,0); check((uint64_t)fx_pages&4095,0);
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5); check(capacity(),1024/SEW);
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,fx_handler);
  for(unsigned i=0;i<2560;++i) ((volatile uint64_t *)fx_pages)[i]=0;
  for(unsigned i=0;i<8;++i) fx_guard_lo[i]=fx_guard_hi[i]=GUARD;
  volatile word *source=(volatile word *)((volatile uint8_t *)fx_pages+4096)-4;
  for(unsigned i=0;i<4;++i) source[i]=(word)(i*37+11);
  fx_pages[2][1]=pte((uint64_t)fx_pages+12288,1);
  fx_pages[2][2]=UINT64_C(0x200000cf);
  fx_pages[3][0]=pte((uint64_t)fx_pages+16384,1);
  fx_pages[4][0]=pte((uint64_t)fx_pages,0xc7);
  fx_pages[4][1]=0;
  fx_satp=(UINT64_C(8)<<60)|(((uint64_t)fx_pages+8192)>>12);
  for(unsigned i=0;i<130;++i) fx_out[i]=(word)0x5b;
  for(unsigned i=0;i<16;++i) fx_mask[i]=mask_gold(i);
  for(unsigned i=0;i<10;++i) fx_records[i]=UINT64_MAX;
  for(unsigned i=0;i<5;++i) fx_post[i]=UINT64_MAX;
  fx_return=UINT64_MAX;
  check_state(0);
  const uint64_t s_status=(status&~(STATUS_MASK|UINT64_C(0x7e602)))|0x2a00;
  fx_enter_s(s_status,fx_satp);
  WRITE(satp,0); asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
  check(fx_unexpected,0); check(fx_count,1); check(fx_marker,1); check(fx_return,EXPECT_VL);
  const uint64_t post[5]={8,TYPE,0,117,5};
  for(unsigned i=0;i<5;++i) check(fx_post[i],post[i]);
  check_state(1);
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
  fx_completed=DONE; WRITE(mstatus,status);
  replay_text(fx_errors ? "SMALL_EXCEPTIONS_14_FAIL\n":"SMALL_EXCEPTIONS_14_PASS\n");
  return fx_errors!=0;
}
#endif
