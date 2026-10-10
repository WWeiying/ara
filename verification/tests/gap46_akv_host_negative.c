/* Host-only fault injections into the actual C bit oracle. */
#define main gap46_reference_main
#include "../../apps/akv_gap46_skew_context/main.c"
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
  printf("GAP46_NEGATIVE_HOST rejected=%u\n",rejected);
  return rejected != 20;
}
