// SPDX-License-Identifier: SHL-0.51
// Indexed LOAD prefix/misalignment recovery; fault-active destination is undefined.
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
#define POISON UINT64_C(0xbad0123456789abc)
static uint64_t index_expected(unsigned r,unsigned e,unsigned fixed) {
  if (e < 3) {
    const uint64_t a[3]={32,8,17},b[3]={24,0,16};
    return r==0 ? (fixed && e==2 ? 16 : a[e]) : b[e];
  }
  return 128+e*8;
}
static uint64_t source_expected(unsigned r,unsigned e) {
  if (r==0 || r==4) return index_expected(r,e,0);
  return UINT64_C(0x6c70000012340000) ^ ((uint64_t)r<<48) ^ (e*37+19);
}
static uint32_t seed_expected(unsigned r,unsigned w) {
  return source_expected(r,w/2) >> (32*(w&1));
}
static uint32_t result_expected(unsigned r,unsigned w) {
  unsigned e=w/2;
  uint64_t v=source_expected(r,e);
  if (r==0 && e==2) v=16;
  if (r==1 && (e==1 || e==2 || e==4)) v=data_expected(0,e==4 ? 20 : e);
  if (r==5 && e==0) v=data_expected(0,32);
  if (r==5 && e==1) v+=1;
  return v >> (32*(w&1));
}
static uint64_t fault_expected(unsigned p,unsigned i) {
  return data_expected(p,i);
}
static unsigned fault_vector_defined(unsigned r,unsigned w) {
  return !(r==1 && (w/2==2 || w/2==4));
}
static uint32_t fault_vector_expected(unsigned r,unsigned w) {
  return r==1 && w/2==1 ? data_expected(0,1) >> (32*(w&1)) : seed_expected(r,w);
}
static uint64_t memory_expected(unsigned p,unsigned i) {
  if (p==0) {
    if (i==1) return POISON;
    if (i==35) return source_expected(5,0);
    if (i==34) return source_expected(5,2);
  }
  return data_expected(p,i);
}
static uint8_t mask_expected(unsigned m,unsigned b) {
  const uint8_t masks[3]={23,5,2};
  return b==0 ? masks[m] : 0;
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
  for (unsigned p=0;p<2;p++) for (unsigned i=0;i<512;i++)
    printf("F %u %u %016lx\n",p,i,(unsigned long)fault_expected(p,i));
  for (unsigned r=0;r<7;r++) for (unsigned w=0;w<32;w++)
    printf("P %u %u %08x %u\n",r,w,fault_vector_expected(r,w),fault_vector_defined(r,w));
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
struct prefix_image { uint32_t lo[16]; uint64_t words[1024]; uint32_t hi[16]; };
volatile struct prefix_image mt_prefix __attribute__((aligned(64)));
volatile uint64_t mt_fix_index[16] __attribute__((aligned(64)));
volatile uint64_t mt_restart[3];
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
    const uint64_t gold[12]={n ? 9 : 4,(uint64_t)(n ? mt_ecall : mt_target),
      n ? 0 : 0x40000011,0x800,mt_expected_satp,5,24,n ? 0 : 2,117,5,n,mt_repair_pte};
    for (unsigned j=0;j<12;j++) check(j==3 ? mt_records[n][j]&TRAP_MASK : mt_records[n][j],gold[j]);
  }
  const uint64_t post[5]={5,24,0,117,5},after[5]={5,24,0,117,5};
  for (unsigned i=0;i<5;i++) {
    check(mt_post[i],post[i]);check(mt_load_post[i],after[i]);check(mt_after[i],after[i]);
    check(mt_store_post[i],after[i]);
  }
  check(mt_marker,1);
  for (unsigned m=0;m<3;m++) for (unsigned b=0;b<16;b++) check(mt_mask[m][b],mask_expected(m,b));
  volatile struct vectors *bufs[3]={&mt_seed,&mt_fault,&mt_result};
  for (unsigned b=0;b<3;b++) {
    for (unsigned i=0;i<16;i++) {check(bufs[b]->lo[i],GUARD);check(bufs[b]->hi[i],GUARD);}
    for (unsigned r=0;r<7;r++) for (unsigned w=0;w<32;w++) {
      if (b==1 && !fault_vector_defined(r,w)) continue;
      check(bufs[b]->words[r][w],b==2 ? result_expected(r,w) :
            b==1 ? fault_vector_expected(r,w) : seed_expected(r,w));
    }
  }
  check(mt_restart[0],5);check(mt_restart[1],24);check(mt_restart[2],2);
  for (unsigned i=0;i<16;i++) check(mt_fix_index[i],index_expected(0,i,1));
  for (unsigned i=0;i<16;i++) {check(mt_prefix.lo[i],GUARD);check(mt_prefix.hi[i],GUARD);}
  uint64_t bad=0;
  for (unsigned p=0;p<2;p++) for (unsigned w=0;w<512;w++) bad |= mt_prefix.words[p*512+w]^fault_expected(p,w);
  check(bad,0);bad=0;
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
    mt_prefix.lo[i]=mt_prefix.hi[i]=GUARD;
    mt_fix_index[i]=index_expected(0,i,1);
    mt_seed.lo[i]=mt_seed.hi[i]=mt_fault.lo[i]=mt_fault.hi[i]=mt_result.lo[i]=mt_result.hi[i]=GUARD;
    for (unsigned m=0;m<3;m++) mt_mask[m][i]=mask_expected(m,i);
  }
  for (unsigned r=0;r<7;r++) for (unsigned w=0;w<32;w++) {
    mt_seed.words[r][w]=seed_expected(r,w);
    mt_fault.words[r][w]=mt_result.words[r][w]=GUARD;
  }
  for (unsigned n=0;n<2;n++) for (unsigned j=0;j<12;j++) mt_records[n][j]=UINT64_MAX;
  for (unsigned i=0;i<5;i++) mt_post[i]=mt_load_post[i]=mt_after[i]=mt_store_post[i]=UINT64_MAX;
  for (unsigned i=0;i<1024;i++) mt_prefix.words[i]=UINT64_C(0xe370697ce370697c);
  ROOT[1]=pte(MID,1);ROOT[2]=UINT64_C(0x200000cf);MID[0]=pte(LEAF,1);
  LEAF[0]=pte(mt_pages[0],0xc7);mt_repair_pte=pte(mt_pages[1],0xc7);LEAF[1]=mt_repair_pte;
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
  replay_text(mt_errors ? "INDEXED_LOAD_SV39_FAIL\n" : "INDEXED_LOAD_SV39_PASS\n");
  return mt_errors!=0;
}
#endif
