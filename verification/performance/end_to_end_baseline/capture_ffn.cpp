#include "llama.h"
#include "ggml-backend.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void need(bool condition, const char *reason) {
    if (!condition) { std::fprintf(stderr, "FFN_CAPTURE_FAIL reason=%s\n", reason); std::exit(1); }
}
static void env(const char *key, const char *value) { need(!setenv(key, value, 1), "environment"); }
#include "capture_environment.h"

static const char *names[] = {"attn_norm-0", "ffn_norm-0", "ffn_swiglu-0"};
static const unsigned widths[] = {2048, 2048, 6144};
static unsigned captured = 0;

static bool capture(ggml_tensor *tensor, bool ask, void *) {
    unsigned part = 0;
    while (part < 3 && std::strcmp(tensor->name, names[part])) ++part;
    if (part == 3) return false;
    if (ask) return true;
    need(part == captured, "boundary_order");
    const unsigned k = widths[part];
    need(tensor->type == GGML_TYPE_F32 && tensor->ne[0] == k && tensor->ne[1] == 40 &&
         tensor->ne[2] == 1 && tensor->ne[3] == 1 && ggml_is_contiguous(tensor) &&
         tensor->nb[0] == 4 && tensor->nb[1] == k*4, "tensor_shape_or_layout");
    std::vector<float> data(4*k);
    ggml_backend_tensor_get(tensor, data.data(), 0, data.size()*sizeof(float));
    for (float value : data) need(std::isfinite(value), "nonfinite_activation");
    std::printf("FFN_CAPTURE_SHAPE source=%s k=%u rows=4 tokens=40 type=f32\n", names[part], k);
    for (unsigned row = 0; row < 4; ++row) {
        for (unsigned offset = 0; offset < k; offset += 16) {
            std::printf("FFN_CAPTURE_DATA source=%s row=%u offset=%u bits=", names[part], row, offset);
            for (unsigned i = 0; i < 16; ++i) {
                uint32_t bits; std::memcpy(&bits, &data[row*k+offset+i], sizeof(bits));
                std::printf("%08x", bits);
            }
            std::putchar('\n');
        }
    }
    if (++captured == 3) {
        std::puts("FFN_CAPTURE_DONE sources=3 bytes=163840 stop=before_first_down performance=not_measured");
        // First-layer data capture, not a successful complete model inference.
        std::exit(0);
    }
    return true;
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0); std::setvbuf(stderr, nullptr, _IONBF, 0);
    configure_capture();
    std::puts("FFN_CAPTURE_SCOPE model=qwen3_1p7b layer=0 qbs=1 kv=q8_0 trace=1");
    llama_backend_init();
    auto mp = llama_model_default_params(); mp.n_gpu_layers = 0;
    auto *model = llama_model_load_from_file("/model/models/Qwen3-1.7B-Q4_K_M.gguf", mp);
    need(model && llama_model_n_layer(model) == 28, "model");
    auto *vocab = llama_model_get_vocab(model); need(llama_vocab_n_tokens(vocab) == 151936, "vocabulary");
    const char prompt[] = "A vector processor executes the same operation on many data elements. Explain how quantized matrix multiplication and attention use this parallelism, and discuss the role of memory bandwidth when generating text with a language model.";
    std::vector<llama_token> tokens(256);
    const int count = llama_tokenize(vocab, prompt, sizeof(prompt)-1, tokens.data(), tokens.size(), true, true);
    need(count == 40, "fixed_prompt_tokens"); tokens.resize(count);
    std::printf("FFN_CAPTURE_TOKENS count=40 ids=");
    for (int i = 0; i < count; ++i) std::printf("%s%d", i ? "," : "", tokens[i]);
    std::putchar('\n');
    auto cp = llama_context_default_params();
    cp.n_ctx = 128; cp.n_batch = cp.n_ubatch = 64; cp.n_threads = cp.n_threads_batch = 1;
    cp.type_k = cp.type_v = GGML_TYPE_Q8_0; cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    cp.cb_eval = capture;
    auto *ctx = llama_init_from_model(model, cp); need(ctx, "context");
    asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
    (void)llama_decode(ctx, llama_batch_get_one(tokens.data(), count));
    need(false, "missing_capture_boundary");
}
