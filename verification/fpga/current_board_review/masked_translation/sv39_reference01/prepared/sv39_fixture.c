// SPDX-License-Identifier: SHL-0.51
// Independent scenario3 semantic derivative; not an original Linux ELF replay.
#include <stdint.h>
#ifndef VARIANT
#define VARIANT 0
#endif
#define ACTIVE (VARIANT == 1)
#define VALID (VARIANT == 2)
#define GUARD UINT32_C(0xe370697c)
#define DONE UINT64_C(0x6d74737633390001)
#define TRAP_MASK UINT64_C(0x8000031888)

static uint16_t data_expected(unsigned page, unsigned i) {
  if (!page && i >= 2044) return (uint16_t)((i - 2044) * 37 + 11);
  return (uint16_t)(0x3100 + page * 0x4000 + i * 37);
}
static uint32_t seed_expected(unsigned r, unsigned w) {
  return r == 1 ? UINT32_C(0x005b005b) : UINT32_C(0x6c700000) ^ (r << 16) ^ w;
}
static uint32_t result_expected(unsigned r, unsigned w) {
  uint32_t v = seed_expected(r, w);
  for (unsigned h = 0; h < 2; ++h) {
    unsigned i = 2*w+h;
    if ((r == 1 && ACTIVE && i == 0) || (r == 3 && i < 8)) {
      uint32_t x = data_expected(r == 1, i);
      v = (v & ~(UINT32_C(65535) << (16*h))) | (x << (16*h));
    }
  }
  return v;
}
#ifdef MT_HOST
#include <stdio.h>
int main(void) {
  for (unsigned r = 0; r < 4; ++r)
    for (unsigned w = 0; w < 32; ++w)
      printf("R %u %u %08x %08x\n", r, w, seed_expected(r,w), result_expected(r,w));
  for (unsigned p = 0; p < 2; ++p)
    for (unsigned i = 0; i < 2048; ++i)
      printf("D %u %u %04x\n", p, i, data_expected(p,i));
  return 0;
}
#else
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long, unsigned long, unsigned long, unsigned long);
#define READ(c,x) asm volatile("csrr %0, " #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ", %0" : : "r"((uint64_t)(x)) : "memory")
asm(".pushsection .bss.mt_pages,\"aw\",@nobits\n.balign 4096\n.zero 4032\n"
    ".globl mt_guard_lo\nmt_guard_lo: .zero 64\n"
    ".globl mt_pages\nmt_pages: .zero 20480\n"
    ".globl mt_guard_hi\nmt_guard_hi: .zero 64\n.popsection\n");
extern volatile uint64_t mt_pages[5][512];
extern volatile uint32_t mt_guard_lo[16], mt_guard_hi[16];
#define ROOT mt_pages[2]
#define MID mt_pages[3]
#define LEAF mt_pages[4]
struct vectors { uint32_t lo[16], words[4][32], hi[16]; };
volatile struct vectors mt_seed __attribute__((aligned(64)));
volatile struct vectors mt_fault __attribute__((aligned(64)));
volatile struct vectors mt_result __attribute__((aligned(64)));
volatile uint16_t mt_out[130] __attribute__((aligned(64)));
volatile uint8_t mt_mask[16] __attribute__((aligned(64)));
volatile uint64_t mt_records[2][12], mt_post[5];
volatile uint64_t mt_trap_count, mt_marker, mt_repair_pte, mt_frame;
volatile uint64_t mt_unexpected, mt_completed, mt_expected_satp;
volatile unsigned mt_checks, mt_errors;
extern char mt_target[], mt_ecall[];
extern void mt_handler(void), mt_enter_s(uint64_t, uint64_t);

static void check(uint64_t got, uint64_t want) {
  ++mt_checks;
  if (got != want) {
    if (!mt_errors) replay_mismatch(VARIANT, mt_checks, want, got);
    ++mt_errors;
  }
}
static uint64_t pte(const volatile void *p, uint64_t flags) {
  return ((uint64_t)p >> 12 << 10) | flags;
}
static void check_result(void) {
  check(mt_unexpected,0); check(mt_trap_count,ACTIVE ? 2 : 1);
  for (unsigned n = 0; n < 2; ++n) {
    int used = n == 0 || ACTIVE;
    int fault = ACTIVE && n == 0;
    const uint64_t gold[12] = {fault ? 13 : 9,
      (uint64_t)(fault ? mt_target : mt_ecall), fault ? 0x40001000 : 0,
      0x800, mt_expected_satp, 8, 8, 0, 117, 5, fault ? 0 : 1,
      fault || (!ACTIVE && !VALID) ? 0 : mt_repair_pte};
    for (unsigned j = 0; j < 12; ++j)
      check(used && j == 3 ? mt_records[n][j] & TRAP_MASK : mt_records[n][j],
            used ? gold[j] : UINT64_MAX);
  }
  const uint64_t post[5] = {8,8,0,117,5};
  for (unsigned i = 0; i < 5; ++i) check(mt_post[i],post[i]);
  check(mt_marker,1);
  for (unsigned i = 0; i < 130; ++i)
    check(mt_out[i], ACTIVE && i == 1 ? data_expected(1,0) : 0x5b);
  for (unsigned i = 0; i < 16; ++i) check(mt_mask[i], ACTIVE && i == 0);
  volatile struct vectors *bufs[3] = {&mt_seed,&mt_fault,&mt_result};
  for (unsigned b = 0; b < 3; ++b) {
    for (unsigned i = 0; i < 16; ++i) {
      check(bufs[b]->lo[i],GUARD); check(bufs[b]->hi[i],GUARD);
    }
    for (unsigned r = 0; r < 4; ++r)
      for (unsigned w = 0; w < 32; ++w)
        check(bufs[b]->words[r][w], b == 2 ? result_expected(r,w) :
              b == 1 && !ACTIVE ? GUARD : seed_expected(r,w));
  }
  uint64_t bad = 0;
  for (unsigned p = 0; p < 2; ++p)
    for (unsigned w = 0; w < 512; ++w) {
      uint64_t gold = 0;
      for (unsigned h = 0; h < 4; ++h)
        gold |= (uint64_t)data_expected(p,4*w+h) << (16*h);
      bad |= mt_pages[p][w] ^ gold;
    }
  check(bad,0);
  bad = 0;
  for (unsigned w = 0; w < 512; ++w) {
    bad |= ROOT[w] ^ (w == 1 ? pte(MID,1) : w == 2 ? UINT64_C(0x200000cf) : 0);
    bad |= MID[w] ^ (w == 0 ? pte(LEAF,1) : 0);
    bad |= LEAF[w] ^ (w == 0 ? pte(mt_pages[0],0xc7) :
      w == 1 && (ACTIVE || VALID) ? mt_repair_pte : 0);
  }
  check(bad,0);
  for (unsigned i = 0; i < 16; ++i) {
    check(mt_guard_lo[i],GUARD); check(mt_guard_hi[i],GUARD);
  }
}

int main(void) {
  uint64_t status, mie, mtvec, mepc, mcause, mtval, satp, medeleg, mideleg;
  uint64_t vl, vtype, vstart, vcsr, fcsr, actual;
  READ(mstatus,status); WRITE(mstatus,status & ~UINT64_C(8));
  READ(mie,mie); WRITE(mie,0); READ(mtvec,mtvec); READ(mepc,mepc);
  READ(mcause,mcause); READ(mtval,mtval); READ(satp,satp);
  READ(medeleg,medeleg); READ(mideleg,mideleg);
  READ(vl,vl); READ(vtype,vtype); READ(vstart,vstart); READ(vcsr,vcsr); READ(fcsr,fcsr);
  READ(vlenb,actual); check(actual,128); check(satp,0);
  check((uint64_t)mt_pages & 4095,0);
  WRITE(vstart,0); WRITE(fcsr,117); WRITE(vcsr,5);
  WRITE(medeleg,0); WRITE(mideleg,0); WRITE(mtvec,mt_handler);
  for (unsigned p = 0; p < 5; ++p)
    for (unsigned w = 0; w < 512; ++w) {
      uint64_t value = 0;
      if (p < 2) for (unsigned h = 0; h < 4; ++h)
        value |= (uint64_t)data_expected(p,4*w+h) << (16*h);
      mt_pages[p][w] = value;
    }
  for (unsigned i = 0; i < 16; ++i) {
    mt_guard_lo[i] = mt_guard_hi[i] = GUARD;
    mt_seed.lo[i] = mt_seed.hi[i] = mt_fault.lo[i] = mt_fault.hi[i] =
      mt_result.lo[i] = mt_result.hi[i] = GUARD;
    mt_mask[i] = ACTIVE && i == 0;
  }
  for (unsigned r = 0; r < 4; ++r)
    for (unsigned w = 0; w < 32; ++w) {
      mt_seed.words[r][w] = seed_expected(r,w);
      mt_fault.words[r][w] = mt_result.words[r][w] = GUARD;
    }
  for (unsigned i = 0; i < 130; ++i) mt_out[i] = 0x5b;
  for (unsigned n = 0; n < 2; ++n)
    for (unsigned j = 0; j < 12; ++j) mt_records[n][j] = UINT64_MAX;
  for (unsigned i = 0; i < 5; ++i) mt_post[i] = UINT64_MAX;
  ROOT[1] = pte(MID,1); ROOT[2] = UINT64_C(0x200000cf); MID[0] = pte(LEAF,1);
  LEAF[0] = pte(mt_pages[0],0xc7); mt_repair_pte = pte(mt_pages[1],0xc7);
  if (VALID) LEAF[1] = mt_repair_pte;
  mt_expected_satp = (UINT64_C(8) << 60) | ((uint64_t)ROOT >> 12);
  const uint64_t s_status = (status & ~(TRAP_MASK | UINT64_C(0x7e602))) | 0x2a00;
  asm volatile("fence rw, rw" : : : "memory");
  if (!mt_errors) mt_enter_s(s_status,mt_expected_satp);
  WRITE(satp,satp);
  asm volatile("sfence.vma zero, zero\nfence rw, rw" : : : "memory");
  check_result();
  asm volatile("vsetvl zero, %0, %1" : : "r"(vl), "r"(vtype) : "memory");
  WRITE(vstart,vstart); WRITE(vcsr,vcsr); WRITE(fcsr,fcsr);
  WRITE(mtvec,mtvec); WRITE(mepc,mepc); WRITE(mcause,mcause); WRITE(mtval,mtval);
  WRITE(medeleg,medeleg); WRITE(mideleg,mideleg); WRITE(mie,mie);
#define RESTORE(c) do { READ(c,actual); check(actual,c); } while (0)
  RESTORE(satp); RESTORE(mtvec); RESTORE(mepc); RESTORE(mcause); RESTORE(mtval);
  RESTORE(medeleg); RESTORE(mideleg); RESTORE(mie); RESTORE(vl); RESTORE(vtype);
  RESTORE(vstart); RESTORE(vcsr); RESTORE(fcsr);
#undef RESTORE
  WRITE(mstatus,status & ~UINT64_C(8)); READ(mstatus,actual); check(actual,status & ~UINT64_C(8));
  mt_completed = DONE;
  WRITE(mstatus,status);
  replay_text(mt_errors ? "MT_SV39_FAIL\n" : "MT_SV39_PASS\n");
  return mt_errors != 0;
}
#endif
