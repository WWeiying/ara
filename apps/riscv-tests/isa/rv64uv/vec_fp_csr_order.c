// SPDX-License-Identifier: SHL-0.51
// Immediate vector-FP/CSR ordering. No synchronizing instruction is allowed
// between a tested FP operation and its following CSR access.
#include "vector_macros.h"

enum { N = 16, NX = 1, DZ = 8, NV = 16 };
enum { RNE, RTZ, RDN, RUP, RMM };
enum { ROUNDED, NAN_INT, UNCHANGED, DIV_ZERO };
static const uint32_t fractions[N] __attribute__((aligned(128))) = {
    0x3fc00000, 0x40200000, 0xbfc00000, 0xc0200000,
    0x3fc00000, 0x40200000, 0xbfc00000, 0xc0200000,
    0x3fc00000, 0x40200000, 0xbfc00000, 0xc0200000,
    0x3fc00000, 0x40200000, 0xbfc00000, 0xc0200000};
static const uint32_t nans[N] __attribute__((aligned(128))) = {
    0x7fc00000, 0x7fc00000, 0x7fc00000, 0x7fc00000,
    0x7fc00000, 0x7fc00000, 0x7fc00000, 0x7fc00000,
    0x7fc00000, 0x7fc00000, 0x7fc00000, 0x7fc00000,
    0x7fc00000, 0x7fc00000, 0x7fc00000, 0x7fc00000};
static uint32_t output[2][N] __attribute__((aligned(128)));
static const int32_t rounded[5][4] = {
    {2, 2, -2, -2}, {1, 2, -1, -2}, {1, 2, -2, -3},
    {2, 3, -1, -2}, {2, 3, -2, -3}};
static volatile uint64_t trap_count, trap_cause, trap_fcsr, trap_cleared;
static unsigned cases, checks;

// No prologue or vector-CSR read may precede the FCSR read. A rejected vector
// FP request must not leave a pending-FP token that blocks this handler.
void __attribute__((naked, used)) mtvec_handler(void) {
  asm volatile(
      "csrr t0, fcsr\n"
      "csrwi fflags, 0\n"
      "csrr t2, fflags\n"
      "la t1, trap_fcsr\n"
      "sd t0, 0(t1)\n"
      "la t1, trap_cleared\n"
      "sd t2, 0(t1)\n"
      "csrr t0, mcause\n"
      "la t1, trap_cause\n"
      "sd t0, 0(t1)\n"
      "la t1, trap_count\n"
      "ld t0, 0(t1)\n"
      "addi t0, t0, 1\n"
      "sd t0, 0(t1)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" :: "r"(mtvec_handler) : "memory");
}

// Setup is before the critical sequence; all stores/barriers/VL restoration
// are AFTER both captured CSR values. Late FCSR checks catch stale reassertion
// of flags following a clear/overwrite. Trap scratch registers are clobbered.
#define RUN(SEQUENCE)                                                         \
  asm volatile(                                                               \
      "vsetivli zero, 16, e32, m1, tu, mu\n"                                  \
      "vle32.v v8, (%[src])\n"                                                \
      "vle32.v v10, (%[nan])\n"                                               \
      "vmv.v.i v12, -1\n"                                                     \
      "vmv.v.i v16, -1\n"                                                     \
      "vmv.v.i v18, 0\n"                                                      \
      "csrw fcsr, %[initial]\n"                                               \
      SEQUENCE                                                                \
      "vsetivli zero, 16, e32, m1, tu, mu\n"                                  \
      "vse32.v v12, (%[out0])\n"                                              \
      "vse32.v v16, (%[out1])\n"                                              \
      "fence\n"                                                              \
      "csrr zero, vl\n"                                                       \
      "csrr %[late], fcsr\n"                                                  \
      : [a] "=&r"(a), [b] "=&r"(b), [late] "=&r"(late)                       \
      : [src] "r"(fractions), [nan] "r"(nans), [out0] "r"(output[0]),         \
        [out1] "r"(output[1]), [initial] "r"(initial), [value] "r"(value)      \
      : "memory", "t0", "t1", "t2", "v8", "v10", "v12", "v16", "v18")

static void check(unsigned id, const char *what, uint64_t got, uint64_t want) {
  ++checks;
  if (got != want) {
    printf("FAIL case=%u %s got=%lx expected=%lx\n", id, what, got, want);
    ++num_failed;
  }
}

static void check_vector(unsigned id, unsigned dest, unsigned kind, unsigned rm) {
  for (unsigned i = 0; i < N; ++i) {
    uint32_t want = kind == UNCHANGED ? UINT32_MAX :
                    kind == NAN_INT ? 0x7fffffff :
                    kind == DIV_ZERO ? (i % 4 < 2 ? 0x7f800000 : 0xff800000) :
                    (uint32_t)rounded[rm][i % 4];
    check(id, dest ? "v16" : "v12", output[dest][i], want);
  }
}

static void run_case(unsigned id) {
  uint64_t a, b, late, initial = 0, value = 0;
  uint64_t want_a = 0, want_b = 0, want_late = 0;
  unsigned kind0 = ROUNDED, kind1 = UNCHANGED, rm0 = RNE, rm1 = RNE;
  switch (id) {
  case 1:
    RUN("vfcvt.x.f.v v12, v8\ncsrr %[a], fflags\ncsrr %[b], fcsr\n");
    want_a = want_b = want_late = NX;
    break;
  case 2:
    RUN("vfcvt.x.f.v v12, v10\ncsrwi fflags, 0\n"
        "csrr %[a], fflags\ncsrr %[b], fcsr\n");
    kind0 = NAN_INT;
    break;
  case 3:
    RUN("vfcvt.x.f.v v12, v8\ncsrsi fflags, 16\n"
        "csrr %[a], fflags\ncsrr %[b], fcsr\n");
    want_a = want_b = want_late = NX | NV;
    break;
  case 4:
    RUN("vfcvt.x.f.v v12, v8\ncsrci fflags, 1\n"
        "csrr %[a], fflags\ncsrr %[b], fcsr\n");
    break;
  case 5:
    value = NX;
    RUN("vfdiv.vv v12, v8, v18\ncsrrw %[a], fflags, %[value]\n"
        "csrr %[b], fflags\n");
    kind0 = DIV_ZERO;
    want_a = DZ;
    want_b = want_late = NX;
    break;
  case 6:
    value = NV;
    RUN("vfcvt.x.f.v v12, v8\ncsrrs %[a], fflags, %[value]\n"
        "csrr %[b], fflags\n");
    want_a = NX;
    want_b = want_late = NX | NV;
    break;
  case 7:
    value = NV;
    RUN("vfcvt.x.f.v v12, v10\ncsrrc %[a], fflags, %[value]\n"
        "csrr %[b], fflags\n");
    kind0 = NAN_INT;
    want_a = NV;
    break;
  case 8: case 9: case 10: case 11: case 12:
    rm0 = id - 8;
    rm1 = (rm0 + 1) % 5;
    initial = rm0 << 5;
    value = rm1;
    RUN("vfcvt.x.f.v v12, v8\ncsrw frm, %[value]\n"
        "vfcvt.x.f.v v16, v8\ncsrr %[a], fflags\ncsrr %[b], frm\n");
    kind1 = ROUNDED;
    want_a = NX;
    want_b = rm1;
    want_late = (rm1 << 5) | NX;
    break;
  case 13:
    rm0 = RDN;
    initial = RDN << 5;
    RUN("vfcvt.x.f.v v12, v8\ncsrr %[a], fcsr\ncsrr %[b], fflags\n");
    want_a = want_late = initial | NX;
    want_b = NX;
    break;
  case 14:
    rm0 = RDN;
    rm1 = RUP;
    initial = RDN << 5;
    value = (RUP << 5) | DZ;
    RUN("vfcvt.x.f.v v12, v8\ncsrrw %[a], fcsr, %[value]\n"
        "vfcvt.x.f.v v16, v8\ncsrr %[b], fcsr\n");
    kind1 = ROUNDED;
    want_a = initial | NX;
    want_b = want_late = value | NX;
    break;
  case 15:
    initial = RMM << 5;
    value = (RMM << 5) | NV;
    RUN("vfcvt.x.f.v v12, v10\ncsrrc %[a], fcsr, %[value]\n"
        "vfcvt.x.f.v v16, v8\ncsrr %[b], fcsr\n");
    kind0 = NAN_INT;
    kind1 = ROUNDED;
    want_a = value;
    want_b = want_late = NX;
    break;
  case 16:
    value = (RUP << 5) | NV;
    RUN("vfcvt.x.f.v v12, v8\ncsrrs %[a], fcsr, %[value]\n"
        "vfcvt.x.f.v v16, v8\ncsrr %[b], fcsr\n");
    kind1 = ROUNDED;
    rm1 = RUP;
    want_a = NX;
    want_b = want_late = value | NX;
    break;
  case 17:
    rm0 = RDN;
    initial = RDN << 5;
    RUN("vfcvt.x.f.v v12, v8\ncsrr %[a], frm\ncsrr %[b], fflags\n");
    want_a = RDN;
    want_b = NX;
    want_late = initial | NX;
    break;
  case 18:
    initial = (RMM << 5) | NV;
    value = (RUP << 5) | DZ;
    RUN("vsetivli zero, 0, e32, m1, tu, mu\n"
        "vfcvt.x.f.v v12, v10\ncsrrw %[a], fcsr, %[value]\ncsrr %[b], fcsr\n");
    kind0 = UNCHANGED;
    want_a = initial;
    want_b = want_late = value;
    break;
  case 19: case 20:
    initial = (RDN << 5) | DZ;
    // Single-width FP conversion at SEW=8 is illegal, including at VL=0.
    // This is NOT the legal FP16->I8 narrowing instruction under repair.
    if (id == 19) {
      RUN("vsetivli zero, 16, e8, m1, tu, mu\n"
          "vfcvt.x.f.v v12, v8\ncsrr %[a], fcsr\ncsrr %[b], fflags\n");
    } else {
      RUN("vsetivli zero, 0, e8, m1, tu, mu\n"
          "vfcvt.x.f.v v12, v8\ncsrr %[a], fcsr\ncsrr %[b], fflags\n");
    }
    kind0 = UNCHANGED;
    want_a = want_late = RDN << 5;
    check(id, "trap count", trap_count, id - 18);
    check(id, "mcause", trap_cause, 2);
    check(id, "handler first fcsr", trap_fcsr, initial);
    check(id, "handler cleared fflags", trap_cleared, 0);
    break;
  case 21:
    // Two independent pending FP requests must both contribute before the
    // single following fflags read. No setup/synchronization between them.
    RUN("vfcvt.x.f.v v12, v10\nvfcvt.x.f.v v16, v8\n"
        "csrr %[a], fflags\ncsrr %[b], fcsr\n");
    kind0 = NAN_INT;
    kind1 = ROUNDED;
    want_a = want_b = want_late = NV | NX;
    break;
  default:
    return;
  }
  check(id, "immediate CSR a", a, want_a);
  check(id, "immediate CSR b", b, want_b);
  check(id, "late fcsr", late, want_late);
  check_vector(id, 0, kind0, rm0);
  check_vector(id, 1, kind1, rm1);
  if (id <= 18 || id == 21)
    check(id, "unexpected trap", trap_count, id == 21 ? 2 : 0);
  ++cases;
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  cases = checks = 0;
  trap_count = trap_cause = trap_fcsr = trap_cleared = 0;
  uint64_t bytes, saved_fcsr;
  asm volatile("csrr %0, vlenb\ncsrr %1, fcsr\n"
               : "=r"(bytes), "=r"(saved_fcsr));
#ifdef __SPIKE__
  rvtest_init();
#endif
  if (bytes < N * sizeof(uint32_t)) {
    printf("FAIL vec_fp_csr_order requires VLEN >= 512\n");
    return 1;
  }
  for (unsigned id = 1; id <= 21; ++id)
    run_case(id);
  asm volatile("csrw fcsr, %0" :: "r"(saved_fcsr) : "memory");
  printf("vec_fp_csr_order: %u cases, %u checks, traps=%lu\n", cases, checks,
         (unsigned long)trap_count);
  EXIT_CHECK();
}
