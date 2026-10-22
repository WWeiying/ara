/* Host-only fault injections into the actual C bit oracle. */
#define main gap54_reference_main
#include "../../apps/akv_gap54_skew_context/main.c"
#undef main

int main(void) {
  unsigned rejected = 0;
  for (unsigned fault = 0; fault < 20; ++fault) {
    akv_v2_reference_init(&context);
    host_mode = host_traps = checks = errors = 0;
    setup();
    unsigned full = fault >= 17 ? 7 : 0;
    unsigned row = full + 1;
    seed(full);
    issue(full);
    poison(full == 7);
    seed(row);
    issue(row);
    if (errors) return 2;
    static const unsigned indices[10] = {0,15,16,31,32,47,48,63,64,255};
    if (fault < 10) got.data[indices[fault]] ^= 1;
    else if (fault == 10) initial.data[127] ^= 1;
    else if (fault == 11) got.before[31] ^= 1;
    else if (fault == 12) got.after[0] ^= 1;
    else if (fault == 13) initial.after[31] ^= 1;
    else if (fault == 14) source[0][1][offset(0,1)+62] ^= 1;
    else if (fault == 15) source[1][2][255] ^= 1;
    else if (fault == 16) descriptor[0].q_row_stride_bytes ^= 2;
    else if (fault == 17) got.data[63] ^= 1;
    else if (fault == 18) got.data[0] ^= 0x1000; /* stale A instead of B */
    else got.data[0] ^= 0x5a5a; /* live poisoned memory instead of snapshot */
    compare(row);
    if (!errors) return 3;
    ++rejected;
  }
  akv_v2_reference_init(&context);
  host_mode = host_traps = checks = errors = 0;
  setup(); seed(0); issue(0); poison(0); seed(1); issue(1); compare(1);
  if (errors) return 4;
  struct { void *base; unsigned bytes; } regions[] = {
    {got.data,512}, {initial.data,512}, {got.before,64}, {got.after,64},
    {initial.before,64}, {initial.after,64}, {source,1536}, {descriptor,128}
  };
  unsigned exhaustive = 0;
  for (unsigned r = 0; r < sizeof(regions)/sizeof(regions[0]); ++r) {
    unsigned char *p = regions[r].base;
    for (unsigned b = 0; b < regions[r].bytes; ++b) {
      errors = 0;
      p[b] ^= 1;
      compare(1);
      p[b] ^= 1;
      if (errors != 1) return 5;
      ++exhaustive;
    }
  }
  errors = 0;
  got.data[0] ^= 1; got.data[4] ^= 1;
  compare(1);
  if (errors != 1) return 6;
  printf("GAP54_EXHAUSTIVE rejected=%u cancellation_rejected=1\n",exhaustive);
  printf("GAP54_NEGATIVE_HOST rejected=%u\n",rejected);
  return rejected != 20;
}
