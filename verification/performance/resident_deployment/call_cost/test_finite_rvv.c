#include "sdk/finite_f16.h"

static uint16_t data[32769] __attribute__((aligned(64)));
int main(void) {
    unsigned long flags, vcsr, start;
    asm volatile("csrwi fflags,21\ncsrwi vcsr,5\ncsrwi vstart,0" ::: "memory");
    for (unsigned bits = 0; bits < 65536; ++bits) {
        data[0] = bits;
        if (ara_resident_finite_f16(data, 1) != ((bits & 0x7c00) != 0x7c00)) return 1;
    }
    const unsigned lengths[] = {1, 2, 63, 64, 65, 127, 128, 129, 17536, 32768};
    for (unsigned j = 0; j < sizeof(lengths) / sizeof(*lengths); ++j) {
        unsigned n = lengths[j];
        for (unsigned i = 0; i < n; ++i) data[i] = i & 1 ? 0x7bff : 0x8000;
        data[n] = 0x7e00;
        if (!ara_resident_finite_f16(data, n)) return 2;
        const unsigned positions[] = {0, n / 2, n - 1};
        const uint16_t invalid[] = {0x7c00, 0xfc00, 0x7c01, 0x7e00, 0xfe01};
        for (unsigned p = 0; p < 3; ++p) {
            unsigned pos = positions[p];
            uint16_t saved = data[pos];
            for (unsigned b = 0; b < 5; ++b) {
                data[pos] = invalid[b];
                if (ara_resident_finite_f16(data, n)) return 3;
            }
            data[pos] = saved;
        }
    }
    asm volatile("csrr %0,fflags\ncsrr %1,vcsr\ncsrr %2,vstart" : "=r"(flags), "=r"(vcsr), "=r"(start));
    return flags != 21 || vcsr != 5 || start != 0 ? 4 : 0;
}
