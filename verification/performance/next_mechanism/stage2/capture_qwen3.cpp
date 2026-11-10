// SPDX-License-Identifier: Apache-2.0
#include "llama.h"
#include "ggml-backend.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static constexpr unsigned rows = 8;
static unsigned captured = 0;

static void need(bool condition, const char *reason) {
    if (!condition) {
        std::fprintf(stderr, "STAGE2_CAPTURE_FAIL reason=%s\n", reason);
        std::exit(1);
    }
}

static bool capture(ggml_tensor *tensor, bool ask, void *opaque) {
    const bool attention = std::strcmp(tensor->name, "attn_norm-0") == 0;
    const bool ffn = std::strcmp(tensor->name, "ffn_norm-0") == 0;
    if (!attention && !ffn) return false;
    if (ask) return true;
    const int tokens = *static_cast<const int *>(opaque);
    need(tensor->type == GGML_TYPE_F32 && tensor->ne[0] == 2048 &&
         tensor->ne[1] == tokens && tensor->ne[2] == 1 && tensor->ne[3] == 1 &&
         ggml_is_contiguous(tensor) && tensor->nb[0] == 4 && tensor->nb[1] == 8192,
         "source_tensor_shape");
    need(captured == (attention ? 0u : 1u), "source_boundary_order");
    std::vector<float> data(rows*2048);
    ggml_backend_tensor_get(tensor, data.data(), 0, data.size()*sizeof(float));
    for (float value : data) need(std::isfinite(value), "nonfinite_activation");
    std::printf("STAGE2_CAPTURE_SHAPE source=%s k=2048 rows=%u tokens=%d type=f32\n",
                tensor->name, rows, tokens);
    for (unsigned row = 0; row < rows; ++row) {
        for (unsigned offset = 0; offset < 2048; offset += 16) {
            std::printf("STAGE2_CAPTURE_DATA source=%s row=%u offset=%u bits=",
                        tensor->name, row, offset);
            for (unsigned i = 0; i < 16; ++i) {
                uint32_t bits;
                std::memcpy(&bits, &data[row*2048+offset+i], sizeof(bits));
                std::printf("%08x", bits);
            }
            std::putchar('\n');
        }
    }
    captured++;
    if (ffn) {
        std::puts("STAGE2_CAPTURE_DONE tensors=2 rows=8 stop=before_first_ffn_projection");
        // Only collect actual GGML tensor values; do not run the remaining model.
        std::exit(0);
    }
    // A post-evaluation false aborts this GGML graph split.
    return true;
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    need(!setenv("GGML_RISCV_QBS", "0", 1) && !setenv("GGML_RISCV_AKV", "0", 1) &&
         !setenv("GGML_RISCV_AKV_QUANT_KV", "0", 1), "disable_accelerated_capture_paths");
    llama_backend_init();
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = 0;
    auto *model = llama_model_load_from_file("/model/models/Qwen3-1.7B-Q4_K_M.gguf", mp);
    need(model && llama_model_n_layer(model) == 28, "model_identity");
    const auto *vocab = llama_model_get_vocab(model);
    need(llama_vocab_n_tokens(vocab) == 151936, "vocabulary");
    const char prompt[] = "A vector processor executes the same operation on many data elements. Explain how quantized matrix multiplication and attention use this parallelism, and discuss the role of memory bandwidth when generating text with a language model.";
    std::vector<llama_token> tokens(256);
    int count = llama_tokenize(vocab, prompt, sizeof(prompt)-1,
                              tokens.data(), tokens.size(), true, true);
    need(count == 40, "fixed_prompt_tokens");
    tokens.resize(count);
    std::printf("STAGE2_CAPTURE_TOKENS count=%d ids=", count);
    for (int i = 0; i < count; ++i) std::printf("%s%d", i ? "," : "", tokens[i]);
    std::putchar('\n');
    auto cp = llama_context_default_params();
    cp.n_ctx = 128;
    cp.n_batch = cp.n_ubatch = 64;
    cp.n_threads = cp.n_threads_batch = 1;
    cp.type_k = cp.type_v = GGML_TYPE_F16;
    cp.cb_eval = capture;
    cp.cb_eval_user_data = &count;
    auto *ctx = llama_init_from_model(model, cp);
    need(ctx != nullptr, "context");
    asm volatile("csrwi fcsr,0;csrwi vcsr,0;csrwi vstart,0" ::: "memory");
    (void)llama_decode(ctx, llama_batch_get_one(tokens.data(), count));
    need(false, "capture_boundary_not_reached");
}
