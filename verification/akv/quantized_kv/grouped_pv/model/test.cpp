#include "llama.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static void require(bool value, const char * reason) {
    if (!value) {
        std::fprintf(stderr, "GROUPED_MODEL_FAIL reason=%s\n", reason);
        std::exit(1);
    }
}

static void option(const char * name, const char * value) {
    require(setenv(name, value, 1) == 0, "setenv");
}

struct generation {
    std::vector<llama_token> tokens;
    std::vector<std::vector<float>> logits;
    std::vector<uintptr_t> fcsr, vcsr;
};

static generation generate(llama_model * model, bool q4, bool grouped, const std::vector<llama_token> & prompt) {
    option("GGML_RISCV_AKV_QUANT_KV", "1");
    if (grouped) option("GGML_RISCV_AKV_GROUPED_PV", "1");
    else require(unsetenv("GGML_RISCV_AKV_GROUPED_PV") == 0, "unset_grouped");
    llama_context_params params = llama_context_default_params();
    params.n_ctx = 128;
    params.n_batch = 32;
    params.n_ubatch = 32;
    params.n_threads = params.n_threads_batch = 1;
    params.type_k = q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0;
    params.type_v = GGML_TYPE_Q8_0;
    params.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    llama_context * ctx = llama_init_from_model(model, params);
    require(ctx, "context_init");
    const llama_vocab * vocab = llama_model_get_vocab(model);
    const int count = llama_vocab_n_tokens(vocab);
    require(count > 1, "vocabulary");
    const char * kind = q4 ? "q4_0" : "q8_0";
    const char * mode = grouped ? "candidate" : "baseline";
    std::printf("GROUPED_MODEL_BEGIN kind=%s mode=%s layers=%d prompt_tokens=%zu generated=3 context=128 threads=1\n", kind, mode, llama_model_n_layer(model), prompt.size());
    auto input = prompt;
    generation result;
    for (unsigned step = 0; step < 3; ++step) {
        const auto batch = llama_batch_get_one(input.data(), static_cast<int32_t>(input.size()));
        uintptr_t fcsr, vcsr;
        __asm__ volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" : : : "memory");
        const int status = llama_decode(ctx, batch);
        __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fcsr), "=r"(vcsr) : : "memory");
        std::printf("GROUPED_MODEL_CSR kind=%s mode=%s step=%u flags=%lu vcsr=%lu\n",
                    kind, mode, step, static_cast<unsigned long>(fcsr), static_cast<unsigned long>(vcsr));
        require(status == 0, "decode");
        require((fcsr & ~uintptr_t(31)) == 0 && (fcsr & 8u) && vcsr == 5, "decode_csr_preservation");
        result.fcsr.push_back(fcsr);
        result.vcsr.push_back(vcsr);
        const float * logits = llama_get_logits_ith(ctx, -1);
        require(logits, "logits");
        result.logits.emplace_back(logits, logits + count);
        for (float value : result.logits.back()) require(std::isfinite(value), "nonfinite_logit");
        const auto token = static_cast<llama_token>(std::max_element(logits, logits + count) - logits);
        require(!llama_vocab_is_eog(vocab, token), "early_eog_in_fixed_smoke_prompt");
        result.tokens.push_back(token);
        char piece[512];
        const int length = llama_token_to_piece(vocab, token, piece, sizeof(piece), 0, true);
        require(length >= 0 && length <= static_cast<int>(sizeof(piece)), "token_piece");
        std::printf("GROUPED_MODEL_TOKEN kind=%s mode=%s step=%u token=%d piece_hex=", kind, mode, step, token);
        for (int i = 0; i < length; ++i) std::printf("%02x", static_cast<unsigned char>(piece[i]));
        std::printf("\n");
        input.assign(1, token);
    }
    std::printf("GROUPED_MODEL_END kind=%s mode=%s generated=3 vocab=%d\n", kind, mode, count);
    llama_free(ctx);
    return result;
}

static void compare(const generation & baseline, const generation & candidate, const char * kind) {
    require(baseline.tokens.size() == 3 && candidate.tokens.size() == 3, "generation_count");
    for (unsigned step = 0; step < 3; ++step) {
        const auto & a = baseline.logits[step];
        const auto & b = candidate.logits[step];
        require(a.size() == b.size() && !a.empty(), "paired_vocabulary");
        require(!std::memcmp(a.data(), b.data(), a.size() * sizeof(float)), "full_logits_bits_changed");
        if (baseline.fcsr[step] != candidate.fcsr[step] || baseline.vcsr[step] != candidate.vcsr[step])
            std::fprintf(stderr, "GROUPED_MODEL_CSR_DIAG kind=%s step=%u baseline_fcsr=%lu candidate_fcsr=%lu baseline_vcsr=%lu candidate_vcsr=%lu\n",
                         kind, step, static_cast<unsigned long>(baseline.fcsr[step]),
                         static_cast<unsigned long>(candidate.fcsr[step]), static_cast<unsigned long>(baseline.vcsr[step]),
                         static_cast<unsigned long>(candidate.vcsr[step]));
        require(baseline.fcsr[step] == candidate.fcsr[step] &&
                baseline.vcsr[step] == candidate.vcsr[step], "paired_decode_csr_changed");
        double square = 0, maximum = 0, sum_a = 0, sum_b = 0;
        const double max_a = *std::max_element(a.begin(), a.end());
        const double max_b = *std::max_element(b.begin(), b.end());
        for (size_t i = 0; i < a.size(); ++i) {
            const double difference = double(a[i]) - b[i];
            square += difference * difference;
            maximum = std::max(maximum, std::fabs(difference));
            sum_a += std::exp(double(a[i]) - max_a);
            sum_b += std::exp(double(b[i]) - max_b);
        }
        const double log_a = max_a + std::log(sum_a), log_b = max_b + std::log(sum_b);
        double kl = 0;
        for (size_t i = 0; i < a.size(); ++i) {
            const double p = double(a[i]) - log_a;
            kl += std::exp(p) * (p - (double(b[i]) - log_b));
        }
        const bool equal = baseline.tokens[step] == candidate.tokens[step];
        std::printf("GROUPED_MODEL_COMPARE kind=%s step=%u common_prefix=1 top1_equal=%u outputs=%zu bitwise=1 csr_equal=1 max_abs=%.9g rmse=%.9g kl=%.9g\n", kind, step, unsigned(equal), a.size(), maximum, std::sqrt(square / a.size()), kl);
        // Equality at each earlier step establishes the next step's common input.
        require(equal, "greedy_trajectory_changed");
    }
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    option("GGML_RISCV_QBS", "1");
    option("GGML_RISCV_QBS_EMULATE", "0");
    option("GGML_RISCV_QBS_TRACE", "1");
    option("GGML_RISCV_QBS_TRACE_CALLS", "1");
    option("GGML_RISCV_QBS_WIDE_M", "0");
    option("GGML_RISCV_AKV", "0");
    option("GGML_RISCV_AKV_EMULATE", "0");
    option("GGML_RISCV_AKV_TRACE", "1");
    option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1");
    require(unsetenv("GGML_RISCV_AKV_GROUPED_PV") == 0, "initial_unset_grouped");
    llama_backend_init();
    auto params = llama_model_default_params();
    params.n_gpu_layers = 0;
    const char * path = "/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf";
    llama_model * model = llama_model_load_from_file(path, params);
    require(model, "model_load");
    require(llama_model_n_layer(model) == 28, "unexpected_model_layers");
    const llama_vocab * vocab = llama_model_get_vocab(model);
    const std::string prompt = "The quick brown fox";
    const int count = -llama_tokenize(vocab, prompt.data(), static_cast<int32_t>(prompt.size()), nullptr, 0, true, true);
    require(count > 1 && count <= 32, "prompt_size");
    std::vector<llama_token> tokens(count);
    require(llama_tokenize(vocab, prompt.data(), static_cast<int32_t>(prompt.size()), tokens.data(), count, true, true) == count, "tokenization");
    for (bool q4 : {false, true}) {
        const auto baseline = generate(model, q4, false, tokens);
        const auto candidate = generate(model, q4, true, tokens);
        compare(baseline, candidate, q4 ? "q4_0" : "q8_0");
    }
    llama_model_free(model);
    llama_backend_free();
    std::puts("GROUPED_MODEL_SUITE_PASS profiles=2 generations=4 tokens_each=3 common_greedy_trajectory=1 baseline=qbs_attention_grouped_default_off performance=not_measured");
}
