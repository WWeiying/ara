#include <stdint.h>
#ifndef STORE
#define STORE 0
#endif
#ifndef SV39
#define SV39 0
#endif
#define GUARD UINT64_C(0xe370697ce370697c)
#define POISON UINT64_C(0xfedcba9876543210)
#define DONE UINT64_C(0x7374726964650009)
#define STATUS_MASK UINT64_C(0x8000031888)
static uint64_t seed(unsigned i) {return UINT64_C(0x9134576800000000) ^ (37*i+11);}
static uint64_t data(unsigned p,unsigned i) {return UINT64_C(0xa136570000000000) ^ ((uint64_t)p<<48) ^ (53*i+19);}
#ifdef ALIGN_HOST
#include <stdio.h>
int main(void) {
  for(unsigned i=0;i<16;i++) printf("%u %016lx %016lx %016lx\n",i,(unsigned long)seed(i),(unsigned long)data(0,i),(unsigned long)data(1,i));
  return 0;
}
#else
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
struct buffer {uint64_t lo[2],words[16],hi[2];};
volatile struct buffer mt_seed __attribute__((aligned(64))), mt_fault __attribute__((aligned(64)));
volatile struct buffer mt_result __attribute__((aligned(64))), mt_next __attribute__((aligned(64)));
volatile struct buffer mt_mem __attribute__((aligned(64))), mt_other __attribute__((aligned(64)));
volatile uint64_t mt_root[512] __attribute__((aligned(4096)));
volatile uint64_t mt_fault_mem[16], mt_records[2][10], mt_post[5], mt_tail[5];
volatile uint64_t mt_target_addr, mt_other_addr, mt_expected_satp, mt_frame;
volatile uint64_t mt_trap_count, mt_marker, mt_unexpected, mt_completed;
volatile unsigned mt_checks, mt_errors;
extern char mt_target[],mt_ecall[];
extern void mt_handler(void),mt_enter(uint64_t,uint64_t);
__attribute__((noinline,noclone)) static void mt_check(uint64_t got,uint64_t want) {
  ++mt_checks;
  if(got!=want) {if(!mt_errors) replay_mismatch(0,mt_checks,want,got);++mt_errors;}
}
static void check_buffers(void) {
  volatile struct buffer *bufs[4]={&mt_seed,&mt_fault,&mt_result,&mt_next};
  for(unsigned b=0;b<4;b++) {
    for(unsigned i=0;i<2;i++) {mt_check(bufs[b]->lo[i],GUARD);mt_check(bufs[b]->hi[i],GUARD);}
    for(unsigned i=0;i<16;i++) {
      if(b==1 && !STORE && i==1) continue; // Incomplete active destination is unspecified on fault.
      uint64_t want=seed(i);
      if(!STORE && ((b==1 && i==0)||(b==2 && i<2))) want=data(0,i);
      if(b==3 && i<2) want=data(1,i);
      mt_check(bufs[b]->words[i],want);
    }
  }
  for(unsigned i=0;i<16;i++) mt_check(mt_fault_mem[i],STORE && i==0 ? seed(0) : data(0,i));
  for(unsigned p=0;p<2;p++) {
    volatile struct buffer *b=p ? &mt_other : &mt_mem;
    for(unsigned i=0;i<2;i++) {mt_check(b->lo[i],GUARD);mt_check(b->hi[i],GUARD);}
    for(unsigned i=0;i<16;i++) {
      uint64_t want=data(p,i);
      if(!p && i==0) want=POISON;
      if(!p && STORE && i==1) want=seed(1);
      if(p && (i==8 || i==9)) want=data(1,i-8);
      mt_check(b->words[i],want);
    }
  }
}
int main(void) {
  uint64_t status,mie,mtvec,mepc,mcause,mtval,satp,medeleg,mideleg;
  uint64_t vl,vtype,vstart,vcsr,fcsr,actual;
  READ(mstatus,status);WRITE(mstatus,status&~UINT64_C(8));
  READ(mie,mie);WRITE(mie,0);READ(mtvec,mtvec);READ(mepc,mepc);
  READ(mcause,mcause);READ(mtval,mtval);READ(satp,satp);READ(medeleg,medeleg);READ(mideleg,mideleg);
  READ(vl,vl);READ(vtype,vtype);READ(vstart,vstart);READ(vcsr,vcsr);READ(fcsr,fcsr);
  READ(vlenb,actual);mt_check(actual,128);mt_check(satp,0);mt_check((uint64_t)mt_root&4095,0);
  WRITE(vstart,0);WRITE(fcsr,117);WRITE(vcsr,5);WRITE(medeleg,0);WRITE(mideleg,0);WRITE(mtvec,mt_handler);
  volatile struct buffer *bufs[6]={&mt_seed,&mt_fault,&mt_result,&mt_next,&mt_mem,&mt_other};
  for(unsigned b=0;b<6;b++) {
    for(unsigned i=0;i<2;i++) bufs[b]->lo[i]=bufs[b]->hi[i]=GUARD;
    for(unsigned i=0;i<16;i++) bufs[b]->words[i]=b==0 ? seed(i) : b<4 ? GUARD : data(b-4,i);
  }
  for(unsigned i=0;i<512;i++) mt_root[i]=SV39 && (i==1 || i==2) ? UINT64_C(0x200000cf) : 0;
  for(unsigned i=0;i<16;i++) mt_fault_mem[i]=GUARD;
  for(unsigned n=0;n<2;n++) for(unsigned i=0;i<10;i++) mt_records[n][i]=UINT64_MAX;
  for(unsigned i=0;i<5;i++) mt_post[i]=mt_tail[i]=UINT64_MAX;
  mt_target_addr=(uint64_t)mt_mem.words-(SV39 ? UINT64_C(0x40000000) : 0);
  mt_other_addr=(uint64_t)mt_other.words-(SV39 ? UINT64_C(0x40000000) : 0);
  mt_expected_satp=SV39 ? (UINT64_C(8)<<60)|((uint64_t)mt_root>>12) : 0;
  const uint64_t enter_status=(status&~(STATUS_MASK|UINT64_C(0x7e602)))|(SV39 ? 0x2a00 : 0x3a00);
  asm volatile("fence rw,rw" : : : "memory");
  if(!mt_errors) mt_enter(enter_status,mt_expected_satp);
  WRITE(satp,satp);asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
  mt_check(mt_unexpected,0);mt_check(mt_trap_count,2);
  for(unsigned n=0;n<2;n++) {
    uint64_t gold[10]={n ? (SV39 ? 9 : 11) : (STORE ? 6 : 4),(uint64_t)(n ? mt_ecall : mt_target),
      n ? 0 : mt_target_addr+4,SV39 ? 0x800 : 0x1800,mt_expected_satp,2,24,n ? 0 : 1,117,5};
    for(unsigned i=0;i<10;i++) mt_check(i==3 ? mt_records[n][i]&STATUS_MASK : mt_records[n][i],gold[i]);
  }
  for(unsigned i=0;i<5;i++) {const uint64_t gold[5]={2,24,0,117,5};mt_check(mt_post[i],gold[i]);mt_check(mt_tail[i],gold[i]);}
  mt_check(mt_marker,1);check_buffers();
  for(unsigned i=0;i<512;i++) mt_check(mt_root[i],SV39 && (i==1 || i==2) ? UINT64_C(0x200000cf) : 0);
  asm volatile("vsetvl zero,%0,%1" : : "r"(vl),"r"(vtype) : "memory");
  WRITE(vstart,vstart);WRITE(vcsr,vcsr);WRITE(fcsr,fcsr);WRITE(mtvec,mtvec);WRITE(mepc,mepc);
  WRITE(mcause,mcause);WRITE(mtval,mtval);WRITE(medeleg,medeleg);WRITE(mideleg,mideleg);WRITE(mie,mie);
#define RESTORE(c) do {READ(c,actual);mt_check(actual,c);} while(0)
  RESTORE(satp);RESTORE(mtvec);RESTORE(mepc);RESTORE(mcause);RESTORE(mtval);RESTORE(medeleg);RESTORE(mideleg);
  RESTORE(mie);RESTORE(vl);RESTORE(vtype);RESTORE(vstart);RESTORE(vcsr);RESTORE(fcsr);
#undef RESTORE
  WRITE(mstatus,status&~UINT64_C(8));READ(mstatus,actual);mt_check(actual,status&~UINT64_C(8));
  mt_completed=DONE;WRITE(mstatus,status);
  replay_text(mt_errors ? "STRIDED_ALIGNMENT_FAIL\n" : "STRIDED_ALIGNMENT_PASS\n");
  return mt_errors!=0;
}
#endif
