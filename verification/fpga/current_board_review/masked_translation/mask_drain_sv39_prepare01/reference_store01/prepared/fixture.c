// SPDX-License-Identifier: SHL-0.51
// New mask-drain boundary; Sv39 scaffold derived from ../sv39_fixture.c.
#include <stdint.h>
#ifndef STORE
#define STORE 0
#endif
#define GUARD UINT32_C(0xe370697c)
#define DONE UINT64_C(0x6d647261696e0001)
#define TRAP_MASK UINT64_C(0x8000031888)
static uint64_t data_expected(unsigned page, unsigned i) {
  return UINT64_C(0xa136570000000000) ^ ((uint64_t)page << 48) ^ ((uint64_t)i * 37 + 11);
}
static uint32_t seed_expected(unsigned r, unsigned w) {
  return r >= 1 && r <= 4 ? UINT32_C(0x5b5b5b5b) : UINT32_C(0x6c700000) ^ (r << 16) ^ w;
}
static uint32_t result_expected(unsigned r, unsigned w) {
  unsigned e = w / 2;
  uint64_t v = seed_expected(r,2*e) | ((uint64_t)seed_expected(r,2*e+1) << 32);
  if (!STORE && r == 1 && e < 9) v = data_expected(1,0);
  if (r == 6 && e < 9) {
    if (!(e & 1)) v = data_expected(0,e);
    else v += 1;
  }
  return (uint32_t)(v >> (32*(w & 1)));
}
static uint64_t memory_expected(unsigned page,unsigned i) {
  if (STORE && page == 1 && i < 9)
    return seed_expected(1,2*i) | ((uint64_t)seed_expected(1,2*i+1) << 32);
  if (page == 0 && i >= 16 && i < 25 && ((i-16)&1))
    return result_expected(6,2*(i-16)) | ((uint64_t)result_expected(6,2*(i-16)+1) << 32);
  return data_expected(page,i);
}
static uint8_t mask_expected(unsigned m, unsigned b) {
  return b == 0 ? (m == 0 ? 255 : m == 1 ? 85 : 170) : b == 1 && m != 2;
}
#ifdef MD_HOST
#include <stdio.h>
int main(void) {
  for (unsigned r=0;r<7;r++) for (unsigned w=0;w<32;w++)
    printf("R %u %u %08x %08x\n",r,w,seed_expected(r,w),result_expected(r,w));
  for (unsigned p=0;p<2;p++) for (unsigned i=0;i<512;i++)
    printf("D %u %u %016lx %016lx\n",p,i,(unsigned long)data_expected(p,i),(unsigned long)memory_expected(p,i));
  for (unsigned m=0;m<3;m++) for (unsigned b=0;b<16;b++)
    printf("M %u %u %02x\n",m,b,mask_expected(m,b));
  return 0;
}
#else
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
#define READ(c,x) asm volatile("csrr %0, " #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ", %0" : : "r"((uint64_t)(x)) : "memory")
asm(".pushsection .bss.mt_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl mt_guard_lo\nmt_guard_lo: .zero 64\n"
    ".globl mt_pages\nmt_pages: .zero 20480\n"
    ".globl mt_guard_hi\nmt_guard_hi: .zero 64\n.popsection\n");
extern volatile uint64_t mt_pages[5][512];
extern volatile uint32_t mt_guard_lo[16],mt_guard_hi[16];
#define ROOT mt_pages[2]
#define MID mt_pages[3]
#define LEAF mt_pages[4]
struct vectors { uint32_t lo[16],words[7][32],hi[16]; };
volatile struct vectors mt_seed __attribute__((aligned(64)));
volatile struct vectors mt_fault __attribute__((aligned(64)));
volatile struct vectors mt_result __attribute__((aligned(64)));
volatile uint8_t mt_mask[3][16] __attribute__((aligned(64)));
volatile uint64_t mt_records[2][12],mt_post[5],mt_load_post[5],mt_after[5],mt_store_post[5];
volatile uint64_t mt_trap_count,mt_marker,mt_repair_pte,mt_frame;
volatile uint64_t mt_unexpected,mt_completed,mt_expected_satp;
volatile unsigned mt_checks,mt_errors;
extern char mt_target[],mt_ecall[];
extern void mt_handler(void),mt_enter_s(uint64_t,uint64_t);
static void check(uint64_t got,uint64_t want) {
  ++mt_checks;
  if (got != want) {
    if (!mt_errors) replay_mismatch(0,mt_checks,want,got);
    ++mt_errors;
  }
}
static uint64_t pte(const volatile void *p,uint64_t flags) {
  return ((uint64_t)p >> 12 << 10) | flags;
}
static void check_result(void) {
  check(mt_unexpected,0);check(mt_trap_count,2);
  for (unsigned n=0;n<2;n++) {
    const uint64_t gold[12]={n ? 9 : STORE ? 15 : 13,(uint64_t)(n ? mt_ecall : mt_target),
      n ? 0 : 0x40001000,0x800,mt_expected_satp,9,26,0,117,5,n,n ? mt_repair_pte : 0};
    for (unsigned j=0;j<12;j++) check(j==3 ? mt_records[n][j]&TRAP_MASK : mt_records[n][j],gold[j]);
  }
  const uint64_t post[5]={9,26,0,117,5},after[5]={9,24,0,117,5};
  for (unsigned i=0;i<5;i++) {
    check(mt_post[i],post[i]);check(mt_load_post[i],after[i]);check(mt_after[i],after[i]);
    check(mt_store_post[i],after[i]);
  }
  check(mt_marker,1);
  for (unsigned m=0;m<3;m++) for (unsigned b=0;b<16;b++) check(mt_mask[m][b],mask_expected(m,b));
  volatile struct vectors *bufs[3]={&mt_seed,&mt_fault,&mt_result};
  for (unsigned b=0;b<3;b++) {
    for (unsigned i=0;i<16;i++) {check(bufs[b]->lo[i],GUARD);check(bufs[b]->hi[i],GUARD);}
    for (unsigned r=0;r<7;r++) for (unsigned w=0;w<32;w++)
      check(bufs[b]->words[r][w],b==2 ? result_expected(r,w) : seed_expected(r,w));
  }
  uint64_t bad=0;
  for (unsigned p=0;p<2;p++) for (unsigned w=0;w<512;w++) bad |= mt_pages[p][w]^memory_expected(p,w);
  check(bad,0);bad=0;
  for (unsigned w=0;w<512;w++) {
    bad |= ROOT[w]^(w==1 ? pte(MID,1) : w==2 ? UINT64_C(0x200000cf) : 0);
    bad |= MID[w]^(w==0 ? pte(LEAF,1) : 0);
    bad |= LEAF[w]^(w==0 ? pte(mt_pages[0],0xc7) : w==1 ? mt_repair_pte : 0);
  }
  check(bad,0);
  for (unsigned i=0;i<16;i++) {check(mt_guard_lo[i],GUARD);check(mt_guard_hi[i],GUARD);}
}
int main(void) {
  uint64_t status,mie,mtvec,mepc,mcause,mtval,satp,medeleg,mideleg;
  uint64_t vl,vtype,vstart,vcsr,fcsr,actual;
  READ(mstatus,status);WRITE(mstatus,status&~UINT64_C(8));
  READ(mie,mie);WRITE(mie,0);READ(mtvec,mtvec);READ(mepc,mepc);
  READ(mcause,mcause);READ(mtval,mtval);READ(satp,satp);
  READ(medeleg,medeleg);READ(mideleg,mideleg);
  READ(vl,vl);READ(vtype,vtype);READ(vstart,vstart);READ(vcsr,vcsr);READ(fcsr,fcsr);
  READ(vlenb,actual);check(actual,128);check(satp,0);check((uint64_t)mt_pages&4095,0);
  WRITE(vstart,0);WRITE(fcsr,117);WRITE(vcsr,5);
  WRITE(medeleg,0);WRITE(mideleg,0);WRITE(mtvec,mt_handler);
  for (unsigned p=0;p<5;p++) for (unsigned w=0;w<512;w++)
    mt_pages[p][w]=p<2 ? data_expected(p,w) : 0;
  for (unsigned i=0;i<16;i++) {
    mt_guard_lo[i]=mt_guard_hi[i]=GUARD;
    mt_seed.lo[i]=mt_seed.hi[i]=mt_fault.lo[i]=mt_fault.hi[i]=mt_result.lo[i]=mt_result.hi[i]=GUARD;
    for (unsigned m=0;m<3;m++) mt_mask[m][i]=mask_expected(m,i);
  }
  for (unsigned r=0;r<7;r++) for (unsigned w=0;w<32;w++) {
    mt_seed.words[r][w]=seed_expected(r,w);
    mt_fault.words[r][w]=mt_result.words[r][w]=GUARD;
  }
  for (unsigned n=0;n<2;n++) for (unsigned j=0;j<12;j++) mt_records[n][j]=UINT64_MAX;
  for (unsigned i=0;i<5;i++) mt_post[i]=mt_load_post[i]=mt_after[i]=mt_store_post[i]=UINT64_MAX;
  ROOT[1]=pte(MID,1);ROOT[2]=UINT64_C(0x200000cf);MID[0]=pte(LEAF,1);
  LEAF[0]=pte(mt_pages[0],0xc7);mt_repair_pte=pte(mt_pages[1],0xc7);
  mt_expected_satp=(UINT64_C(8)<<60)|((uint64_t)ROOT>>12);
  const uint64_t s_status=(status&~(TRAP_MASK|UINT64_C(0x7e602)))|0x2a00;
  asm volatile("fence rw,rw" : : : "memory");
  if (!mt_errors) mt_enter_s(s_status,mt_expected_satp);
  WRITE(satp,satp);asm volatile("sfence.vma zero,zero\nfence rw,rw" : : : "memory");
  check_result();
  asm volatile("vsetvl zero,%0,%1" : : "r"(vl),"r"(vtype) : "memory");
  WRITE(vstart,vstart);WRITE(vcsr,vcsr);WRITE(fcsr,fcsr);
  WRITE(mtvec,mtvec);WRITE(mepc,mepc);WRITE(mcause,mcause);WRITE(mtval,mtval);
  WRITE(medeleg,medeleg);WRITE(mideleg,mideleg);WRITE(mie,mie);
#define RESTORE(c) do {READ(c,actual);check(actual,c);} while(0)
  RESTORE(satp);RESTORE(mtvec);RESTORE(mepc);RESTORE(mcause);RESTORE(mtval);
  RESTORE(medeleg);RESTORE(mideleg);RESTORE(mie);RESTORE(vl);RESTORE(vtype);
  RESTORE(vstart);RESTORE(vcsr);RESTORE(fcsr);
#undef RESTORE
  WRITE(mstatus,status&~UINT64_C(8));READ(mstatus,actual);check(actual,status&~UINT64_C(8));
  mt_completed=DONE;WRITE(mstatus,status);
  replay_text(mt_errors ? "MASK_DRAIN_SV39_FAIL\n" : "MASK_DRAIN_SV39_PASS\n");
  return mt_errors!=0;
}
#endif
