// Native RVV directed test. Compile with scalar autovectorization disabled.
// Run on a fresh simulation: v24-v27 are deliberately never initialized before
// their first use. No vector setup may precede main in the test harness.
#include <stdint.h>
#include <stdio.h>

#define BYTES 128
static uint8_t a[BYTES] __attribute__((aligned(64)));
static uint8_t b[BYTES] __attribute__((aligned(64)));
static uint8_t old[BYTES] __attribute__((aligned(64)));
static uint8_t got[BYTES] __attribute__((aligned(64)));
static unsigned checks, errors;

#define DEFINE_OP(NAME, OP, COLD) \
static unsigned long NAME(unsigned long vl, unsigned long start, int mode) { \
  unsigned long final_start; \
  if (mode == 2) { \
    __asm__ volatile( \
      "csrw vstart, zero\n\t" \
      "vsetvli zero, %[vl], e8, m8, ta, ma\n\t" \
      OP " v16, " COLD ", " COLD "\n\t" \
      "csrr %[end], vstart\n\t" \
      "vs1r.v v16, (%[out])\n\t" \
      : [end] "=&r" (final_start) \
      : [vl] "r" (vl), [out] "r" (got) \
      : "memory", "v16"); \
  } else { \
    __asm__ volatile( \
      "csrw vstart, zero\n\t" \
      "vl1re8.v v8, (%[a])\n\t" \
      "vl1re8.v v9, (%[b])\n\t" \
      "vl1re8.v v16, (%[old])\n\t" \
      "vsetvli zero, %[vl], e8, m8, tu, mu\n\t" \
      "csrw vstart, %[start]\n\t" \
      "beqz %[mode], 1f\n\t" \
      OP " v16, v9, v8\n\t" \
      "j 2f\n\t" \
      "1: " OP " v16, v8, v8\n\t" \
      "2: csrr %[end], vstart\n\t" \
      "vs1r.v v16, (%[out])\n\t" \
      : [end] "=&r" (final_start) \
      : [vl] "r" (vl), [start] "r" (start), [mode] "r" (mode), \
        [a] "r" (a), [b] "r" (b), [old] "r" (old), [out] "r" (got) \
      : "memory", "v8", "v9", "v16"); \
  } \
  return final_start; \
}

DEFINE_OP(do_xor, "vmxor.mm", "v24")
DEFINE_OP(do_andnot, "vmandn.mm", "v25")
DEFINE_OP(do_xnor, "vmxnor.mm", "v26")
DEFINE_OP(do_ornot, "vmorn.mm", "v27")

typedef unsigned long (*operation)(unsigned long, unsigned long, int);
static operation const operations[] = {do_xor, do_andnot, do_xnor, do_ornot};

static void run(unsigned op, unsigned vl, unsigned start, int mode) {
  unsigned long end = operations[op](vl, start, mode);
  ++checks;
  if (end != 0) ++errors;
  for (unsigned bit = 0; bit < BYTES * 8; ++bit) {
    if (mode == 2 && bit >= vl) continue; // Tail-agnostic cold case.
    unsigned shift = bit & 7, byte = bit >> 3;
    unsigned want = (old[byte] >> shift) & 1;
    if (bit >= start && bit < vl) {
      if (mode != 1) want = op >= 2;
      else {
        unsigned x = (a[byte] >> shift) & 1, y = (b[byte] >> shift) & 1;
        switch (op) {
          case 0: want = x ^ y; break;
          case 1: want = y & (x ^ 1); break;
          case 2: want = (x ^ y) ^ 1; break;
          default: want = y | (x ^ 1); break;
        }
      }
    }
    ++checks;
    if (((got[byte] >> shift) & 1) != want) {
      if (errors < 8) printf("masklogical mismatch op=%u mode=%d vl=%u start=%u bit=%u\n",
                             op, mode, vl, start, bit);
      ++errors;
    }
  }
}

int main(void) {
  unsigned long vlenb;
  __asm__ volatile("csrr %0, vlenb" : "=r" (vlenb));
  if (vlenb != BYTES) {
    printf("FAILED: masklogical_same_source requires VLEN=1024\n");
    return 1;
  }
  for (unsigned i = 0; i < BYTES; ++i) {
    a[i] = (uint8_t)(0x69 ^ (i * 13));
    b[i] = (uint8_t)(0xc3 ^ (i * 29));
    old[i] = (uint8_t)(0xa5 ^ (i * 7));
  }
  // Four independent cold registers retain SRAM X in four-state simulation.
  for (unsigned op = 0; op < 4; ++op) run(op, 64, 0, 2);
  static const unsigned windows[][2] = {
    {1, 0}, {63, 7}, {257, 0}, {511, 255},
    {1024, 257}, {0, 0}, {31, 31}, {31, 40}
  };
  for (unsigned op = 0; op < 4; ++op)
    for (unsigned i = 0; i < sizeof(windows) / sizeof(windows[0]); ++i)
      for (int mode = 0; mode < 2; ++mode)
        run(op, windows[i][0], windows[i][1], mode);
  printf("%s: masklogical_same_source cases=68 checks=%u errors=%u\n",
         errors ? "FAILED" : "PASSED", checks, errors);
  return errors != 0;
}
