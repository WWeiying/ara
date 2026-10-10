// Build with vec=0 and -fno-slp-vectorize: reference loops must remain scalar.
#include "vector_macros.h"

#define WORDS 32
#define ROUNDS 4
#define BAD_STORE 0xe0000000ul
#define ALIGN128 __attribute__((aligned(128)))

static volatile uint32_t source[ROUNDS][WORDS] ALIGN128;
static volatile uint32_t input[ROUNDS][WORDS] ALIGN128;
static volatile uint32_t target[ROUNDS][2 * WORDS] ALIGN128;
static volatile uint32_t result[ROUNDS][WORDS] ALIGN128;
static const uint32_t mask ALIGN128 = 0xaaaaaaaa;
// count, mcause, mepc, mtval, vstart, v8[0], unretired vset/scalar destinations.
static volatile uint64_t trap_info[8] __attribute__((used));
extern char lookahead_store_fault[];

void rvtest_init(void) {
  // Correctness-only trap test, not a performance benchmark: keep main in
  // M-mode after apps/common/crt0.S executes its startup mret.
  asm volatile("csrs mstatus, %0" : : "r"(MSTATUS_MPP) : "memory");
}

static void __attribute__((naked, used, aligned(4))) trap_handler(void) {
  asm volatile(
      "addi sp, sp, -16\n"
      "sd t0, 0(sp)\n"
      "sd t1, 8(sp)\n"
      "la t1, trap_info\n"
      "ld t0, 0(t1)\n"
      "addi t0, t0, 1\n"
      "sd t0, 0(t1)\n"
      "csrr t0, mcause\n"
      "sd t0, 8(t1)\n"
      "csrr t0, mepc\n"
      "sd t0, 16(t1)\n"
      "csrr t0, mtval\n"
      "sd t0, 24(t1)\n"
      "csrr t0, vstart\n"
      "sd t0, 32(t1)\n"
      // No vset, vector store, or vector-register modification in the handler.
      "vmv.x.s t0, v8\n"
      "sd t0, 40(t1)\n"
      "sd t2, 48(t1)\n"
      "sd t3, 56(t1)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "ld t0, 0(sp)\n"
      "ld t1, 8(sp)\n"
      "addi sp, sp, 16\n"
      "mret\n");
}

static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    if (num_failed < 8)
      printf("lookahead %u: got %lx expected %lx\n", id,
             (unsigned long)actual, (unsigned long)expected);
    ++num_failed;
  }
}

static uint32_t old_word(unsigned round, unsigned i) {
  return 0xdead0000u ^ (round << 12) ^ i;
}

// Keep the tested store/vset/load adjacent, with no completion CSR or fence.
#define STORE_LOAD(SUFFIX)                                                     \
  asm volatile("vsetvli zero, %[full], e32, m1, tu, mu\n"                       \
               "vle32.v v4, (%[src])\n"                                       \
               "vmv.v.i v8, -1\n"                                            \
               "vlm.v v0, (%[mask])\n"                                       \
               "vsetvli zero, %[n], e32, m1, tu, mu\n"                        \
               "vse32.v v4, (%[dst])" SUFFIX "\n"                            \
               "vsetvli zero, %[n], e32, m1, tu, mu\n"                        \
               "vle32.v v8, (%[load])\n"                                     \
               "vsetvli zero, %[full], e32, m1, tu, mu\n"                     \
               "vse32.v v8, (%[out])\n"                                      \
               :                                                             \
               : [full] "r"(WORDS), [n] "r"(n), [src] "r"(source[r]),           \
                 [dst] "r"(&target[r][store_off]), [load] "r"(load),           \
                 [out] "r"(result[r]), [mask] "r"(&mask)                       \
               : "v0", "v4", "v8", "memory")

static void run_case(unsigned id, unsigned store_off, unsigned load_off,
                     unsigned n, unsigned masked, unsigned disjoint) {
  for (unsigned r = 0; r < ROUNDS; ++r) {
    for (unsigned i = 0; i < WORDS; ++i) {
      source[r][i] = 0x12340000u ^ (id << 16) ^ (r << 10) ^ (i * 37);
      input[r][i] = 0x87650000u ^ (id << 16) ^ (r << 10) ^ (i * 71);
      result[r][i] = 0;
    }
    for (unsigned i = 0; i < 2 * WORDS; ++i)
      target[r][i] = old_word(r, i);
  }
  MEMORY_BARRIER;
  for (unsigned r = 0; r < ROUNDS; ++r) {
    const volatile uint32_t *load =
        disjoint ? input[r] : &target[r][load_off];
    if (masked) {
      STORE_LOAD(", v0.t");
    } else {
      STORE_LOAD("");
    }
  }
  MEMORY_BARRIER;

  uint64_t actual_sum = 0, expected_sum = 0;
  for (unsigned r = 0; r < ROUNDS; ++r) {
    for (unsigned i = 0; i < 2 * WORDS; ++i) {
      unsigned j = i - store_off;
      uint32_t expected = j < n && (!masked || ((mask >> j) & 1))
                              ? source[r][j] : old_word(r, i);
      uint32_t actual = target[r][i];
      check(id * 1000 + r * 100 + i, actual, expected);
      actual_sum += actual;
      expected_sum += expected;
    }
    for (unsigned i = 0; i < WORDS; ++i) {
      unsigned pos = load_off + i, j = pos - store_off;
      uint32_t expected = 0xffffffffu;
      if (i < n)
        expected = disjoint ? input[r][i]
                   : j < n && (!masked || ((mask >> j) & 1))
                       ? source[r][j] : old_word(r, pos);
      check(id * 1000 + r * 100 + 64 + i, result[r][i], expected);
      actual_sum += result[r][i];
      expected_sum += expected;
    }
  }
  check(id, actual_sum, expected_sum);
}

static void __attribute__((noinline)) fault_case(uint32_t sentinel) {
  uint64_t visible_vl, visible_remaining;
  asm volatile("vsetvli zero, %[n], e32, m1, tu, mu\n"
               "vmv.v.i v4, 7\n"
               "vmv.v.x v8, %[sentinel]\n"
               "mv t2, %[sentinel]\n"
               "mv t3, %[sentinel]\n"
               ".option push\n"
               ".option norvc\n"
               ".balign 4\n"
               "lookahead_store_fault: vse32.v v4, (%[bad])\n"
               "vsetvli t2, %[n], e32, m1, tu, mu\n"
               "sub t3, %[n], t2\n"
               "vle32.v v8, (%[src])\n"
               "vse32.v v8, (%[out])\n"
               "mv %[vl], t2\n"
               "mv %[remaining], t3\n"
               ".option pop\n"
               : [vl] "=&r"(visible_vl), [remaining] "=&r"(visible_remaining)
               : [n] "r"(WORDS), [sentinel] "r"(sentinel),
                 [bad] "r"(BAD_STORE), [src] "r"(input[0]),
                 [out] "r"(result[0])
               : "t2", "t3", "v4", "v8", "memory");
  MEMORY_BARRIER;
  check(86, visible_vl, WORDS);
  check(87, visible_remaining, 0);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  uint64_t old_mtvec, vl;
  for (unsigned i = 0; i < 8; ++i)
    trap_info[i] = 0;
  asm volatile("csrrw %0, mtvec, %1" : "=r"(old_mtvec)
               : "r"(trap_handler) : "memory");
  asm volatile("csrw vstart, zero\n"
               "vsetvli %0, %1, e32, m1, tu, mu\n"
               : "=r"(vl) : "r"(WORDS) : "memory");
  check(0, vl, WORDS); // One 128-byte unit requires VLEN >= 1024.
  if (vl == WORDS) {
    run_case(1, 0, 0, WORDS, 0, 1);  // Disjoint streaming.
    run_case(2, 0, 0, WORDS, 0, 0);  // Same-address RAW, old != new.
    run_case(3, 0, 16, WORDS, 0, 0); // Upper half overlaps.
    run_case(4, 16, 0, WORDS, 0, 0); // Lower half overlaps.
    run_case(5, 0, 0, 19, 0, 1);    // Short store/load; tail stays sentinel.
    run_case(6, 0, 0, WORDS, 1, 0);  // Masked RAW retains inactive words.
    check(7, trap_info[0], 0);
    for (unsigned r = 0; r < 2; ++r) {
      uint32_t sentinel = r ? 0x2468ace0u : 0x13579bdfu;
      for (unsigned i = 0; i < WORDS; ++i) {
        input[0][i] = 0x76540000u ^ (r << 12) ^ (i * 73);
        result[0][i] = 0;
      }
      MEMORY_BARRIER;
      fault_case(sentinel);
      check(80, trap_info[0], r + 1);
      check(81, trap_info[1], 7);
      check(82, trap_info[2], (uintptr_t)lookahead_store_fault);
      check(83, trap_info[3], BAD_STORE);
      check(84, trap_info[4], 0);
      check(85, trap_info[5], sentinel);
      check(88, trap_info[6], sentinel);
      check(89, trap_info[7], sentinel);
      for (unsigned i = 0; i < WORDS; ++i)
        check(90 + i, result[0][i], input[0][i]);
    }
  }
  // Leave neither the local trap handler nor live vector context at exit.
  MEMORY_BARRIER;
  asm volatile("csrw mtvec, %1\n"
               "csrw vstart, zero\n"
               "csrw vcsr, zero\n"
               "vsetvli %0, zero, e32, m1, tu, mu\n"
               "vmv.v.i v0, 0\n"
               "vmv.v.i v4, 0\n"
               "vmv.v.i v8, 0\n"
               "vsetivli zero, 0, e32, m1, tu, mu\n"
               : "=&r"(vl) : "r"(old_mtvec)
               : "v0", "v4", "v8", "memory");
  EXIT_CHECK();
}
