#include "quantizers.h"
#include "captures.h"
#include <stdio.h>

static float input[8960];
static block_q8_K expected[37], actual[37];
int main(void) {
    unsigned checks = 0;
    for (unsigned capture = 0; capture < 7; ++capture) {
        const size_t bytes = capture_lengths[capture]*sizeof(float);
        memcpy(input, capture_data[capture], bytes);
        for (unsigned frm = 0; frm < 5; ++frm) {
            for (unsigned vc = 0; vc < 8; ++vc) {
                const unsigned flags[] = {0,1,2,4,8,16,31,0};
                unsigned fcsr = (frm<<5)|flags[vc], ef, ev, af, av;
                memset(expected, 0xa5, sizeof(expected));
                memset(actual, 0xa5, sizeof(actual));
                asm volatile("csrw fcsr,%0; csrw vcsr,%1" :: "r"(fcsr), "r"(vc) : "memory");
                decode_original(input, expected+1, capture_lengths[capture]);
                asm volatile("frcsr %0; csrr %1,vcsr" : "=r"(ef), "=r"(ev) :: "memory");
                asm volatile("csrw fcsr,%0; csrw vcsr,%1" :: "r"(fcsr), "r"(vc) : "memory");
                decode_candidate(input, actual+1, capture_lengths[capture]);
                asm volatile("frcsr %0; csrr %1,vcsr" : "=r"(af), "=r"(av) :: "memory");
                if (memcmp(expected, actual, sizeof(actual)) || ef!=af || ev!=av ||
                    memcmp(input, capture_data[capture], bytes)) {
                    printf("Q8K_DECODE_REAL_FAIL capture=%u frm=%u vc=%u\n", capture, frm, vc);
                    return 1;
                }
                for (unsigned b=0; b<capture_lengths[capture]/256; ++b) {
                    for (unsigned g=0; g<16; ++g) {
                        int sum=0;
                        for (unsigned j=0; j<16; ++j) sum+=actual[b+1].qs[g*16+j];
                        if (sum!=actual[b+1].bsums[g]) return 2;
                    }
                }
                ++checks;
            }
        }
    }
    printf("Q8K_DECODE_REAL_PASS checks=%u\n", checks);
    return checks==280 ? 0 : 3;
}
