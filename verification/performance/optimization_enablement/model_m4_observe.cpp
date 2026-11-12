#include "llama.h"
#include <cstdio>
#include <cstdlib>

extern "C" int32_t __real_llama_decode(llama_context *, llama_batch);
extern "C" llama_token __real_llama_sampler_sample(llama_sampler *, llama_context *, int32_t);

extern "C" int32_t __wrap_llama_decode(llama_context *ctx, llama_batch batch) {
    static unsigned step;
    unsigned before;
    asm volatile("csrr %0,vstart" : "=r"(before) :: "memory");
    if (before) __builtin_trap();
    const int32_t rc = __real_llama_decode(ctx, batch);
    unsigned fc, vc, start;
    asm volatile("frcsr %0;csrr %1,vcsr;csrr %2,vstart"
                 : "=r"(fc), "=r"(vc), "=r"(start) :: "memory");
    std::fprintf(stderr, "M4_DECODE step=%u rows=%d rc=%d fcsr=%u vcsr=%u vstart=%u\n",
                 step++, batch.n_tokens, rc, fc, vc, start);
    return rc;
}

extern "C" llama_token __wrap_llama_sampler_sample(llama_sampler *sampler, llama_context *ctx, int32_t idx) {
    static unsigned step;
    const llama_token token = __real_llama_sampler_sample(sampler, ctx, idx);
    std::fprintf(stderr, "M4_TOKEN step=%u token=%d\n", step++, token);
    return token;
}
