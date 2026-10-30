#include "qbs_abi.h"
#include "qbs_ref.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#define REQUIRE(expr) do { if (!(expr)) { \
  fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #expr); exit(1); \
} } while (0)

int main(void) {
  const unsigned vlens[] = {0, 32, 128, 512, 1023, 1024, 1025, 2048, 4096};
  unsigned encodings = 0;
#ifndef TEST_BASELINE
  REQUIRE(QBS_M_MINUS_ONE_BITS == 3);
  REQUIRE(QBS_QBACC_FUNCT7_BIT == 3);
  REQUIRE(QBS_VRF_CONTINUATION_CAPABILITY_INDEX == 4);
  REQUIRE(QBS_VRF_CONTINUATION_CAPABILITY_BIT == 0);
  REQUIRE(QBS_VRF_CONTINUATION_VLEN_BITS == 1024);
#endif
  for (unsigned v = 0; v < sizeof(vlens) / sizeof(vlens[0]); ++v) {
    for (unsigned i = 0; i < 256; ++i) {
      uint64_t got = qbs_capability_word(i, vlens[v]);
      REQUIRE(qbs_ref_capability_word(i, vlens[v]) == got);
      if (i == 4) {
        uint64_t expected = 0;
#if defined(ARA_QBS_VRF_CONTINUATION) && !defined(TEST_BASELINE)
        expected = vlens[v] == 1024 ? 1 : 0;
#endif
        REQUIRE(got == expected);
      } else {
        /* Identical output must match the archived pre-change header. */
        printf("CAP vlen=%u index=%u word=%016" PRIx64 "\n", vlens[v], i, got);
      }
    }
    REQUIRE(qbs_capability_word(~0u, vlens[v]) == 0);
  }
  for (unsigned m = 1; m <= 8; ++m)
    for (unsigned vd = 0; vd < 32; ++vd)
      for (unsigned rs1 = 0; rs1 < 32; ++rs1)
        for (unsigned rs2 = 0; rs2 < 32; ++rs2) {
          uint32_t expected = UINT32_C(0x5b) | (vd << 7) | (rs1 << 15) |
                              (rs2 << 20) | ((m - 1) << 25);
          REQUIRE(qbs_encode_qbexec(vd, rs1, rs2, m) == expected);
#ifndef TEST_BASELINE
          REQUIRE(qbs_encode_qbacc(vd, rs1, rs2, m) ==
                  (expected | UINT32_C(0x10000000)));
          REQUIRE((qbs_encode_qbacc(vd, rs1, rs2, m) >> 29) == 0);
#endif
          ++encodings;
        }
  for (unsigned rd = 0; rd < 32; ++rd)
    for (unsigned rs1 = 0; rs1 < 32; ++rs1)
      REQUIRE(qbs_encode_qbinfo(rd, rs1) ==
              (UINT32_C(0x105b) | (rd << 7) | (rs1 << 15)));
  REQUIRE(encodings == 262144);
  puts("QBACC_ABI_C_PASS encodings=262144 capabilities=2304");
  return 0;
}
