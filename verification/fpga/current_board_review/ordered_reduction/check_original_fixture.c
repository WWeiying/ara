#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include "fp_reduction_inputs.h"

struct fixture { uint64_t bits; unsigned flags; };
#include "fixtures.h"

int main(void) {
    unsigned index = 3 * 420 + 4 * 60 + 3 * 15;
    uint64_t infinity = SEW == 16 ? UINT64_C(0x7c00) : UINT64_C(0x7f800000);
    uint64_t negative = SEW == 16 ? UINT64_C(0xfc00) : UINT64_C(0xff800000);
    uint64_t nan = SEW == 16 ? UINT64_C(0x7e00) : UINT64_C(0x7fc00000);
    printf("ORIGINAL_FIXTURE sew=%u seed=%016" PRIx64
           " input2=%016" PRIx64 " input5=%016" PRIx64
           " result=%016" PRIx64 " flags=%02x\n",
           SEW, reduction_seed(3), reduction_input(3, 2, SEW),
           reduction_input(3, 5, SEW), fixtures[1][index].bits, fixtures[1][index].flags);
    return reduction_seed(3) != infinity || reduction_input(3, 2, SEW) != infinity ||
           reduction_input(3, 5, SEW) != negative || fixtures[1][index].bits != nan ||
           fixtures[1][index].flags != 16;
}
