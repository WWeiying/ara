/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/akv_direct_policy.h>

_Static_assert(sizeof(struct ara_akv_direct_info) == 64, "info ABI");
_Static_assert(sizeof(struct ara_akv_direct_lease) == 64, "lease ABI");
_Static_assert(offsetof(struct ara_akv_direct_info, gate_signature) == 16, "signature");
_Static_assert(offsetof(struct ara_akv_direct_info, generation) == 24, "info generation");
_Static_assert(offsetof(struct ara_akv_direct_lease, generation) == 16, "generation");
_Static_assert(offsetof(struct ara_akv_direct_lease, owner_tid) == 24, "tid");
_Static_assert(offsetof(struct ara_akv_direct_lease, reserved) == 32, "reserved");
_Static_assert(ARA_AKV_DIRECT_GET_INFO == 0x80404bb0UL, "info ioctl");
_Static_assert(ARA_AKV_DIRECT_ACQUIRE == 0xc0404bb1UL, "acquire ioctl");
_Static_assert(ARA_AKV_DIRECT_RELEASE == 0x4bb2UL, "release ioctl");
_Static_assert(ARA_AKV_DIRECT_REQUIRED_FEATURES == 7, "features");

int main(void)
{
    const struct ara_akv_direct_lease good = {.abi = 1, .bytes = 64};
    struct ara_akv_direct_lease v;
    uint64_t seed = UINT64_C(0x2718281828459045);
    unsigned checks = 0;
    assert(akv_direct_valid_lease(&good));
    checks++;
    for (unsigned byte = 0; byte < sizeof(v); byte++) {
        for (unsigned bit = 0; bit < 8; bit++) {
            v = good;
            ((unsigned char *)&v)[byte] ^= (unsigned char)(1u << bit);
            assert(!akv_direct_valid_lease(&v));
            checks++;
        }
    }
    for (unsigned run = 0; run < 16384; run++) {
        v = good;
        seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
        unsigned byte = 8 + seed % 56;
        ((unsigned char *)&v)[byte] = (unsigned char)(1 + seed % 255);
        assert(!akv_direct_valid_lease(&v));
        checks++;
    }
    for (unsigned mode = 0; mode < 8; mode++) {
        uint64_t gate = UINT64_C(0x414b560100000000) | mode;
        assert(akv_direct_valid_gate(gate));
        checks++;
        for (unsigned bit = 3; bit < 64; bit++) {
            assert(!akv_direct_valid_gate(gate ^ (UINT64_C(1) << bit)));
            checks++;
        }
    }
    assert(!akv_direct_valid_gate(0));
    checks++;
    printf("AKV_DIRECT_HOST_POLICY_PASS checks=%u\n", checks);
    return 0;
}
