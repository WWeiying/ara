/* Reuse only the frozen finite-half decoder and explicit host flag mapping. */
#define main unused_panel4_oracle_main
#include "../qk_panel4_native/rtl_oracle.c"
#undef main

int main(int argc, char **argv) {
  if (argc != 4 || sizeof(float) != 4 || FLT_RADIX != 2 || FLT_MANT_DIG != 24)
    return 1;
  const uint16_t endian = 1;
  if (*(const unsigned char *)&endian != 1 || fesetround(FE_TONEAREST)) return 2;
  static uint16_t q[12 * 128], k[2 * 256 * 128];
  static float qf[12 * 128], kf[2 * 256 * 128];
  read_exact(argv[1], q, sizeof(q));
  read_exact(argv[2], k, sizeof(k));
  for (unsigned i = 0; i < 12 * 128; ++i) qf[i] = half(q[i]);
  for (unsigned i = 0; i < 2 * 256 * 128; ++i) kf[i] = half(k[i]);
  FILE *out = fopen(argv[3], "wb");
  if (!out) return 3;
  const unsigned dims[3] = {64, 96, 128}, tokens[3] = {1, 63, 64};
  for (unsigned id = 0; id < 3; ++id) {
    const unsigned head = id != 0;
    uint32_t bits[128];
    for (unsigned i = 0; i < 128; ++i) bits[i] = UINT32_C(0xa5a5a5a5);
    if (feclearexcept(FE_ALL_EXCEPT)) return 4;
    for (unsigned row = 0; row < 2; ++row) {
      for (unsigned token = 0; token < tokens[id]; ++token) {
        float sum = 0.0f;
        for (unsigned d = 0; d < dims[id]; ++d)
          sum = fmaf(qf[(head * 6 + row) * 128 + d],
                     kf[(head * 256 + token) * 128 + d], sum);
        memcpy(&bits[row * 64 + token], &sum, 4);
      }
    }
    unsigned flags = riscv_flags(fetestexcept(FE_ALL_EXCEPT));
    if (fwrite(bits, sizeof(bits), 1, out) != 1) return 5;
    printf("ORACLE case=%u head=%u d=%u tokens=%u outputs=%u fcsr=%u\n",
           id, head, dims[id], tokens[id], 2 * tokens[id], flags);
  }
  return fclose(out) != 0;
}
