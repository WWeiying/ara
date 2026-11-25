#define main original_prepare_cases
#include "test_prepare.c"
#undef main

static uint16_t sk[256 * 4 * 128] __attribute__((aligned(64)));
static uint16_t sv[256 * 4 * 128] __attribute__((aligned(64)));

int main(void)
{
    assert(original_prepare_cases() == 0);
    unsigned tested = 0;
    const unsigned tokens[] = {1, 63, 64, 65, 137, 256};
    for (unsigned d = 64; d <= 128; d += 32)
        for (unsigned factor = 1; factor <= 4; ++factor)
            for (unsigned ti = 0; ti < sizeof(tokens) / sizeof(tokens[0]); ++ti) {
                const unsigned stride = d * factor;
                for (unsigned i = 0; i < sizeof(sk) / sizeof(sk[0]); ++i) sk[i] = sv[i] = 0x7e00;
                for (unsigned t = 0; t < tokens[ti]; ++t)
                    for (unsigned i = 0; i < d; ++i) sk[t * stride + i] = sv[t * stride + i] = 0x3c00;
                struct ara_resident_compute_buffers b = {
                    .query=q, .key=sk, .value=sv, .mask=mask, .output=output,
                    .scratch=&scratch, .scratch_bytes=sizeof(scratch),
                    .heads=2, .dimension=d, .tokens=tokens[ti], .scale_bits=0x3e000000,
                    .flags=ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS,
                    .key_token_stride=stride * 2, .value_token_stride=stride * 2,
                };
                init_caps();
                assert(validate_buffers(&b) == 0);
                assert(validate_domain(&b) == 0);
                assert(prepare_compute(&b, &scratch, 128, 0, 0) == 0);
                assert(scratch.plan.descriptor.k_token_stride_bytes == stride * 2);
                assert(scratch.plan.descriptor.v_token_stride_bytes == stride * 2);
                unsigned last = (tokens[ti] - 1) * stride + d - 1;
                sk[last] = 0x7e00;
                assert(validate_domain(&b) == -ARA_EOPNOTSUPP);
                sk[last] = 0x3c00; sv[last] = 0xfc00;
                assert(validate_domain(&b) == -ARA_EOPNOTSUPP);
                sv[last] = 0x3c00;
                b.key_token_stride += 2;
                assert(validate_buffers(&b) == -ARA_EINVAL);
                b.key_token_stride = d * 2 - 64;
                assert(validate_buffers(&b) == -ARA_EINVAL);
                ++tested;
            }
    printf("PASS strided compute: %u shapes; NaN padding ignored, live active rows checked, descriptor strides retained\n", tested);
    return 0;
}
