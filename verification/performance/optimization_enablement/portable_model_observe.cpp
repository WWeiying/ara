#include "llama.h"
#include <cstdio>

extern "C" int32_t __real_llama_decode(llama_context *, llama_batch);
extern "C" llama_token __real_llama_sampler_sample(llama_sampler *, llama_context *, int32_t);

extern "C" int32_t __wrap_llama_decode(llama_context *ctx, llama_batch batch) {
    static unsigned step;
    unsigned bf, bv, bs, af, av, as;
    asm volatile("frcsr %0;csrr %1,vcsr;csrr %2,vstart" : "=r"(bf), "=r"(bv), "=r"(bs) :: "memory");
    if (bs) __builtin_trap();
    const int32_t rc = __real_llama_decode(ctx, batch);
    asm volatile("frcsr %0;csrr %1,vcsr;csrr %2,vstart" : "=r"(af), "=r"(av), "=r"(as) :: "memory");
    std::fprintf(stderr, "PORTABLE_DECODE step=%u rows=%d rc=%d before_fcsr=%u before_vcsr=%u before_vstart=%u fcsr=%u vcsr=%u vstart=%u\n",
                 step++, batch.n_tokens, rc, bf, bv, bs, af, av, as);
    return rc;
}

extern "C" llama_token __wrap_llama_sampler_sample(llama_sampler *sampler, llama_context *ctx, int32_t idx) {
    static unsigned step;
    const llama_token token = __real_llama_sampler_sample(sampler, ctx, idx);
    std::fprintf(stderr, "PORTABLE_TOKEN step=%u token=%d\n", step++, token);
    return token;
}
