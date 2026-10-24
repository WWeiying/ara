#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

static std::vector<unsigned char> load(const std::string & path, size_t bytes) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    assert(file && file.tellg() == static_cast<std::streamoff>(bytes));
    file.seekg(0);
    std::vector<unsigned char> result(bytes);
    file.read(reinterpret_cast<char *>(result.data()), bytes);
    assert(file.good());
    return result;
}

static float compare(const float * actual, const float * expected) {
    float maximum = 0;
    for (unsigned i = 0; i < 1536; ++i) {
        assert(std::isfinite(actual[i]) && std::isfinite(expected[i]));
        const float error = std::fabs(actual[i] - expected[i]);
        assert(error <= 0.004f + 0.002f * std::fabs(expected[i]));
        if (error > maximum) maximum = error;
    }
    return maximum;
}

static uintptr_t compute(ggml_context * ctx, ggml_cgraph * graph, int threads) {
    __asm__ volatile("csrwi fcsr,0;csrwi vcsr,5" : : : "memory");
    assert(ggml_graph_compute_with_ctx(ctx, graph, threads) == GGML_STATUS_SUCCESS);
    uintptr_t flags;
    __asm__ volatile("frcsr %0" : "=r"(flags));
    return flags;
}

static void profile(bool q4) {
    const char * name = q4 ? "q4_0" : "q8_0";
    const std::string directory = q4 ? "/q4" : "/q8";
    ggml_init_params init{};
    init.mem_size = 4 * 1024 * 1024;
    init.no_alloc = true;
    ggml_context * ctx = ggml_init(init);
    assert(ctx);
    auto * q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, 128, 1, 12, 1);
    auto * k = ggml_new_tensor_4d(ctx, q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0, 128, 256, 2, 1);
    auto * v = ggml_new_tensor_4d(ctx, GGML_TYPE_Q8_0, 128, 256, 2, 1);
    auto * mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, 256, 1, 1, 1);
    uint32_t word = UINT32_C(0x3db504f3);
    float scale;
    std::memcpy(&scale, &word, 4);
    auto * dst = ggml_flash_attn_ext(ctx, q, k, v, mask, scale, 0, 0);
    auto * graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, dst);
    auto buffer = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
    assert(buffer);
    ggml_tensor * tensors[] = {q, k, v, mask};
    const char * files[] = {"attn_q_input-0.bin", "attn_k_input-0.bin", "attn_v_input-0.bin", "attn_mask_input-0.bin"};
    for (unsigned i = 0; i < 4; ++i) {
        const auto bytes = load(directory + "/" + files[i], ggml_nbytes(tensors[i]));
        ggml_backend_tensor_set(tensors[i], bytes.data(), 0, bytes.size());
    }
    const auto gold_bytes = load(directory + "/kqv_out-0.bin", 6144);
    std::vector<float> gold(1536), ordinary(1536), candidate(1536);
    std::memcpy(gold.data(), gold_bytes.data(), 6144);
    setenv("GGML_RISCV_AKV_QUANT_KV", "0", 1);
    const uintptr_t ordinary_flags = compute(ctx, graph, 1);
    ggml_backend_tensor_get(dst, ordinary.data(), 0, 6144);
    const float ordinary_error = compare(ordinary.data(), gold.data());
    setenv("GGML_RISCV_AKV_QUANT_KV", "1", 1);
    for (unsigned repeat = 0; repeat < 2; ++repeat) {
        std::printf("QUANT_LIVE_BEGIN kind=%s mode=native repeat=%u\n", name, repeat);
        std::fflush(stdout);
        std::memset(dst->data, 0xa5, 6144);
        const auto flags = compute(ctx, graph, 1);
        const auto * actual = static_cast<const float *>(dst->data);
        const float error = compare(actual, gold.data());
        compare(actual, ordinary.data());
        assert(flags == ordinary_flags);
        if (!repeat) std::memcpy(candidate.data(), actual, 6144);
        else assert(!std::memcmp(candidate.data(), actual, 6144));
        std::printf("QUANT_LIVE_END kind=%s mode=native repeat=%u flags=%lu max_abs=%.9g\n", name, repeat, static_cast<unsigned long>(flags), static_cast<double>(error));
    }
    auto * mask_words = static_cast<uint16_t *>(mask->data);
    const uint16_t saved = mask_words[63];
    mask_words[63] = UINT16_C(0xfc00);
    setenv("GGML_RISCV_AKV_QUANT_KV", "0", 1);
    compute(ctx, graph, 1);
    ggml_backend_tensor_get(dst, ordinary.data(), 0, 6144);
    setenv("GGML_RISCV_AKV_QUANT_KV", "1", 1);
    std::printf("QUANT_LIVE_BEGIN kind=%s mode=mask_fallback\n", name);
    std::fflush(stdout);
    std::memset(dst->data, 0xa5, 6144);
    compute(ctx, graph, 1);
    assert(!std::memcmp(dst->data, ordinary.data(), 6144));
    std::printf("QUANT_LIVE_END kind=%s mode=mask_fallback exact=1\n", name);
    mask_words[63] = saved;
    std::printf("QUANT_LIVE_BEGIN kind=%s mode=thread_fallback\n", name);
    std::fflush(stdout);
    std::memset(dst->data, 0xa5, 6144);
    compute(ctx, graph, 2);
    compare(static_cast<const float *>(dst->data), gold.data());
    std::printf("QUANT_LIVE_END kind=%s mode=thread_fallback\n", name);
    setenv("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "0", 1);
    std::printf("QUANT_LIVE_BEGIN kind=%s mode=memory_fallback\n", name);
    std::fflush(stdout);
    std::memset(dst->data, 0xa5, 6144);
    compute(ctx, graph, 1);
    compare(static_cast<const float *>(dst->data), gold.data());
    std::printf("QUANT_LIVE_END kind=%s mode=memory_fallback\n", name);
    setenv("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1", 1);
    for (unsigned i = 0; i < 4; ++i) {
        const auto original = load(directory + "/" + files[i], ggml_nbytes(tensors[i]));
        assert(!std::memcmp(tensors[i]->data, original.data(), original.size()));
    }
    std::printf("QUANT_LIVE_PROFILE_PASS kind=%s heads=12 kv_heads=2 outputs=1536 native_calls=2 ordinary_gold_max=%.9g inputs_unchanged=1\n", name, static_cast<double>(ordinary_error));
    ggml_backend_buffer_free(buffer);
    ggml_free(ctx);
}

int main() {
    setenv("GGML_RISCV_QBS", "1", 1);
    setenv("GGML_RISCV_QBS_EMULATE", "0", 1);
    setenv("GGML_RISCV_AKV", "0", 1);
    setenv("GGML_RISCV_AKV_EMULATE", "0", 1);
    setenv("GGML_RISCV_AKV_TRACE", "1", 1);
    setenv("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1", 1);
    ggml_cpu_init();
    profile(false);
    profile(true);
    std::puts("QUANT_LIVE_SUITE_PASS profiles=2 executor=native_qbs performance=not_measured");
}
