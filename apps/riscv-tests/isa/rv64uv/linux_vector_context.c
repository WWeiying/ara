// SPDX-License-Identifier: GPL-2.0-or-later
// Standard-RVV path adapted from Linux 6.19.6 arch/riscv/include/asm/vector.h.
// Original vector support: Copyright (C) 2020 SiFive.
// Provenance and harness differences: verification/cva6/linux_vector_context.md.
#include "vector_macros.h"

#if !defined(__clang__) || defined(vec) || defined(ARA_FPGA) || defined(ARA_LINUX) || defined(__SPIKE__)
#error "Use the non-ZCC scalar-C bare-metal SoC build (vec=0)"
#endif
#if NR_LANES != 4 || VLEN != 1024
#error "This test targets config=default: 4 lanes, VLEN=1024"
#endif

#define READ(CSR, X) asm volatile("csrr %0, " #CSR : "=r"(X) : : "memory")
#define WRITE(CSR, X) asm volatile("csrw " #CSR ", %0" : : "r"((uint64_t)(X)) : "memory")
#define WORDS (32 * VLEN / 64)
#define ROUNDS 6
#define ROUND_CHECKS (2 + 5 + 5 + 2 * WORDS + 32)
#define PLANNED_CHECKS (7 + ROUNDS * ROUND_CHECKS)
#define DONE UINT64_C(0x76637478646f6e65)
#define GUARD UINT64_C(0xbadc0ffe5a1a5a1a)

struct vstate { uint64_t vstart, vtype, vl, vcsr, vlenb; };
struct buffer {
  uint64_t before[8], data[WORDS], after[8];
} __attribute__((aligned(64)));
static struct buffer inputs[4], saved, physical;
static const struct vstate configs[4] = {
  {3, 0x10, 17, 7, 128}, // e32,m1,tu,mu
  {1, 0xcf, 19, 2, 128}, // e16,mf2,ta,ma
  {0, 0x19, 0, 5, 128},  // e64,m2,tu,mu; zero active elements
  {0, UINT64_C(1) << 63, 0, 0, 128} // VILL, still owns physical registers
};
static const unsigned schedule[ROUNDS] = {0, 1, 0, 2, 3, 1};
static unsigned rounds_done;
static volatile uint64_t completed, phase __attribute__((used));
static volatile uint64_t trap_info[4] __attribute__((used));
static volatile uint64_t m_frame __attribute__((used));
static unsigned char trap_stack[256] __attribute__((used, aligned(16)));
static struct { uint64_t id, actual, expected; } failures[32];
static unsigned failure_count;
extern char vector_context_s_entry[], vector_context_ecall[], vector_context_m_resume[];

// Fixed a0/a1 bindings replace kernel compiler operands and struct offsets.
// The four m8 accesses and their ordering are the Linux standard-RVV sequence.
static void __attribute__((naked, noinline, used))
linux_save(struct vstate *dest, void *datap) {
  asm volatile(
      "li t1, 0x600\ncsrs sstatus, t1\n"
      "csrr t0, vstart\nsd t0, 0(a0)\n"
      "csrr t0, vtype\nsd t0, 8(a0)\n"
      "csrr t0, vl\nsd t0, 16(a0)\n"
      "csrr t0, vcsr\nsd t0, 24(a0)\n"
      "csrr t0, vlenb\nsd t0, 32(a0)\n"
      "vsetvli t0, zero, e8, m8, ta, ma\n"
      "vse8.v v0, (a1)\nadd a1, a1, t0\n"
      "vse8.v v8, (a1)\nadd a1, a1, t0\n"
      "vse8.v v16, (a1)\nadd a1, a1, t0\n"
      "vse8.v v24, (a1)\n"
      "csrc sstatus, t1\nret\n");
}

static void __attribute__((naked, noinline, used))
linux_restore(const struct vstate *src, const void *datap) {
  asm volatile(
      "li t1, 0x600\ncsrs sstatus, t1\n"
      "vsetvli t0, zero, e8, m8, ta, ma\n"
      "vle8.v v0, (a1)\nadd a1, a1, t0\n"
      "vle8.v v8, (a1)\nadd a1, a1, t0\n"
      "vle8.v v16, (a1)\nadd a1, a1, t0\n"
      "vle8.v v24, (a1)\n"
      "ld t0, 16(a0)\nld t2, 8(a0)\nvsetvl zero, t0, t2\n"
      "ld t0, 0(a0)\ncsrw vstart, t0\n"
      "ld t0, 24(a0)\ncsrw vcsr, t0\n"
      "csrc sstatus, t1\nret\n");
}

#define DUMP_REG(N) "vs1r.v v" #N ", (a0)\naddi a0, a0, 128\n"
// Independent oracle path: each physical register, not another m8 save loop.
static void __attribute__((naked, noinline, used)) dump_physical(void *datap) {
  asm volatile(
      "csrw vstart, zero\n"
      DUMP_REG(0) DUMP_REG(1) DUMP_REG(2) DUMP_REG(3)
      DUMP_REG(4) DUMP_REG(5) DUMP_REG(6) DUMP_REG(7)
      DUMP_REG(8) DUMP_REG(9) DUMP_REG(10) DUMP_REG(11)
      DUMP_REG(12) DUMP_REG(13) DUMP_REG(14) DUMP_REG(15)
      DUMP_REG(16) DUMP_REG(17) DUMP_REG(18) DUMP_REG(19)
      DUMP_REG(20) DUMP_REG(21) DUMP_REG(22) DUMP_REG(23)
      DUMP_REG(24) DUMP_REG(25) DUMP_REG(26) DUMP_REG(27)
      DUMP_REG(28) DUMP_REG(29) DUMP_REG(30) DUMP_REG(31)
      "csrr zero, vl\nfence rw, rw\nret\n");
}

static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    if (failure_count < 32) {
      failures[failure_count].id = id;
      failures[failure_count].actual = actual;
      failures[failure_count].expected = expected;
      ++failure_count;
    }
    ++num_failed;
  }
}

static void check_state(unsigned id, const struct vstate *a, const struct vstate *b) {
  check(id, a->vstart, b->vstart);
  check(id + 1, a->vtype, b->vtype);
  check(id + 2, a->vl, b->vl);
  check(id + 3, a->vcsr, b->vcsr);
  check(id + 4, a->vlenb, b->vlenb);
}

static uint64_t pattern(unsigned context, unsigned word) {
  return UINT64_C(0x132547698badcfe0) ^
      ((uint64_t)(context + 1) * UINT64_C(0x1122334455667788)) ^
      ((uint64_t)(word + 1) * UINT64_C(0x0103070b131d2b3d));
}

static void __attribute__((noinline, used)) s_test(void) {
  for (unsigned r = 0; r < ROUNDS; ++r) {
    unsigned c = schedule[r], id = 100 + r * 2000;
    uint64_t status;
    struct vstate observed, extracted;
    phase = r + 1;
    for (unsigned i = 0; i < WORDS; ++i) {
      saved.data[i] = ~pattern(c, i);
      physical.data[i] = ~pattern(c, i);
    }
    asm volatile("fence rw, rw" : : : "memory");
    linux_restore(&configs[c], inputs[c].data);
    READ(sstatus, status); check(id++, status & MSTATUS_VS, 0);
    asm volatile("csrs sstatus, %0" : : "r"((uint64_t)MSTATUS_VS) : "memory");
    READ(vstart, observed.vstart); READ(vtype, observed.vtype);
    READ(vl, observed.vl); READ(vcsr, observed.vcsr); READ(vlenb, observed.vlenb);
    check_state(id, &observed, &configs[c]); id += 5;
    linux_save(&extracted, saved.data);
    READ(sstatus, status); check(id++, status & MSTATUS_VS, 0);
    asm volatile("csrs sstatus, %0" : : "r"((uint64_t)MSTATUS_VS) : "memory");
    check_state(id, &extracted, &configs[c]); id += 5;
    dump_physical(physical.data);
    for (unsigned i = 0; i < WORDS; ++i) {
      check(id++, saved.data[i], pattern(c, i));
      check(id++, physical.data[i], pattern(c, i));
    }
    for (unsigned i = 0; i < 8; ++i) {
      check(id++, saved.before[i], GUARD); check(id++, saved.after[i], GUARD);
      check(id++, physical.before[i], GUARD); check(id++, physical.after[i], GUARD);
    }
    ++rounds_done;
  }
}

// Any S exception exits to a known M frame; never skip a faulting instruction.
static void __attribute__((naked, used, aligned(4))) m_handler(void) {
  asm volatile(
      "csrrw sp, mscratch, sp\nla t0, trap_info\n"
      "csrr t1, mcause\nsd t1, 0(t0)\ncsrr t1, mepc\nsd t1, 8(t0)\n"
      "csrr t1, mtval\nsd t1, 16(t0)\ncsrr t1, mstatus\nsd t1, 24(t0)\n"
      "li t2, 0x21888\nnot t2, t2\nand t1, t1, t2\n"
      "li t2, 0x1800\nor t1, t1, t2\ncsrw mstatus, t1\n"
      "la t0, vector_context_m_resume\ncsrw mepc, t0\nmret\n");
}

// Save all callee-saved GPRs, including unexpected exceptions inside S C code.
static void __attribute__((naked, noinline, used)) enter_s(uint64_t status) {
  asm volatile(
      "addi sp, sp, -112\nsd ra, 0(sp)\nsd s0, 8(sp)\nsd s1, 16(sp)\n"
      "sd s2, 24(sp)\nsd s3, 32(sp)\nsd s4, 40(sp)\nsd s5, 48(sp)\n"
      "sd s6, 56(sp)\nsd s7, 64(sp)\nsd s8, 72(sp)\nsd s9, 80(sp)\n"
      "sd s10, 88(sp)\nsd s11, 96(sp)\nla t0, m_frame\nsd sp, 0(t0)\n"
      "la t0, trap_stack\naddi t0, t0, 256\ncsrw mscratch, t0\n"
      "la t0, m_handler\ncsrw mtvec, t0\ncsrw mstatus, a0\n"
      "la t0, vector_context_s_entry\ncsrw mepc, t0\nmret\n"
      ".globl vector_context_s_entry\nvector_context_s_entry:\n"
      "call s_test\n.balign 4\n.globl vector_context_ecall\nvector_context_ecall: ecall\nunimp\n"
      ".globl vector_context_m_resume\nvector_context_m_resume:\n"
      "la t0, m_frame\nld sp, 0(t0)\n"
      "ld ra, 0(sp)\nld s0, 8(sp)\nld s1, 16(sp)\nld s2, 24(sp)\n"
      "ld s3, 32(sp)\nld s4, 40(sp)\nld s5, 48(sp)\nld s6, 56(sp)\n"
      "ld s7, 64(sp)\nld s8, 72(sp)\nld s9, 80(sp)\nld s10, 88(sp)\n"
      "ld s11, 96(sp)\naddi sp, sp, 112\nret\n");
}

void rvtest_init(void) {
  uint64_t status, mie, medeleg, mideleg, mtvec, mepc, mcause, mtval, mscratch;
  uint64_t satp, old_vl, old_vtype, old_vstart, old_vcsr, vlenb;
  READ(mstatus, status); WRITE(mstatus, status & ~MSTATUS_MIE);
  READ(mie, mie); WRITE(mie, 0);
  READ(medeleg, medeleg); READ(mideleg, mideleg);
  READ(mtvec, mtvec); READ(mepc, mepc); READ(mcause, mcause);
  READ(mtval, mtval); READ(mscratch, mscratch); READ(satp, satp);
  asm volatile("csrs mstatus, %0" : : "r"((uint64_t)MSTATUS_VS) : "memory");
  READ(vl, old_vl); READ(vtype, old_vtype); READ(vstart, old_vstart);
  READ(vcsr, old_vcsr); READ(vlenb, vlenb);
  WRITE(medeleg, 0); WRITE(mideleg, 0);
  test_case = num_failed = 0;
  check(1, satp, 0); check(2, vlenb, 128);
  for (unsigned c = 0; c < 4; ++c)
    for (unsigned i = 0; i < WORDS; ++i) inputs[c].data[i] = pattern(c, i);
  for (unsigned i = 0; i < 8; ++i)
    saved.before[i] = saved.after[i] = physical.before[i] = physical.after[i] = GUARD;
  for (unsigned i = 0; i < 4; ++i) trap_info[i] = UINT64_MAX;
  const uint64_t s_status = (status & ~(uint64_t)(MSTATUS_MPP | MSTATUS_MPIE |
      MSTATUS_MIE | MSTATUS_SIE | MSTATUS_MPRV | MSTATUS_MPV | MSTATUS_TVM |
      MSTATUS_SUM | MSTATUS_MXR | MSTATUS_VS)) | 0x800;
  asm volatile("fence rw, rw" : : : "memory");
  if (!num_failed) enter_s(s_status);
  check(3, trap_info[0], 9);
  check(4, trap_info[1], (uint64_t)vector_context_ecall);
  check(5, trap_info[2], 0);
  check(6, trap_info[3] & MSTATUS_MPP, 0x800);
  check(7, rounds_done, ROUNDS);
  asm volatile("csrs mstatus, %0" : : "r"((uint64_t)MSTATUS_VS) : "memory");
  asm volatile("vsetvl zero, %0, %1" : : "r"(old_vl), "r"(old_vtype) : "memory");
  WRITE(vcsr, old_vcsr); WRITE(vstart, old_vstart);
  WRITE(mtvec, mtvec); WRITE(mepc, mepc); WRITE(mcause, mcause); WRITE(mtval, mtval);
  WRITE(mscratch, mscratch); WRITE(medeleg, medeleg); WRITE(mideleg, mideleg);
  WRITE(mie, mie); completed = DONE; WRITE(mstatus, status);
}

int main(void) {
  for (unsigned i = 0; i < failure_count; ++i)
    printf("Failure #%lu: got %016lx expected %016lx\n",
           failures[i].id, failures[i].actual, failures[i].expected);
  printf("linux_vector_context: rounds=%u checks=%d phase=%lu cause=%lx epc=%lx tval=%lx\n",
         rounds_done, test_case, phase, trap_info[0], trap_info[1], trap_info[2]);
  if (completed != DONE || num_failed || test_case != PLANNED_CHECKS) {
    printf("FAIL: linux_vector_context failures=%d planned=%d\n", num_failed, PLANNED_CHECKS);
    return 1;
  }
  printf("PASSED: linux_vector_context\n");
  return 0;
}
