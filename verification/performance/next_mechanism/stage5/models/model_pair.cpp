// Successor of sums_model_test.cpp. Numerical evidence only; route audit is separate.
#include "llama.h"
#include "case_config.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

#ifndef STAGE5_REVIEWED_RESIDENT_ENV
#error "Bind the independently reviewed resident-only selector before building a runnable pair"
#endif

static void need(bool ok, const char *reason) {
    if (!ok) { std::fprintf(stderr, "STAGE5_MODEL_FAIL case=%s reason=%s\n", case_id, reason); std::exit(1); }
}
static void put(FILE *f, const void *p, size_t n) { need(std::fwrite(p, 1, n, f) == n, "write"); }
static void get(FILE *f, void *p, size_t n) { need(std::fread(p, 1, n, f) == n, "read"); }
static void env(const char *key, const char *value) { need(setenv(key, value, 1) == 0, "environment"); }

static void generate(unsigned mode, const char *path) {
    // Each child starts without ambient runtime switches or cached GGML state.
    need(clearenv() == 0, "clearenv");
    env("PATH", "/bin:/usr/bin"); env("LC_ALL", "C");
    for (const auto &entry : common_environment) {
        need(std::strcmp(entry.key, STAGE5_REVIEWED_RESIDENT_ENV) != 0, "selector_is_not_a_fixed_switch");
        env(entry.key, entry.value);
    }
    env(STAGE5_REVIEWED_RESIDENT_ENV, mode ? "1" : "0");
    std::printf("STAGE5_MODEL_BEGIN case=%s requested=%u\n", case_id, mode);
    llama_backend_init();
    auto mp = llama_model_default_params(); mp.n_gpu_layers = 0;
    auto *model = llama_model_load_from_file(model_path, mp);
    need(model && llama_model_n_layer(model) == expected_layers, "model");
    auto *vocab = llama_model_get_vocab(model);
    const uint32_t count = llama_vocab_n_tokens(vocab);
    need(count == expected_vocab, "vocabulary");
    std::vector<llama_token> all(8192);
    const int n = llama_tokenize(vocab, source_text, std::strlen(source_text), all.data(),
                                 all.size(), true, false);
    need(n == int(sizeof(source_tokens) / sizeof(source_tokens[0])), "tokenizer_length");
    need(std::equal(all.begin(), all.begin() + n, source_tokens), "tokenizer_identity");
    need(std::equal(frozen_tokens, frozen_tokens + prompt_tokens + 2, all.begin()), "frozen_prefix");
    for (unsigned i = 0; i < prompt_tokens + 2; ++i)
        need(!llama_vocab_is_eog(vocab, frozen_tokens[i]), "input_eog");

    auto cp = llama_context_default_params();
    cp.n_ctx = context_capacity; cp.n_batch = cp.n_ubatch = context_capacity;
    cp.n_threads = cp.n_threads_batch = 1;
    cp.type_k = cache_k; cp.type_v = cache_v;
    cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    auto *ctx = llama_init_from_model(model, cp); need(ctx, "context");
    need(llama_n_ctx(ctx) == effective_context_capacity, "effective_context_capacity");
    std::printf("STAGE5_CONTEXT case=%s requested=%u n_ctx_requested=%u n_ctx_effective=%u\n",
                case_id, mode, context_capacity, llama_n_ctx(ctx));
    FILE *f = std::fopen(path, "wb"); need(f, "open");
    put(f, &count, sizeof(count));
    for (unsigned step = 0; step < 3; ++step) {
        std::vector<llama_token> input;
        if (step == 0) input.assign(frozen_tokens, frozen_tokens + prompt_tokens);
        else input.assign(1, frozen_tokens[prompt_tokens + step - 1]);
        std::printf("STAGE5_STEP_BEGIN case=%s requested=%u step=%u input_rows=%zu logical_context=%u\n",
                    case_id, mode, step, input.size(), prompt_tokens + step);
        asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
        const int rc = llama_decode(ctx, llama_batch_get_one(input.data(), input.size()));
        uintptr_t fc, vc, vs;
        asm volatile("frcsr %0;csrr %1,vcsr;csrr %2,vstart" : "=r"(fc), "=r"(vc), "=r"(vs) :: "memory");
        need(rc == 0 && fc <= 31 && (fc & 8) && vc <= 7 && vs == 0, "decode_csr");
        const float *logits = llama_get_logits_ith(ctx, -1); need(logits, "logits");
        for (uint32_t i = 0; i < count; ++i) need(std::isfinite(logits[i]), "finite");
        const llama_token token = std::max_element(logits, logits + count) - logits;
        put(f, &token, sizeof(token)); put(f, &fc, sizeof(fc)); put(f, &vc, sizeof(vc)); put(f, &vs, sizeof(vs));
        put(f, logits, count * sizeof(float));
        std::printf("STAGE5_STEP_END case=%s requested=%u step=%u greedy=%d fcsr=%lu vcsr=%lu vstart=%lu outputs=%u\n",
                    case_id, mode, step, token, (unsigned long)fc, (unsigned long)vc, (unsigned long)vs, count);
    }
    need(std::fclose(f) == 0, "close");
    llama_free(ctx); llama_model_free(model); llama_backend_free();
    std::printf("STAGE5_MODEL_END case=%s requested=%u\n", case_id, mode);
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0); std::setvbuf(stderr, nullptr, _IONBF, 0);
    const char *paths[] = {"/tmp/stage5-off.bin", "/tmp/stage5-on.bin"};
    for (unsigned mode = 0; mode < 2; ++mode) {
        const pid_t child = fork(); need(child >= 0, "fork");
        if (!child) { generate(mode, paths[mode]); std::exit(0); }
        int status = 0;
        need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "child");
    }
    FILE *a = std::fopen(paths[0], "rb"), *b = std::fopen(paths[1], "rb"); need(a && b, "pair");
    uint32_t na, nb; get(a, &na, sizeof(na)); get(b, &nb, sizeof(nb));
    need(na == expected_vocab && na == nb, "paired_vocabulary");
    std::vector<float> va(na), vb(nb);
    for (unsigned step = 0; step < 3; ++step) {
        llama_token ta, tb; uintptr_t fa, fb, ca, cb, sa, sb;
        get(a, &ta, sizeof(ta)); get(b, &tb, sizeof(tb));
        get(a, &fa, sizeof(fa)); get(b, &fb, sizeof(fb));
        get(a, &ca, sizeof(ca)); get(b, &cb, sizeof(cb));
        get(a, &sa, sizeof(sa)); get(b, &sb, sizeof(sb));
        get(a, va.data(), na * sizeof(float)); get(b, vb.data(), nb * sizeof(float));
        need(ta == tb && fa == fb && ca == cb && sa == sb, "paired_token_csr");
        need(std::memcmp(va.data(), vb.data(), na * sizeof(float)) == 0, "paired_logits");
        std::printf("STAGE5_NUMERICAL_COMPARE case=%s step=%u outputs=%u bitwise=1 csr_equal=1 token_equal=1\n",
                    case_id, step, na);
    }
    need(std::fgetc(a) == EOF && std::fgetc(b) == EOF && !std::ferror(a) && !std::ferror(b), "extra_records");
    std::fclose(a); std::fclose(b);
    std::printf("STAGE5_NUMERICAL_PAIR_ONLY case=%s comparisons=3 route_audit_required=1 performance=not_measured\n", case_id);
}
