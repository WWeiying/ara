#include "llama.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

static void need(bool ok, const char *why) {
    if (!ok) { std::fprintf(stderr, "M4_SUMS_MODEL_FAIL reason=%s\n", why); std::exit(1); }
}
static void env(const char *key, const char *value) { need(!setenv(key, value, 1), "environment"); }
static void write(FILE *f, const void *p, size_t n) { need(std::fwrite(p, 1, n, f) == n, "write"); }
static void read(FILE *f, void *p, size_t n) { need(std::fread(p, 1, n, f) == n, "read"); }

static void generate(unsigned mode, const char *output) {
    env("GGML_RISCV_QBS", "1"); env("GGML_RISCV_QBS_EMULATE", "0");
    env("GGML_RISCV_QBS_TRACE", "1"); env("GGML_RISCV_QBS_TRACE_CALLS", "1");
    env("GGML_RISCV_QBS_M4_PREPARE", "1");
    env("GGML_RISCV_QBS_TRACE_M4_PREPARE", "1");
    env("GGML_RISCV_QBS_WIDE_M", "0"); env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "1");
    env("GGML_RISCV_QBS_M4_CACHE", "1");
    env("GGML_RISCV_QBS_M4_PACKED", "1");
    env("GGML_RISCV_QBS_TRACE_LIFETIME", "1");
    env("GGML_RISCV_QBS_ACTIVATION_CONTEXT", "1");
    env("GGML_RISCV_AKV", "0"); env("GGML_RISCV_AKV_EMULATE", "0");
    env("GGML_RISCV_AKV_QUANT_KV", "1"); env("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1");
    env("GGML_RISCV_AKV_QUANT_PREFILL", "1");
    env("GGML_RISCV_AKV_REGISTER_PV", "1");
    env("GGML_RISCV_QBS_M4_PARALLEL_SUMS", mode ? "1" : "0");
    env("GGML_RISCV_AKV_GROUPED_PV", "0"); env("GGML_RISCV_AKV_TRACE", "1");
    std::printf("M4_SUMS_MODEL_BEGIN enabled=%u\n", mode);
    llama_backend_init();
    auto mp = llama_model_default_params(); mp.n_gpu_layers = 0;
    auto *model = llama_model_load_from_file("/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf", mp);
    need(model && llama_model_n_layer(model) == 28, "model");
    auto *vocab = llama_model_get_vocab(model);
    const uint32_t count = llama_vocab_n_tokens(vocab);
    need(count == 151936, "vocabulary");
    const char prompt[] = "The quick brown fox";
    std::vector<llama_token> tokens(32);
    const int n = llama_tokenize(vocab, prompt, sizeof(prompt)-1, tokens.data(), tokens.size(), true, true);
    need(n == 4, "prompt"); tokens.resize(n);
    FILE *f = std::fopen(output, "wb"); need(f, "open_output");
    write(f, &count, sizeof(count));
    for (unsigned kind = 0; kind < 2; ++kind) {
        auto cp = llama_context_default_params();
        cp.n_ctx = 128; cp.n_batch = cp.n_ubatch = 32;
        cp.n_threads = cp.n_threads_batch = 1;
        cp.type_k = kind ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0; cp.type_v = GGML_TYPE_Q8_0;
        cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
        auto *ctx = llama_init_from_model(model, cp); need(ctx, "context");
        auto input = tokens;
        for (unsigned step = 0; step < 3; ++step) {
            asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
            need(llama_decode(ctx, llama_batch_get_one(input.data(), input.size())) == 0, "decode");
            uintptr_t fc, vc;
            asm volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc), "=r"(vc) :: "memory");
            need(fc <= 31 && (fc & 8) && vc <= 7, "csr");
            const float *logits = llama_get_logits_ith(ctx, -1); need(logits, "logits");
            for (uint32_t i = 0; i < count; ++i) need(std::isfinite(logits[i]), "finite");
            const llama_token token = std::max_element(logits, logits + count) - logits;
            need(!llama_vocab_is_eog(vocab, token), "early_eog");
            write(f, &token, sizeof(token)); write(f, &fc, sizeof(fc)); write(f, &vc, sizeof(vc));
            write(f, logits, count*sizeof(float));
            std::printf("M4_SUMS_MODEL_STEP enabled=%u kind=%u step=%u token=%d fcsr=%lu vcsr=%lu outputs=%u\n",
                        mode, kind, step, token, (unsigned long)fc, (unsigned long)vc, count);
            input.assign(1, token);
        }
        llama_free(ctx);
    }
    need(!std::fclose(f), "close");
    llama_model_free(model); llama_backend_free();
    std::printf("M4_SUMS_MODEL_END enabled=%u\n", mode);
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0); std::setvbuf(stderr, nullptr, _IONBF, 0);
    const char *paths[] = {"/tmp/register25-off.bin", "/tmp/register25-on.bin"};
    // Parent never enters GGML: cached environment choices initialize independently in each child.
    for (unsigned mode = 0; mode < 2; ++mode) {
        const pid_t child = fork(); need(child >= 0, "fork");
        if (!child) { generate(mode, paths[mode]); std::exit(0); }
        int status = 0;
        need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "child");
    }
    FILE *a = std::fopen(paths[0], "rb"), *b = std::fopen(paths[1], "rb"); need(a && b, "paired_files");
    uint32_t na, nb; read(a, &na, sizeof(na)); read(b, &nb, sizeof(nb));
    need(na == 151936 && na == nb, "paired_vocabulary");
    std::vector<float> va(na), vb(nb);
    for (unsigned record = 0; record < 6; ++record) {
        llama_token ta, tb; uintptr_t fa, fb, ca, cb;
        read(a, &ta, sizeof(ta)); read(b, &tb, sizeof(tb));
        read(a, &fa, sizeof(fa)); read(b, &fb, sizeof(fb));
        read(a, &ca, sizeof(ca)); read(b, &cb, sizeof(cb));
        read(a, va.data(), na*sizeof(float)); read(b, vb.data(), nb*sizeof(float));
        need(ta == tb && fa == fb && ca == cb, "paired_token_csr");
        need(!std::memcmp(va.data(), vb.data(), na*sizeof(float)), "paired_logits");
        std::printf("M4_SUMS_MODEL_COMPARE kind=%u step=%u outputs=%u bitwise=1 csr_equal=1 token_equal=1\n",
                    record/3, record%3, na);
    }
    need(std::fgetc(a) == EOF && std::fgetc(b) == EOF && !std::ferror(a) && !std::ferror(b), "extra_records");
    std::fclose(a); std::fclose(b);
    std::puts("M4_SUMS_MODEL_SUITE_PASS comparisons=6 performance=not_measured");
    return 0;
}
