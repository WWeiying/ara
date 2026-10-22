// Actual-SoC Linux prerequisite checks; see verification/cva6/linux_state_prereq.md.
#include "vector_macros.h"

#define VS_INITIAL (MSTATUS_VS & (MSTATUS_VS >> 1))
#define VS_CLEAN (VS_INITIAL << 1)
#define FS_INITIAL (MSTATUS_FS & (MSTATUS_FS >> 1))
#define STATE_MASK ((uint64_t)(MSTATUS_VS | MSTATUS_FS | MSTATUS_XS) | MSTATUS_SD)
#define MACHINE_STATE_MASK (MSTATUS_MPP | MSTATUS_MPIE | MSTATUS_MIE)
#define FAILURE_CAPACITY 256u
#define PLANNED_CHECKS 165
#define DONE UINT64_C(0x707265726571)

#if FAILURE_CAPACITY < PLANNED_CHECKS
#error "Failure log must hold every planned check"
#endif

#define READ_CSR(csr, value) \
  asm volatile("csrr %0, " #csr : "=r"(value) : : "memory")
#define WRITE_CSR(csr, value) \
  asm volatile("csrw " #csr ", %0" : : "r"((uint64_t)(value)) : "memory")

static volatile uint64_t completed;
static struct {
  uint64_t id, actual, expected;
} failures[FAILURE_CAPACITY];
static unsigned failure_count, failure_overflow;
static volatile uint64_t off_trap[3] __attribute__((used));
extern char prereq_vs_off[], prereq_vs_resume[];

// Only installed around prereq_vs_off, with interrupts masked. Preserve every
// GPR touched and recover at a known label, never blindly skip an unknown PC.
static void __attribute__((naked, used, aligned(4))) vs_off_handler(void) {
  asm volatile("addi sp, sp, -16\n"
               "sd t0, 0(sp)\n"
               "sd t1, 8(sp)\n"
               "la t1, off_trap\n"
               "ld t0, 0(t1)\n"
               "addi t0, t0, 1\n"
               "sd t0, 0(t1)\n"
               "csrr t0, mcause\n"
               "sd t0, 8(t1)\n"
               "csrr t0, mepc\n"
               "sd t0, 16(t1)\n"
               "la t0, prereq_vs_resume\n"
               "csrw mepc, t0\n"
               "ld t0, 0(sp)\n"
               "ld t1, 8(sp)\n"
               "addi sp, sp, 16\n"
               "mret\n");
}

// Unlike XCMP, do not return on a mismatch: cleanup must always run.
static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    if (failure_count < FAILURE_CAPACITY) {
      failures[failure_count].id = id;
      failures[failure_count].actual = actual;
      failures[failure_count].expected = expected;
      ++failure_count;
    } else
      ++failure_overflow;
    ++num_failed;
  }
}

static void check_state(unsigned id, uint64_t m, uint64_t s, uint64_t expected) {
  check(id, m & STATE_MASK, expected);
  check(id + 1, s & STATE_MASK, expected);
}

static void set_state(unsigned id, uint64_t base, uint64_t fields,
                      uint64_t expected) {
  uint64_t m, s;
  asm volatile("csrw mstatus, %2\ncsrr %0, mstatus\ncsrr %1, sstatus"
               : "=&r"(m), "=r"(s) : "r"(base | fields) : "memory");
  check_state(id, m, s, expected);
}

static void test_vs(uint64_t base, uint64_t old_mtvec) {
  uint64_t m, s, vl, vtype;
  set_state(1, base, 0, 0);
  set_state(3, base, VS_INITIAL, VS_INITIAL);
  asm volatile("vsetivli %0, 1, e8, m1, tu, mu\n"
               "csrr %1, mstatus\ncsrr %2, sstatus"
               : "=&r"(vl), "=&r"(m), "=r"(s) : : "memory");
  check_state(5, m, s, MSTATUS_VS | MSTATUS_SD);
  check(7, vl, 1);
  set_state(8, base, VS_CLEAN, VS_CLEAN);
  asm volatile("vsetivli %0, 2, e16, m1, tu, mu\n"
               "csrr %1, mstatus\ncsrr %2, sstatus"
               : "=&r"(vl), "=&r"(m), "=r"(s) : : "memory");
  check_state(10, m, s, MSTATUS_VS | MSTATUS_SD);
  check(12, vl, 2);
  set_state(13, base, 0, 0);
  set_state(15, base, MSTATUS_VS, MSTATUS_VS | MSTATUS_SD);
  set_state(17, base, 0, 0);

  off_trap[0] = off_trap[1] = off_trap[2] = 0;
  WRITE_CSR(mtvec, vs_off_handler);
  asm volatile(".balign 4\n"
               "prereq_vs_off: vsetivli zero, 3, e32, m1, tu, mu\n"
               "prereq_vs_resume: csrr %0, mstatus\n"
               "csrr %1, sstatus"
               : "=&r"(m), "=r"(s) : : "memory");
  WRITE_CSR(mtvec, old_mtvec);
  check(19, off_trap[0], 1);
  check(20, off_trap[1], CAUSE_ILLEGAL_INSTRUCTION);
  check(21, off_trap[2], (uint64_t)prereq_vs_off);
  check_state(22, m, s, 0);
  WRITE_CSR(mstatus, base | VS_INITIAL);
  READ_CSR(vtype, vtype);
  READ_CSR(vl, vl);
  check(24, vtype, 8); // e16, m1, tu, mu; rejected instruction changed nothing.
  check(25, vl, 2);
  set_state(26, base, MSTATUS_FS, MSTATUS_FS | MSTATUS_SD);
}

// Keep the CSR RMW and both post-write snapshots in one scalar-only block.
#define SSTATUS_CASE(ID, OP, BITS, BEFORE, AFTER)                            \
  do {                                                                      \
    uint64_t old, m, s;                                                      \
    asm volatile(OP " %0, sstatus, %3\n"                                     \
                 "csrr %1, mstatus\ncsrr %2, sstatus"                         \
                 : "=&r"(old), "=&r"(m), "=r"(s)                            \
                 : "r"((uint64_t)(BITS)) : "memory");                       \
    check(ID, old & STATE_MASK, BEFORE);                                     \
    check_state((ID) + 1, m, s, AFTER);                                      \
    check((ID) + 3, m & MACHINE_STATE_MASK, MSTATUS_MPP | MSTATUS_MPIE);       \
  } while (0)

static void test_sstatus(uint64_t base) {
  // FS=XS=Off isolates VS -> SD. SSTATUS must preserve these M-only sentinels.
  WRITE_CSR(mstatus, base | MSTATUS_MPP | MSTATUS_MPIE);
  SSTATUS_CASE(40, "csrrw", VS_INITIAL | MSTATUS_SD, 0, VS_INITIAL);
  SSTATUS_CASE(44, "csrrs", VS_CLEAN, VS_INITIAL, MSTATUS_VS | MSTATUS_SD);
  SSTATUS_CASE(48, "csrrc", VS_INITIAL, MSTATUS_VS | MSTATUS_SD, VS_CLEAN);
  SSTATUS_CASE(52, "csrrc", VS_CLEAN, VS_CLEAN, 0);
  SSTATUS_CASE(56, "csrrw", VS_CLEAN, 0, VS_CLEAN);
  SSTATUS_CASE(60, "csrrs", VS_INITIAL, VS_CLEAN, MSTATUS_VS | MSTATUS_SD);
  SSTATUS_CASE(64, "csrrc", MSTATUS_SD, MSTATUS_VS | MSTATUS_SD,
               MSTATUS_VS | MSTATUS_SD);
  SSTATUS_CASE(68, "csrrw", 0, MSTATUS_VS | MSTATUS_SD, 0);
  WRITE_CSR(mstatus, base);
}

// Raw immediate encodings deliberately bypass the assembler's vtype checks.
// Every invalid configuration must discard its otherwise legal low byte.
#define VTYPE_CASE(ID, CONFIG, BITS)                                         \
  do {                                                                      \
    uint64_t bad_type, bad_vl, good_type, good_vl;                             \
    asm volatile(CONFIG "\ncsrr %0, vtype\ncsrr %1, vl\n"                    \
                 "vsetivli zero, 3, e32, m2, ta, ma\n"                        \
                 "csrr %2, vtype\ncsrr %3, vl"                               \
                 : "=&r"(bad_type), "=&r"(bad_vl), "=&r"(good_type),         \
                   "=r"(good_vl)                                           \
                 : "r"(UINT64_C(3)), "r"((uint64_t)(BITS) | UINT64_C(0xcf))  \
                 : "memory");                                              \
    check(ID, bad_type, UINT64_C(0x8000000000000000));                         \
    check((ID) + 1, bad_vl, 0);                                              \
    check((ID) + 2, good_type, UINT64_C(0xd1));                                \
    check((ID) + 3, good_vl, 3);                                             \
  } while (0)

static void test_vtype(void) {
  uint64_t type, vl;
  asm volatile("vsetivli zero, 3, e16, mf2, ta, ma\n"
               "csrr %0, vtype\ncsrr %1, vl"
               : "=&r"(type), "=r"(vl) : : "memory");
  check(400, type, UINT64_C(0xcf));
  check(401, vl, 3);
  VTYPE_CASE(402, "vsetvl zero, %4, %5", UINT64_C(1) << 8);
  VTYPE_CASE(406, "vsetvl zero, %4, %5", UINT64_C(1) << 9);
  VTYPE_CASE(410, "vsetvl zero, %4, %5", UINT64_C(1) << 10);
  VTYPE_CASE(414, "vsetvl zero, %4, %5", UINT64_C(1) << 31);
  VTYPE_CASE(418, "vsetvl zero, %4, %5", UINT64_C(1) << 62);
  VTYPE_CASE(422, "vsetvl zero, %4, %5", UINT64_C(1) << 63);
  VTYPE_CASE(426, ".insn i 0x57, 7, x0, %4, 0x1cf", 0);
  VTYPE_CASE(430, ".insn i 0x57, 7, x0, %4, 0x2cf", 0);
  VTYPE_CASE(434, ".insn i 0x57, 7, x0, %4, 0x4cf", 0);
  VTYPE_CASE(438, ".word 0xdcf1f057", 0); // vsetivli AVL=3, vtype=0x1cf.
  VTYPE_CASE(442, ".word 0xecf1f057", 0); // vsetivli AVL=3, vtype=0x2cf.
}

// FMV.D.X transports raw FLEN=64 bits, not a C numeric conversion or a
// narrow move/load that would repair the malformed box. Inspect all 64 result
// bits, including the output box. Full fcsr comparison also checks frm=RNE.
#define FP_CASE(ID, INSN, A, B, EXPECTED, FLAGS)                              \
  do {                                                                      \
    uint64_t actual, fcsr;                                                   \
    asm volatile("fmv.d.x ft0, %2\nfmv.d.x ft1, %3\n"                         \
                 "csrw fcsr, zero\n" INSN "\n"                               \
                 "fmv.x.d %0, ft2\ncsrr %1, fcsr"                            \
                 : "=&r"(actual), "=r"(fcsr)                                \
                 : "r"((uint64_t)(A)), "r"((uint64_t)(B))                    \
                 : "ft0", "ft1", "ft2", "memory");                          \
    check(ID, actual, EXPECTED);                                             \
    check((ID) + 1, fcsr, FLAGS);                                            \
  } while (0)

#define FP_FORMAT(ID, FMT, ONE, FOUR, TWO, NEG, SNAN, QNAN, INF, ZERO, HOLE)   \
  do {                                                                      \
    FP_CASE(ID, "fdiv." FMT " ft2, ft0, ft1, rne", FOUR, ONE, FOUR, 0);       \
    FP_CASE(ID + 2, "fdiv." FMT " ft2, ft0, ft1, rne",                        \
            FOUR & ~UINT64_C(0x8000000000000000), ONE, QNAN, 0);              \
    FP_CASE(ID + 4, "fdiv." FMT " ft2, ft0, ft1, rne",                        \
            ONE, ZERO & ~(HOLE), QNAN, 0);                                   \
    FP_CASE(ID + 6, "fdiv." FMT " ft2, ft0, ft1, rne", ONE, ZERO, INF, 8);    \
    FP_CASE(ID + 8, "fdiv." FMT " ft2, ft0, ft1, rne",                        \
            SNAN & ~(HOLE), ONE, QNAN, 0);                                   \
    FP_CASE(ID + 10, "fdiv." FMT " ft2, ft0, ft1, rne", SNAN, ONE, QNAN, 16);\
    FP_CASE(ID + 12, "fsqrt." FMT " ft2, ft0, rne", FOUR, 0, TWO, 0);         \
    FP_CASE(ID + 14, "fsqrt." FMT " ft2, ft0, rne",                           \
            NEG & ~UINT64_C(0x8000000000000000), 0, QNAN, 0);                 \
    FP_CASE(ID + 16, "fsqrt." FMT " ft2, ft0, rne", NEG, 0, QNAN, 16);        \
    FP_CASE(ID + 18, "fsqrt." FMT " ft2, ft0, rne",                           \
            SNAN & ~(HOLE), 0, QNAN, 0);                                     \
    FP_CASE(ID + 20, "fsqrt." FMT " ft2, ft0, rne", SNAN, 0, QNAN, 16);       \
    FP_CASE(ID + 22, "fsqrt." FMT " ft2, ft0, rne", QNAN | 1, 0, QNAN, 0);   \
  } while (0)

static void test_nanbox(void) {
  FP_FORMAT(100, "h", UINT64_C(0xffffffffffff3c00), UINT64_C(0xffffffffffff4400),
            UINT64_C(0xffffffffffff4000), UINT64_C(0xffffffffffffc400),
            UINT64_C(0xffffffffffff7c01), UINT64_C(0xffffffffffff7e00),
            UINT64_C(0xffffffffffff7c00), UINT64_C(0xffffffffffff0000),
            UINT64_C(0x0000000000010000));
  FP_FORMAT(150, "s", UINT64_C(0xffffffff3f800000), UINT64_C(0xffffffff40800000),
            UINT64_C(0xffffffff40000000), UINT64_C(0xffffffffc0800000),
            UINT64_C(0xffffffff7f800001), UINT64_C(0xffffffff7fc00000),
            UINT64_C(0xffffffff7f800000), UINT64_C(0xffffffff00000000),
            UINT64_C(0x0000000100000000));
  // D has no upper boxing bits: these are ordinary full-width operands.
  FP_CASE(200, "fdiv.d ft2, ft0, ft1, rne", UINT64_C(0x4010000000000000),
          UINT64_C(0x3ff0000000000000), UINT64_C(0x4010000000000000), 0);
  FP_CASE(202, "fsqrt.d ft2, ft0, rne", UINT64_C(0x4010000000000000), 0,
          UINT64_C(0x4000000000000000), 0);
  FP_CASE(204, "fsqrt.d ft2, ft0, rne", UINT64_C(0xc010000000000000), 0,
          UINT64_C(0x7ff8000000000000), 16);
}

// crt0 calls this with a valid stack in M-mode, before mret into U-mode main.
void rvtest_init(void) {
  uint64_t status, mtvec, mepc, mcause, mtval, fcsr, vl, vtype, vstart, vcsr;
  uint64_t ft0, ft1, ft2, actual;
  INIT_CHECK();
  completed = 0;
  failure_count = failure_overflow = 0;
  asm volatile("csrrci %0, mstatus, 8" : "=r"(status) : : "memory");
  READ_CSR(mtvec, mtvec);
  READ_CSR(mepc, mepc);
  READ_CSR(mcause, mcause);
  READ_CSR(mtval, mtval);
  const uint64_t base = status & ~(STATE_MASK | MSTATUS_MIE);
  WRITE_CSR(mstatus, base | FS_INITIAL | VS_INITIAL);
  READ_CSR(fcsr, fcsr);
  READ_CSR(vl, vl);
  READ_CSR(vtype, vtype);
  READ_CSR(vstart, vstart);
  READ_CSR(vcsr, vcsr);
  asm volatile("fmv.x.d %0, ft0\nfmv.x.d %1, ft1\nfmv.x.d %2, ft2"
               : "=r"(ft0), "=r"(ft1), "=r"(ft2) : : "memory");
  WRITE_CSR(vstart, 0);

  test_vs(base, mtvec);
  test_sstatus(base);
  WRITE_CSR(mstatus, base | FS_INITIAL | VS_INITIAL);
  test_vtype();
  test_nanbox();

  // Restore extension contents first; status last so restore operations cannot
  // dirty the saved FS/VS. No assertion above can bypass this sequence.
  asm volatile("fmv.d.x ft0, %0\nfmv.d.x ft1, %1\nfmv.d.x ft2, %2"
               : : "r"(ft0), "r"(ft1), "r"(ft2) : "ft0", "ft1", "ft2", "memory");
  WRITE_CSR(fcsr, fcsr);
  // Reset VL/vtype must be restorable, including VILL; do not mask bit 63.
  asm volatile("vsetvl zero, %0, %1" : : "r"(vl), "r"(vtype) : "memory");
  WRITE_CSR(vcsr, vcsr);
  WRITE_CSR(vstart, vstart);
  READ_CSR(fcsr, actual);
  check(300, actual, fcsr);
  READ_CSR(vl, actual);
  check(301, actual, vl);
  READ_CSR(vtype, actual);
  check(302, actual, vtype);
  READ_CSR(vcsr, actual);
  check(303, actual, vcsr);
  READ_CSR(vstart, actual);
  check(304, actual, vstart);
  WRITE_CSR(mtvec, mtvec);
  WRITE_CSR(mepc, mepc);
  WRITE_CSR(mcause, mcause);
  WRITE_CSR(mtval, mtval);
  WRITE_CSR(mstatus, status & ~MSTATUS_MIE);
  READ_CSR(mstatus, actual);
  check(305, actual, status & ~MSTATUS_MIE);
  completed = DONE;
  WRITE_CSR(mstatus, status);
}

int main(void) {
  if (completed != DONE) {
    printf("ERROR: linux_state_prereq M-mode hook did not complete\n");
    return 1;
  }
  for (unsigned i = 0; i < failure_count; ++i)
    printf("Failure #%lu: got %016lx expected %016lx\n",
           failures[i].id, failures[i].actual, failures[i].expected);
  if (failure_overflow)
    printf("ERROR: failure log overflow: %u unrecorded (capacity %u)\n",
           failure_overflow, FAILURE_CAPACITY);
  printf("linux_state_prereq: %d checks\n", test_case);
  if (test_case != PLANNED_CHECKS) {
    printf("ERROR: check count %d != planned %d\n", test_case, PLANNED_CHECKS);
    return 1;
  }
  EXIT_CHECK();
}
