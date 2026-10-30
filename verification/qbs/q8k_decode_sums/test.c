#include "sums.h"
#include <stdio.h>
#include <string.h>

__attribute__((noinline)) static void original(vint8m2_t values, size_t vl, int16_t *out) {
    const vint16m1_t zero = __riscv_vmv_v_x_i16m1(0, 1);
    vint8m1_t part = __riscv_vget_v_i8m2_i8m1(values, 0);
    out[0] = __riscv_vmv_x_s_i16m1_i16(__riscv_vwredsum_vs_i8m1_i16m1(part, zero, 16));
    for (size_t offset = 16; offset < vl; offset += 16) {
        values = __riscv_vslidedown_vx_i8m2(values, 16, vl);
        part = __riscv_vget_v_i8m2_i8m1(values, 0);
        out[offset / 16] = __riscv_vmv_x_s_i16m1_i16(__riscv_vwredsum_vs_i8m1_i16m1(part, zero, 16));
    }
}

int main(void) {
    int8_t input[256];
    int16_t expected[18], actual[18];
    unsigned checks = 0;
    for (unsigned pattern = 0; pattern < 260; ++pattern) {
        for (unsigned i = 0; i < 256; ++i) {
            input[i] = pattern < 256 ? (int8_t)(pattern + 37*i) :
                       pattern == 256 ? -128 : pattern == 257 ? 127 :
                       pattern == 258 ? 0 : (i % 2 ? -128 : 127);
        }
        for (size_t size = 16; size <= 256; size += 16) {
            for (unsigned csr = 0; csr < 8; ++csr) {
                memset(expected, 0xa5, sizeof(expected));
                memset(actual, 0xa5, sizeof(actual));
                for (size_t offset = 0; offset < size;) {
                    size_t vl = __riscv_vsetvl_e8m2(size-offset);
                    // Use only complete groups, including a tail below VLMAX.
                    vl -= vl % 16;
                    if (!vl) return 2;
                    const vint8m2_t q = __riscv_vle8_v_i8m2(input+offset, vl);
                    asm volatile("csrw vcsr,%0; csrwi fcsr,17" :: "r"(csr) : "memory");
                    original(q, vl, expected+1+offset/16);
                    qbs_decode_sums_candidate(q, vl, actual+1+offset/16);
                    unsigned vc, fc;
                    asm volatile("csrr %0,vcsr; frcsr %1" : "=r"(vc), "=r"(fc) :: "memory");
                    if (vc != csr || fc != 17) return 3;
                    offset += vl;
                }
                if (memcmp(expected, actual, sizeof(actual))) return 4;
                for (size_t i = 0; i < size/16; ++i) {
                    int sum = 0;
                    for (size_t j = 0; j < 16; ++j) sum += input[16*i+j];
                    if (actual[i+1] != sum) return 5;
                }
                ++checks;
            }
        }
    }
    printf("Q8K_DECODE_SUMS_PASS checks=%u\n", checks);
    return checks == 33280 ? 0 : 6;
}
