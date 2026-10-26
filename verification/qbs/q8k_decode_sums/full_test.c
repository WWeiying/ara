#include "quantizers.h"
#include <stdio.h>

static float input[8960], saved[8960];
static block_q8_K expected[37], actual[37];

int main(void) {
    const int lengths[] = {0, 256, 512, 1536, 1792, 8960};
    unsigned checks = 0;
    for (unsigned pattern = 0; pattern < 12; ++pattern) {
        for (unsigned i = 0; i < 8960; ++i) {
            float value = (float)((int)((i*37+pattern*19)%257)-128)/17.0f;
            if (pattern == 0) value = 0.0f;
            if (pattern == 1) value = -0.0f;
            if (pattern == 2) value = i%2 ? -1.0f : 1.0f;
            if (pattern == 3) value = i%2 ? 1.0f : -1.0f;
            if (pattern == 4) value *= 0x1p-100f;
            if (pattern == 5) value *= 0x1p100f;
            input[i] = value;
        }
        memcpy(saved, input, sizeof(input));
        for (unsigned length = 0; length < 6; ++length) {
            for (unsigned frm = 0; frm < 5; ++frm) {
                for (unsigned vc = 0; vc < 8; ++vc) {
                    unsigned fcsr = (frm<<5) | (pattern%2 ? 17 : 0);
                    unsigned ef, ev, af, av;
                    memset(expected, 0xa5, sizeof(expected));
                    memset(actual, 0xa5, sizeof(actual));
                    asm volatile("csrw fcsr,%0; csrw vcsr,%1" :: "r"(fcsr), "r"(vc) : "memory");
                    decode_original(input, expected+1, lengths[length]);
                    asm volatile("frcsr %0; csrr %1,vcsr" : "=r"(ef), "=r"(ev) :: "memory");
                    asm volatile("csrw fcsr,%0; csrw vcsr,%1" :: "r"(fcsr), "r"(vc) : "memory");
                    decode_candidate(input, actual+1, lengths[length]);
                    asm volatile("frcsr %0; csrr %1,vcsr" : "=r"(af), "=r"(av) :: "memory");
                    if (memcmp(expected, actual, sizeof(actual)) || ef != af || ev != av ||
                        memcmp(input, saved, sizeof(input))) {
                        printf("Q8K_DECODE_FULL_FAIL pattern=%u k=%d frm=%u vcsr=%u f=%u/%u v=%u/%u\n",
                               pattern, lengths[length], frm, vc, ef, af, ev, av);
                        return 1;
                    }
                    for (int b = 0; b < lengths[length]/256; ++b) {
                        for (unsigned g = 0; g < 16; ++g) {
                            int sum = 0;
                            for (unsigned j = 0; j < 16; ++j) sum += actual[b+1].qs[16*g+j];
                            if (sum != actual[b+1].bsums[g]) return 2;
                        }
                    }
                    ++checks;
                }
            }
        }
    }
    printf("Q8K_DECODE_FULL_PASS checks=%u\n", checks);
    return checks == 2880 ? 0 : 3;
}
