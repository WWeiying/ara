#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "kernel_compute.c"

static unsigned short q[8 * 128] __attribute__((aligned(64)));
static unsigned short k[256 * 128] __attribute__((aligned(64)));
static unsigned short v[256 * 128] __attribute__((aligned(64)));
static unsigned short mask[256] __attribute__((aligned(64)));
static float output[8 * 128] __attribute__((aligned(64)));
static struct ara_compute_scratch scratch;

static uint64_t words[5];
static uint64_t reader(void *unused, unsigned index)
{
    (void)unused;
    assert(index < 5);
    return words[index];
}

static void init_caps(void)
{
    for (unsigned i = 0; i < 4; ++i) {
        words[i] = akv_capability_word(i, 1);
        if (words[i] == 0)
            words[i] = akv_v2_capability_word(i, 1);
    }
    words[4] = AKV_RESIDENT_CAPABILITY_BASE_WORD | AKV_RESIDENT_CAPABILITY_SUPPORT_MASK;
    assert(akv_device_query(reader, NULL, &scratch.device) == AKV_STATUS_OK);
}

int main(void)
{
    struct ara_resident_compute_buffers b = {
        .query = q, .key = k, .value = v, .mask = mask, .output = output,
        .scratch = &scratch, .scratch_bytes = sizeof(scratch),
        .heads = 1, .dimension = 64, .tokens = 1, .scale_bits = 0x3e000000,
        .flags = ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS,
    };
    unsigned shapes = 0;
    init_caps();
    for (unsigned h = 1; h <= 8; ++h)
        for (unsigned d = 64; d <= 128; d += 32)
            for (unsigned t = 1; t <= 256; ++t) {
                b.heads = h; b.dimension = d; b.tokens = t;
                assert(validate_buffers(&b) == 0);
                assert(prepare_compute(&b, &scratch, 128, 0, 0) == 0);
                assert(scratch.plan.descriptor.q_rows == h);
                assert(scratch.plan.descriptor.head_dim == d);
                assert(scratch.schedule.tail.tokens == ((t - 1) % 64 + 1));
                assert(b.started == 0 && b.resident_used == 0);
                ++shapes;
            }
    for (unsigned flags = 0; flags < 7; ++flags) {
        b.flags = flags;
        assert(ara_resident_compute(&b) == -ARA_EOPNOTSUPP);
        assert(b.started == 0);
    }
    b.flags = 7;
    assert(validate_domain(&b) == 0);
    for (unsigned mode = 0; mode != 5; ++mode) {
        words[4] = mode == 0 ? 0 : mode == 1 ? AKV_RESIDENT_CAPABILITY_BASE_WORD |
            (1u << AKV_RESIDENT_CAPABILITY_PV_SUPPORTED_BIT) :
            mode == 2 ? AKV_RESIDENT_CAPABILITY_BASE_WORD |
            (1u << AKV_RESIDENT_CAPABILITY_QK_SUPPORTED_BIT) :
            mode == 3 ? UINT64_MAX : (AKV_RESIDENT_CAPABILITY_BASE_WORD |
            AKV_RESIDENT_CAPABILITY_SUPPORT_MASK) ^ 2;
        assert(akv_device_query(reader, NULL, &scratch.device) == AKV_STATUS_OK);
        assert(prepare_compute(&b, &scratch, 128, 0, 0) == -ARA_EOPNOTSUPP);
    }
    init_caps();
    assert(prepare_compute(&b, &scratch, 64, 0, 0) == -ARA_EOPNOTSUPP);
    assert(prepare_compute(&b, &scratch, 128, 1, 0) == -ARA_EOPNOTSUPP);
    assert(prepare_compute(&b, &scratch, 128, 0, 1) == -ARA_EOPNOTSUPP);

    b.heads = 1; b.dimension = 64; b.tokens = 1;
    for (unsigned u = 0; u < 65536; ++u) {
        q[0] = k[0] = v[0] = (uint16_t)u;
        assert(validate_domain(&b) ==
               ((u & 0x7c00u) == 0x7c00u ? -ARA_EOPNOTSUPP : 0));
    }
    q[0] = k[0] = v[0] = 0;
    b.tokens = 2;
    for (unsigned u = 0; u < 65536; ++u) {
        mask[0] = (uint16_t)u;
        assert(validate_domain(&b) ==
               ((u & 0x7c00u) == 0x7c00u && u != 0xfc00u ? -ARA_EOPNOTSUPP : 0));
    }
    mask[0] = mask[1] = 0xfc00;
    assert(validate_domain(&b) == -ARA_EOPNOTSUPP);
    assert(ara_resident_compute(&b) == -ARA_EOPNOTSUPP && b.started == 0);
    mask[1] = 0;
    assert(validate_domain(&b) == 0);
    mask[0] = 0;
    b.scale_bits = 0x3f800001;
    assert(validate_domain(&b) == -ARA_EOPNOTSUPP);
    assert(ara_resident_compute(&b) == -ARA_EOPNOTSUPP && b.started == 0);
    b.scale_bits = 0x3f800000;
    assert(validate_domain(&b) == 0);
    b.scale_bits = 1;
    assert(validate_domain(&b) == 0);
    b.scale_bits = 0x3e000000;
    for (unsigned array = 0; array < 4; ++array) {
        uint16_t *p = array == 0 ? q : array == 1 ? k : array == 2 ? v : mask;
        for (unsigned u = 0x7c00; u <= 0x7fff; ++u) {
            p[0] = (uint16_t)u;
            assert(ara_resident_compute(&b) == -ARA_EOPNOTSUPP);
            assert(b.started == 0 && b.resident_used == 0);
        }
        p[0] = 0xfc00;
        assert(validate_domain(&b) == (array == 3 ? 0 : -ARA_EOPNOTSUPP));
        p[0] = 0;
    }
    for (unsigned i = 0; i < 64; ++i)
        q[i] = k[i] = v[i] = 0x7bff;
    mask[0] = 0x7bff;
    b.scale_bits = 0x3f800000;
    assert(validate_domain(&b) == 0);
    memset(q, 0, sizeof(q)); memset(k, 0, sizeof(k)); memset(v, 0, sizeof(v));
    memset(mask, 0, sizeof(mask));
    b.scale_bits = 0x3e000000;
    b.heads = 0;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.heads = 9;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.heads = 8; b.dimension = 256;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.dimension = 128; b.tokens = 257;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.tokens = 256; b.scale_bits = 0x7f800000;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.scale_bits = 0x3e000000; b.output = q;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.output = output; b.scratch_bytes--;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.scratch_bytes++; b.query = (char *)q + 2;
    assert(ara_resident_compute(&b) == -ARA_EINVAL);
    b.query = q; b.started = 1;
    assert(ara_resident_compute(&b) == -ARA_EIO && b.started == 1);
    assert(ara_resident_compute(NULL) == -ARA_EINVAL);
    printf("PASS: %u shapes; all 65536 F16 data/mask encodings; scale/all-mask/domain rejection; fail-closed caps, state, aliases, no retry; scratch=%zu\n",
           shapes, ara_resident_compute_scratch_bytes());
    return 0;
}
