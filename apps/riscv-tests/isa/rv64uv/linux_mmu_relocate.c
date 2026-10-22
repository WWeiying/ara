// SPDX-License-Identifier: GPL-2.0-only
// relocate_enable_mmu adapted from Linux 6.19.6 arch/riscv/kernel/head.S.
// Original: Copyright (C) 2012 Regents of the University of California.
// Provenance, oracle and harness differences: verification/cva6/linux_mmu_relocate.md.
#include "vector_macros.h"

#if !defined(__clang__) || defined(vec) || defined(ARA_FPGA) || defined(ARA_LINUX) || defined(__SPIKE__)
#error "Use the non-ZCC scalar-C bare-metal SoC build"
#endif
#define READ(CSR, X) asm volatile("csrr %0, " #CSR : "=r"(X) : : "memory")
#define WRITE(CSR, X) asm volatile("csrw " #CSR ", %0" : : "r"((uint64_t)(X)) : "memory")
#define VA_BASE UINT64_C(0xffffffff80000000)
#define PA_BASE UINT64_C(0x80000000)
#define DELTA (VA_BASE - PA_BASE)
#define MODE (UINT64_C(8) << 60)
#define LEAF_FLAGS (PTE_V | PTE_R | PTE_W | PTE_A | PTE_D)
#define GUARD UINT64_C(0x6b6b6b6b6b6b6b6b)
#define DONE UINT64_C(0x72656c6f63617465)
#define NOBS 13
#define PLANNED_CHECKS 26

static uint64_t trampoline_pg_dir[512] __attribute__((used, aligned(4096)));
static uint64_t final_pg_dir[512] __attribute__((used, aligned(4096)));
static uint64_t code_mid[512] __attribute__((used, aligned(4096)));
static uint64_t data_mid[512] __attribute__((used, aligned(4096)));
static uint64_t data_leaf[512] __attribute__((used, aligned(4096)));
static uint64_t pages[2][512] __attribute__((used, aligned(4096)));
static volatile uint64_t kernel_map_va __attribute__((used));
static volatile uint64_t satp_mode __attribute__((used));
static volatile uint64_t replacement_pte __attribute__((used));
static volatile uint64_t observations[NOBS] __attribute__((used));
static volatile uint64_t trap_info[4] __attribute__((used));
static volatile uint64_t m_frame __attribute__((used));
static volatile uint64_t completed;
static struct { uint64_t id, actual, expected; } failures[32];
static unsigned failure_count;
extern char _start[], __global_pointer$[];
extern char reloc_s_entry[], reloc_s_resume[], reloc_s_ecall[], reloc_m_resume[];
extern char linux_satp_trampoline[], linux_virtual_entry[], linux_satp_final[], linux_debug_park[];

// Preserve the Linux instruction order; symbols/macros use a small test layout.
// Non-XIP, non-shadow-call-stack RV64/Sv39 branch. No added fences in this function.
static void __attribute__((naked, noinline, used, aligned(4))) linux_relocate(uint64_t root_pa) {
  asm volatile(
      ".option push\n.option norvc\n.option norelax\n"
      "la a1, kernel_map_va\nld a1, 0(a1)\nla a2, _start\n"
      "sub a1, a1, a2\nadd ra, ra, a1\n"
      "la a2, linux_virtual_entry\nadd a2, a2, a1\ncsrw stvec, a2\n"
      "srli a2, a0, 12\nla a1, satp_mode\nld a1, 0(a1)\nor a2, a2, a1\n"
      "la a0, trampoline_pg_dir\nsrli a0, a0, 12\nor a0, a0, a1\n"
      "sfence.vma\n.globl linux_satp_trampoline\nlinux_satp_trampoline: csrw satp, a0\n"
      ".balign 4\n.globl linux_virtual_entry\nlinux_virtual_entry:\n"
      "la a0, linux_debug_park\ncsrw stvec, a0\n"
      "la gp, __global_pointer$\n"
      ".globl linux_satp_final\nlinux_satp_final: csrw satp, a2\nsfence.vma\nret\n"
      ".option pop\n");
}

// Unlike Linux's infinite debug park, return an unexpected trap to the checker.
static void __attribute__((naked, used, aligned(4))) debug_park(void) {
  asm volatile(".globl linux_debug_park\nlinux_debug_park: ecall\nunimp\n");
}

static void __attribute__((naked, used, aligned(4))) m_handler(void) {
  asm volatile(
      "la t0, trap_info\ncsrr t1, mcause\nsd t1, 0(t0)\n"
      "csrr t1, mepc\nsd t1, 8(t0)\ncsrr t1, mtval\nsd t1, 16(t0)\n"
      "csrr t1, mstatus\nsd t1, 24(t0)\n"
      "li t2, 0x21888\nnot t2, t2\nand t1, t1, t2\n"
      "li t2, 0x1800\nor t1, t1, t2\ncsrw mstatus, t1\n"
      "la t0, reloc_m_resume\ncsrw mepc, t0\nmret\n");
}

// S code uses only caller-saved GPRs and gp. It never accesses the unmapped S stack.
static void __attribute__((naked, noinline, used)) enter_s(uint64_t status) {
  asm volatile(
      "addi sp, sp, -16\nsd ra, 0(sp)\nsd gp, 8(sp)\n"
      "la t0, m_frame\nsd sp, 0(t0)\n"
      "la t0, m_handler\ncsrw mtvec, t0\ncsrw mstatus, a0\n"
      "la t0, reloc_s_entry\ncsrw mepc, t0\nmret\n"
      ".globl reloc_s_entry\nreloc_s_entry:\n"
      "la a0, final_pg_dir\ncall linux_relocate\n"
      ".globl reloc_s_resume\nreloc_s_resume:\n"
      "la t0, observations\n"
      "csrr t1, satp\nsd t1, 0(t0)\ncsrr t1, scause\nsd t1, 8(t0)\n"
      "csrr t1, sepc\nsd t1, 16(t0)\ncsrr t1, stval\nsd t1, 24(t0)\n"
      "la t1, reloc_s_resume\nsd t1, 32(t0)\nsd gp, 40(t0)\n"
      "li t2, 0x40000000\nld t1, 0(t2)\nsd t1, 48(t0)\n"
      "la t3, data_leaf\nld t1, 0(t3)\nsd t1, 88(t0)\n"
      "la t1, replacement_pte\nld t1, 0(t1)\nsd t1, 0(t3)\nsd t1, 96(t0)\n"
      "fence rw, rw\nsfence.vma t2, zero\n"
      "ld t1, 0(t2)\nsd t1, 56(t0)\n"
      "li t1, 0x13579bdf2468ace0\nsd t1, 8(t2)\nfence rw, rw\n"
      "ld t1, 8(t2)\nsd t1, 64(t0)\ncsrr t1, stvec\nsd t1, 72(t0)\n"
      "li t1, 1\nsd t1, 80(t0)\nfence rw, rw\n"
      ".balign 4\n.globl reloc_s_ecall\nreloc_s_ecall: ecall\nunimp\n"
      ".globl reloc_m_resume\nreloc_m_resume:\n"
      "la t0, m_frame\nld sp, 0(t0)\nld ra, 0(sp)\nld gp, 8(sp)\naddi sp, sp, 16\nret\n");
}

static uint64_t pointer_pte(const void *p) { return ((uint64_t)p >> 12 << 10) | PTE_V; }
static uint64_t leaf_pte(const void *p) { return ((uint64_t)p >> 12 << 10) | LEAF_FLAGS; }
static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    if (failure_count < 32) {
      failures[failure_count].id = id;
      failures[failure_count].actual = actual;
      failures[failure_count++].expected = expected;
    }
    ++num_failed;
  }
}

void rvtest_init(void) {
  uint64_t status, mie, medeleg, mideleg, mtvec, mepc, mcause, mtval, satp;
  uint64_t stvec, sepc, scause, stval, actual;
  INIT_CHECK();
  asm volatile("csrrci %0, mstatus, 8" : "=r"(status) : : "memory");
  READ(mie, mie); WRITE(mie, 0);
  READ(medeleg, medeleg); READ(mideleg, mideleg);
  READ(mtvec, mtvec); READ(mepc, mepc); READ(mcause, mcause); READ(mtval, mtval);
  READ(satp, satp); READ(stvec, stvec); READ(sepc, sepc); READ(scause, scause); READ(stval, stval);
  WRITE(mideleg, 0); WRITE(medeleg, UINT64_C(1) << 12);
  WRITE(scause, 0); WRITE(sepc, 0); WRITE(stval, 0);
  for (unsigned i = 0; i < 512; ++i) {
    trampoline_pg_dir[i] = final_pg_dir[i] = code_mid[i] = data_mid[i] = data_leaf[i] = 0;
    pages[0][i] = pages[1][i] = GUARD;
  }
  for (unsigned i = 0; i < NOBS; ++i) observations[i] = UINT64_MAX;
  for (unsigned i = 0; i < 4; ++i) trap_info[i] = UINT64_MAX;
  kernel_map_va = VA_BASE; satp_mode = MODE;
  trampoline_pg_dir[510] = final_pg_dir[510] = pointer_pte(code_mid);
  code_mid[0] = (PA_BASE >> 12 << 10) | LEAF_FLAGS | PTE_X;
  final_pg_dir[1] = pointer_pte(data_mid);
  data_mid[0] = pointer_pte(data_leaf);
  data_leaf[0] = leaf_pte(pages[0]); replacement_pte = leaf_pte(pages[1]);
  pages[0][0] = UINT64_C(0x1122334455667788);
  pages[1][0] = UINT64_C(0x8877665544332211);
  check(1, satp, 0); check(2, (uint64_t)_start, PA_BASE);
  check(3, (uint64_t)pages >= PA_BASE && (uint64_t)(pages + 2) <= PA_BASE + 0x200000, 1);
  READ(medeleg, actual); check(4, actual, UINT64_C(1) << 12);
  asm volatile("fence rw, rw\nsfence.vma" : : : "memory");
  const uint64_t s_status = (status & ~(uint64_t)(MSTATUS_MPP | MSTATUS_MPIE |
      MSTATUS_MIE | MSTATUS_SIE | MSTATUS_MPRV | MSTATUS_MPV | MSTATUS_TVM |
      MSTATUS_SUM | MSTATUS_MXR)) | 0x800;
  if (!num_failed) enter_s(s_status);
  WRITE(satp, satp); asm volatile("sfence.vma\nfence rw, rw" : : : "memory");
  uint64_t expected[NOBS] = {
    MODE | ((uint64_t)final_pg_dir >> 12), 12, (uint64_t)linux_virtual_entry,
    (uint64_t)linux_virtual_entry, (uint64_t)reloc_s_resume + DELTA,
    (uint64_t)__global_pointer$ + DELTA, UINT64_C(0x1122334455667788),
    UINT64_C(0x8877665544332211), UINT64_C(0x13579bdf2468ace0),
    (uint64_t)linux_debug_park + DELTA, 1, leaf_pte(pages[0]), leaf_pte(pages[1])
  };
  for (unsigned i = 0; i < NOBS; ++i) check(10 + i, observations[i], expected[i]);
  check(30, trap_info[0], 9); check(31, trap_info[1], (uint64_t)reloc_s_ecall + DELTA);
  check(32, trap_info[2], 0); check(33, trap_info[3] & MSTATUS_MPP, 0x800);
  check(34, pages[0][1], GUARD); check(35, pages[1][1], UINT64_C(0x13579bdf2468ace0));
  check(36, pages[0][0], UINT64_C(0x1122334455667788));
  check(37, pages[1][0], UINT64_C(0x8877665544332211));
  check(38, data_leaf[0], leaf_pte(pages[1]));
  WRITE(stvec, stvec); WRITE(sepc, sepc); WRITE(scause, scause); WRITE(stval, stval);
  WRITE(mtvec, mtvec); WRITE(mepc, mepc); WRITE(mcause, mcause); WRITE(mtval, mtval);
  WRITE(medeleg, medeleg); WRITE(mideleg, mideleg); WRITE(mie, mie);
  completed = DONE; WRITE(mstatus, status);
}

int main(void) {
  for (unsigned i = 0; i < NOBS; ++i) printf("RELOC_OBS %u %016lx\n", i, observations[i]);
  for (unsigned i = 0; i < 4; ++i) printf("RELOC_TRAP %u %016lx\n", i, trap_info[i]);
  printf("RELOC_MEMORY %016lx %016lx\n", pages[0][1], pages[1][1]);
  for (unsigned i = 0; i < failure_count; ++i)
    printf("Failure #%lu: got %016lx expected %016lx\n", failures[i].id, failures[i].actual, failures[i].expected);
  printf("linux_mmu_relocate: checks=%d failures=%d\n", test_case, num_failed);
  if (completed != DONE || num_failed || test_case != PLANNED_CHECKS) {
    printf("FAIL: linux_mmu_relocate\n"); return 1;
  }
  printf("PASSED: linux_mmu_relocate\n"); return 0;
}
