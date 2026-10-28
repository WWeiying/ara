#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wextra"
#include "prefix_schedule.h"
#pragma GCC diagnostic pop
#include "ggml-cpu/quants.h"
#include "ggml-quants.h"
#include "ggml-cpu.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#include "ggml-cpu/vec.h"
#pragma GCC diagnostic pop
#include <algorithm>
#include <array>
#include <cassert>
#include <cfenv>
#include <cstring>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

static std::vector<unsigned char> load(const std::string &path, size_t size) {
    FILE *f = std::fopen(path.c_str(), "rb"); assert(f);
    std::vector<unsigned char> data(size);
    assert(std::fread(data.data(), 1, size, f) == size && std::fgetc(f) == EOF);
    assert(!std::fclose(f)); return data;
}
struct context {
    const unsigned char *key, *value;
    unsigned row_bytes, base, rows, calls, decodes, elements;
    unsigned visible[8];
    alignas(64) unsigned char query[8][136];
    bool q4;
};
static int qk(void *opaque, unsigned first, unsigned rows, unsigned token,
              unsigned tokens, float *output, size_t stride) {
    auto &c = *static_cast<context *>(opaque);
    assert(first + rows <= c.rows && (rows == 1 || rows == 2 || rows == 4));
    ++c.calls;
    for (unsigned row = 0; row < rows; ++row) {
        assert(token + tokens <= c.visible[first + row]);
        for (unsigned t = 0; t < tokens; ++t) {
            auto dot = c.q4 ? ggml_vec_dot_q4_0_q8_0 : ggml_vec_dot_q8_0_q8_0;
            dot(128, output + row * stride + t, 0, c.key + (token + t) * c.row_bytes,
                0, c.query[first + row], 0, 1);
            ++c.elements;
        }
    }
    return 0;
}
static int value(void *opaque, unsigned token, float *output, unsigned dim) {
    auto &c = *static_cast<context *>(opaque); assert(dim == 128);
    ++c.decodes;
    dequantize_row_q8_0(reinterpret_cast<const block_q8_0 *>(c.value + token * 136), output, 128);
    return 0;
}
static void scale(int n, float *out, float s) { ggml_vec_scale_f32(n, out, s); }
static void mad(int n, float *out, const float *v, float s) { ggml_vec_mad_f32(n, out, v, s); }

int main(int argc, char **argv) {
    assert(argc == 3);
    // GGML quantized dot products use the CPU FP16 conversion table.
    ggml_cpu_init();
    const std::string root = argv[1], kind = argv[2];
    assert(kind == "q4_0" || kind == "q8_0");
    const unsigned key_bytes = kind == "q4_0" ? 72 : 136;
    auto q = load(root + "/attn_q_input-0.bin", 163840);
    auto k = load(root + "/attn_k_input-0.bin", key_bytes * 256 * 8);
    auto v = load(root + "/attn_v_input-0.bin", 278528);
    auto mask = load(root + "/attn_mask_input-0.bin", 10240);
    auto golden = load(root + "/kqv_out-0.bin", 163840);
    const float score_scale = 1.0f / std::sqrt(128.0f);
    unsigned outputs = 0, decoded = 0, original_decoded = 0, elements = 0;
    double max_error = 0;
    for (unsigned kv = 0; kv < 8; ++kv) {
        for (unsigned first_query = 0; first_query < 20; first_query += 4) {
            context c{}; c.key = k.data() + kv * 256 * key_bytes;
            c.value = v.data() + kv * 256 * 136; c.row_bytes = key_bytes; c.q4 = kind == "q4_0"; c.rows = 8;
            for (unsigned row = 0; row < 8; ++row) {
                const unsigned query = first_query + row / 2, head = kv * 2 + row % 2;
                c.visible[row] = query + 1;
                for (unsigned t = 0; t < 256; ++t) {
                    uint16_t bits; std::memcpy(&bits, mask.data() + (query * 256 + t) * 2, 2);
                    assert(bits == (t <= query ? 0 : 0xfc00));
                }
                alignas(64) float query_data[128];
                std::memcpy(query_data, q.data() + (head * 20 + query) * 512, sizeof(query_data));
                quantize_row_q8_0(query_data, c.query[row], 128);
            }
            float reference[8][136], output[8][136];
            std::memset(reference, 0xa5, sizeof(reference)); std::memset(output, 0xa5, sizeof(output));
            akv_quant_online_workspace_t w;
            std::feclearexcept(FE_ALL_EXCEPT);
            for (unsigned row = 0; row < 8; ++row) {
                context single = c; single.rows = 1; single.calls = single.decodes = single.elements = 0;
                single.visible[0] = c.visible[row]; std::memcpy(single.query[0], c.query[row], 136);
                akv_quant_online_plan_t p = {1, 128, single.visible[0], score_scale, &single, qk, value, scale, mad};
                assert(akv_quant_online_head_major(&p, reference[row], 136, &w) == 0);
                original_decoded += single.decodes;
            }
            const int flags = std::fetestexcept(FE_ALL_EXCEPT);
            std::feclearexcept(FE_ALL_EXCEPT);
            akv_quant_online_plan_t p = {8, 128, 20, score_scale, &c, qk, value, scale, mad};
            assert(quant_prefill_prefix_schedule(&p, c.visible, output[0], 136, &w) == 0);
            assert(flags == std::fetestexcept(FE_ALL_EXCEPT));
            assert(!std::memcmp(reference, output, sizeof(output)));
            decoded += c.decodes; elements += c.elements;
            for (unsigned row = 0; row < 8; ++row) {
                unsigned query = first_query + row / 2, head = kv * 2 + row % 2;
                for (unsigned d = 0; d < 128; ++d) {
                    float want; std::memcpy(&want, golden.data() + ((query * 16 + head) * 128 + d) * 4, 4);
                    assert(std::isfinite(want) && std::isfinite(output[row][d]));
                    double error = std::fabs(double(output[row][d]) - want);
                    max_error = std::max(max_error, error);
                    assert(error <= 2e-5 + 2e-5 * std::fabs(double(want)));
                    ++outputs;
                }
            }
        }
    }
    assert(outputs == 40960 && original_decoded == 3360 && decoded == 480 && elements == 3360);
    std::printf("REAL_PREFIX_PASS type=%s outputs=%u bitexact_schedule=1 flags=1 golden_max_abs=%.9g value_calls=%u reference_value_calls=%u qk_elements=%u performance=not_measured\n",
                kind.c_str(), outputs, max_error, decoded, original_decoded, elements);
}
