// Eight mask-logical operations at one aggregate-word restart boundary.
#include <stdint.h>
#include <stdio.h>

static uint8_t a[128] __attribute__((aligned(64)));
static uint8_t b[128] __attribute__((aligned(64)));
static uint8_t old[128] __attribute__((aligned(64)));
volatile uint8_t restart8_got[8][144] __attribute__((aligned(64)));
static unsigned checks, errors;

static void check(unsigned got, unsigned want) {
  ++checks;
  if (got != want) ++errors;
}

#define DEFINE_OP(N, OP, DST, SRC1) \
static __attribute__((noinline)) void op##N(unsigned long *end, unsigned long *vl) { \
  unsigned long seen_start, seen_vl; \
  __asm__ volatile( \
    "csrw vstart, zero\n\t" \
    "vl1re8.v v8, (%[a])\n\t" \
    "vl1re8.v v9, (%[b])\n\t" \
    "vl1re8.v v0, (%[a])\n\t" \
    "vl1re8.v v16, (%[old])\n\t" \
    "vsetvli zero, %[full], e8, m8, tu, mu\n\t" \
    "csrw vstart, %[start]\n\t" \
    ".globl restart8_site" #N "\nrestart8_site" #N ":\n\t" \
    OP " " DST ", v9, " SRC1 "\n\t" \
    "csrr %[end], vstart\n\t" \
    "csrr %[vl], vl\n\t" \
    "vs1r.v " DST ", (%[out])\n\t" \
    "fence rw, rw\n\t" \
    : [end] "=&r" (seen_start), [vl] "=&r" (seen_vl) \
    : [a] "r" (a), [b] "r" (b), [old] "r" (old), \
      [out] "r" (&restart8_got[N][8]), [full] "r" (1024UL), [start] "r" (256UL) \
    : "memory", "v0", "v8", "v9", "v16"); \
  *end = seen_start; *vl = seen_vl; \
}

DEFINE_OP(0, "vmand.mm",  "v16", "v8")
DEFINE_OP(1, "vmnand.mm", "v16", "v8")
DEFINE_OP(2, "vmandn.mm", "v16", "v8")
DEFINE_OP(3, "vmor.mm",   "v8",  "v8") // Legal vd == vs1; prefix comes from a.
DEFINE_OP(4, "vmnor.mm",  "v16", "v8")
DEFINE_OP(5, "vmorn.mm",  "v16", "v8")
DEFINE_OP(6, "vmxor.mm",  "v16", "v0") // v0 is source data, not predication.
DEFINE_OP(7, "vmxnor.mm", "v16", "v8")

int main(void) {
  unsigned long vlenb;
  __asm__ volatile("csrr %0, vlenb" : "=r" (vlenb));
  check(vlenb, 128);
  if (errors) return 1;
  for (unsigned i = 0; i < 128; ++i) {
    a[i] = (uint8_t)(0x69 ^ (i * 13));
    b[i] = (uint8_t)(0xc3 ^ (i * 29));
    old[i] = (uint8_t)(0xa5 ^ (i * 7));
  }
  void (*const ops[])(unsigned long *, unsigned long *) =
      {op0, op1, op2, op3, op4, op5, op6, op7};
  for (unsigned op = 0; op < 8; ++op) {
    for (unsigned i = 0; i < 144; ++i) restart8_got[op][i] = 0xd3;
    unsigned long end, vl;
    ops[op](&end, &vl);
    check(end, 0); check(vl, 1024);
    for (unsigned bit = 0; bit < 1024; ++bit) {
      unsigned byte = bit >> 3, shift = bit & 7;
      unsigned x = (b[byte] >> shift) & 1, y = (a[byte] >> shift) & 1;
      unsigned want;
      switch (op) {
        case 0: want = x & y; break;
        case 1: want = !(x & y); break;
        case 2: want = x & !y; break;
        case 3: want = x | y; break;
        case 4: want = !(x | y); break;
        case 5: want = x | !y; break;
        case 6: want = x ^ y; break;
        default: want = !(x ^ y); break;
      }
      if (bit < 256) want = ((op == 3 ? a[byte] : old[byte]) >> shift) & 1;
      check((restart8_got[op][8 + byte] >> shift) & 1, want);
    }
    for (unsigned i = 0; i < 8; ++i) {
      check(restart8_got[op][i], 0xd3);
      check(restart8_got[op][136+i], 0xd3);
    }
#ifdef __SPIKE__
    printf("RESTART8 %u ", op);
    for (unsigned i = 0; i < 144; ++i) printf("%02x", (unsigned)restart8_got[op][i]);
    printf("\n");
#endif
  }
  printf("%s: masklogical_restart8 cases=8 checks=%u errors=%u\n",
         errors ? "FAILED" : "PASSED", checks, errors);
  return errors != 0;
}
