#include <stdio.h>
#include <string.h>
#include "original_case.c"
#include "expected.h"

int main(void) {
    uint64_t random = UINT64_C(0x937ad68de41c725f);
    for (unsigned i = 0; i < 512; ++i) {
        random ^= random << 13; random ^= random >> 7; random ^= random << 17;
        a[i] = random; b[i] = random >> 19;
        switch (i % 8) {
        case 0: a[i] = 0; b[i] = 0; break;
        case 1: a[i] = (word)-1; b[i] = 1; break;
        case 2: a[i] = 128; b[i] = (word)-1; break;
        case 3: b[i] = SEW; break;
        }
    }
    unsigned lengths[] = {0, 1, 2, 3, 256, 511, 512};
    unsigned trial = 0;
    for (unsigned li = 0; li < 7; ++li)
    for (unsigned mode = 0; mode < 4; ++mode) {
        unsigned vl = lengths[li], starts[] = {1, vl / 2, vl, 511};
        for (unsigned si = 0; si < 4; ++si)
        for (unsigned rm = 0; rm < 8; ++rm) {
            unsigned sat = rm >> 2;
            uint8_t want[514];
            memset(want, 0x5b, sizeof want);
            for (unsigned i = 0; i < 512; ++i)
                if (i < vl && i >= starts[si] && selected(mode, i))
                    want[i + 1] = extra_value(0, a[i], b[i], rm, &sat);
            if (memcmp(want, expected_blocks[expected_index[trial]], sizeof want) ||
                sat != expected_sat[trial]) return 1;
            if (++trial == 777) {
                printf("ORIGINAL_SCALAR_EQUIVALENCE_PASS calls=777 results=397824 guards=1554\n");
                return 0;
            }
        }
    }
    return 2;
}
