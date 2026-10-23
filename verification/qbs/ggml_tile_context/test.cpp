#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml-quants.h"
#include "quants.h"
#include "repack.h"
#include "arch/riscv/qbs.h"
#include "qbs/qbs.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>

static void require(bool ok, const char * message) {
    if (!ok) {
        std::fprintf(stderr, "QBS_TILE_GRAPH_FAIL reason=%s\n", message);
        std::exit(1);
    }
}

static bool enabled(const char * name) {
    const char * value = std::getenv(name);
    return value && (!std::strcmp(value, "1") || !std::strcmp(value, "true") ||
        !std::strcmp(value, "TRUE") || !std::strcmp(value, "yes") ||
        !std::strcmp(value, "YES") || !std::strcmp(value, "on") || !std::strcmp(value, "ON"));
}

static uint16_t u16(const uint8_t * p) {
    return uint16_t(p[0]) | uint16_t(uint16_t(p[1]) << 8);
}

static int s8(uint8_t value) {
    return value < 128 ? int(value) : int(value) - 256;
}

static void put16(uint8_t * p, uint16_t value) {
    p[0] = uint8_t(value);
    p[1] = uint8_t(value >> 8);
}

static double half_value(uint16_t bits) {
    const unsigned exponent = (bits >> 10) & 31u;
    const unsigned fraction = bits & 1023u;
    require(exponent != 31, "nonfinite_half_in_oracle");
    const double value = exponent ? std::ldexp(double(1024u + fraction), int(exponent) - 25)
                                  : std::ldexp(double(fraction), -24);
    return bits & 0x8000u ? -value : value;
}

static uint16_t exact_scale_half(float value) {
    int exponent = 0;
    const float fraction = std::frexp(value, &exponent);
    require(fraction == 0.5f && exponent >= -13 && exponent <= 16,
            "activation_scale_not_normal_power_of_two");
    return uint16_t((exponent + 14) << 10);
}

// Original row-major bytes, never the production R4 buffer or dot kernel.
static void decode_row(ggml_type type, const uint8_t * bytes, int blocks,
                       double * values) {
    for (int b = 0; b < blocks; ++b) {
        if (type == GGML_TYPE_Q8_0) {
            const uint8_t * p = bytes + b * 34;
            const double scale = half_value(u16(p));
            for (int j = 0; j < 32; ++j) values[b * 32 + j] = scale * s8(p[2 + j]);
        } else if (type == GGML_TYPE_Q8_K) {
            const uint8_t * p = bytes + b * 292;
            float scale;
            std::memcpy(&scale, p, sizeof(scale));
            require(std::isfinite(scale), "nonfinite_q8k_scale");
            for (int j = 0; j < 256; ++j) values[b * 256 + j] = double(scale) * s8(p[4 + j]);
        } else {
            require(type == GGML_TYPE_Q4_K, "unsupported_oracle_type");
            const uint8_t * p = bytes + b * 144;
            const double d = half_value(u16(p));
            const double dmin = half_value(u16(p + 2));
            const uint8_t * scales = p + 4;
            for (int j = 0; j < 256; ++j) {
                const int group = j / 32;
                const unsigned scale = group < 4 ? scales[group] & 63u
                    : (scales[group + 4] & 15u) | ((scales[group - 4] >> 6) << 4);
                const unsigned minimum = group < 4 ? scales[group + 4] & 63u
                    : (scales[group + 4] >> 4) | ((scales[group] >> 6) << 4);
                const unsigned packed = p[16 + (j / 64) * 32 + j % 32];
                const unsigned quant = j % 64 < 32 ? packed & 15u : packed >> 4;
                values[b * 256 + j] = d * scale * quant - dmin * minimum;
            }
        }
    }
}

// Inputs deliberately avoid rounding ties and signed-amax ties: all scaled
// quantization products are exact integers. This isolates mapping/lifetime
// from known reference-FMA versus RVV tail-row rounding differences.
static std::vector<uint8_t> scalar_activation(const float * source, bool q8_k, int blocks) {
    const int elements = q8_k ? 256 : 32;
    const int block_bytes = q8_k ? 292 : 34;
    std::vector<uint8_t> bytes(size_t(blocks) * block_bytes, 0);
    for (int b = 0; b < blocks; ++b) {
        const float * x = source + b * elements;
        float amax = 0, signed_max = 0;
        for (int j = 0; j < elements; ++j) {
            require(std::isfinite(x[j]), "nonfinite_activation");
            if (std::fabs(x[j]) > amax) {
                amax = std::fabs(x[j]);
                signed_max = x[j];
            }
        }
        require(amax > 0, "unexpected_zero_block");
        const float d = q8_k ? signed_max / -127.0f : amax / 127.0f;
        const float inverse = q8_k ? -127.0f / signed_max : 1.0f / d;
        uint8_t * p = bytes.data() + b * block_bytes;
        if (q8_k) std::memcpy(p, &d, sizeof(d));
        else put16(p, exact_scale_half(d));
        for (int j = 0; j < elements; ++j) {
            const float scaled = x[j] * inverse;
            const int quant = int(std::round(scaled));
            require(scaled == float(quant) && quant >= -127 && quant <= 127,
                    "activation_not_exactly_quantizable");
            p[(q8_k ? 4 : 2) + j] = uint8_t(quant);
        }
        if (q8_k) {
            for (int g = 0; g < 16; ++g) {
                int sum = 0;
                for (int j = 0; j < 16; ++j) sum += s8(p[4 + g * 16 + j]);
                put16(p + 260 + 2 * g, uint16_t(sum));
            }
        }
    }
    return bytes;
}

static uint64_t digest(const std::vector<float> & values) {
    uint64_t hash = UINT64_C(14695981039346656037);
    for (float value : values) {
        uint32_t bits;
        std::memcpy(&bits, &value, sizeof(bits));
        for (unsigned byte = 0; byte < 4; ++byte)
            hash = (hash ^ ((bits >> (8 * byte)) & 255u)) * UINT64_C(1099511628211);
    }
    return hash;
}

struct shape {
    ggml_type type;
    int m;
    int blocks;
};

static constexpr shape shapes[] = {
    {GGML_TYPE_Q8_0, 1, 1}, {GGML_TYPE_Q8_0, 3, 17},
    {GGML_TYPE_Q8_0, 4, 28}, {GGML_TYPE_Q8_0, 4, 32}, {GGML_TYPE_Q8_0, 4, 33},
    {GGML_TYPE_Q8_0, 5, 1}, {GGML_TYPE_Q8_0, 5, 17}, {GGML_TYPE_Q8_0, 5, 28},
    {GGML_TYPE_Q8_0, 8, 17}, {GGML_TYPE_Q8_0, 8, 28}, {GGML_TYPE_Q8_0, 9, 17},
    {GGML_TYPE_Q4_K, 4, 2}, {GGML_TYPE_Q4_K, 4, 4}, {GGML_TYPE_Q4_K, 4, 5},
    {GGML_TYPE_Q4_K, 8, 2}, {GGML_TYPE_Q4_K, 8, 3},
};

static void run_shape(unsigned case_index, int threads, unsigned segment) {
    const shape s = shapes[case_index];
    constexpr int n = 37;
    const bool q8_k = s.type == GGML_TYPE_Q4_K;
    const ggml_type activation_type = q8_k ? GGML_TYPE_Q8_K : GGML_TYPE_Q8_0;
    const int elements = q8_k ? 256 : 32;
    const int k = s.blocks * elements;
    const size_t weight_stride = ggml_row_size(s.type, k);
    const size_t activation_stride = ggml_row_size(activation_type, k);
    require(ggml_type_size(s.type) == (q8_k ? 144u : 34u) &&
            ggml_type_size(activation_type) == (q8_k ? 292u : 34u), "unexpected_block_abi");
    require(ggml_riscv_qbs_supports_tensor(s.type, k, n), "native_qbs_tensor_not_supported");

    ggml_init_params params{};
    params.mem_size = 1024 * 1024;
    params.no_alloc = true;
    ggml_context * weight_context = ggml_init(params);
    ggml_context * context = ggml_init(params);
    require(weight_context && context, "context_allocation");
    ggml_tensor * weights = ggml_new_tensor_2d(weight_context, s.type, k, n);
    ggml_set_name(weights, "tile_context_weights");
    ggml_backend_buffer_t weight_buffer = ggml_backend_alloc_ctx_tensors_from_buft(
        weight_context, ggml_backend_cpu_repack_buffer_type());
    require(weight_buffer && weights->extra, "repack_buffer_not_selected");
    const auto * wt = ggml_get_type_traits(s.type);
    require(wt && wt->from_float_ref, "missing_weight_reference_quantizer");
    std::vector<uint8_t> original_weights(n * weight_stride);
    std::vector<double> weight_values(n * k);
    std::vector<float> source(k);
    for (int row = 0; row < n; ++row) {
        for (int i = 0; i < k; ++i) {
            const int quant = int((unsigned(row * 29 + i * 17 + i / elements * 13) % 127u)) - 63;
            source[i] = float(quant) / 512.0f;
        }
        wt->from_float_ref(source.data(), original_weights.data() + row * weight_stride, k);
        decode_row(s.type, original_weights.data() + row * weight_stride,
                   s.blocks, weight_values.data() + row * k);
    }
    ggml_backend_tensor_set(weights, original_weights.data(), 0, original_weights.size());
    const size_t block_bytes = ggml_type_size(s.type);
    const size_t segment_blocks = segment ? segment : unsigned(s.blocks);
    for (size_t row = 0; row < n; ++row) {
        for (size_t b = 0; b < unsigned(s.blocks); ++b) {
            const size_t start = b / segment_blocks * segment_blocks;
            const size_t local_k = std::min(segment_blocks, size_t(s.blocks) - start);
            const size_t index = start * 40 + (row / 4) * local_k * 4 + (b - start) * 4 + row % 4;
            require(std::memcmp(static_cast<const uint8_t *>(weights->data) + index * block_bytes,
                original_weights.data() + (row * s.blocks + b) * block_bytes, block_bytes) == 0,
                "qbs_r4_byte_mapping");
        }
    }

    ggml_tensor * activation = ggml_new_tensor_2d(context, GGML_TYPE_F32, k, s.m);
    ggml_set_name(activation, "tile_context_activation");
    ggml_tensor * output = ggml_mul_mat(context, weights, activation);
    ggml_set_name(output, "tile_context_output");
    ggml_backend_t backend = ggml_backend_cpu_init();
    require(backend != nullptr, "cpu_backend");
    ggml_backend_cpu_set_n_threads(backend, threads);
    ggml_backend_buffer_t buffer = ggml_backend_alloc_ctx_tensors(context, backend);
    require(buffer != nullptr, "tensor_allocation");
    const void * activation_address = activation->data;
    ggml_cgraph * graph = ggml_new_graph(context);
    ggml_build_forward_expand(graph, output);
    std::vector<float> inputs(s.m * k), actual(s.m * n), readback(s.m * k);
    std::vector<double> activation_values(s.m * k);
    std::vector<uint8_t> production(activation_stride), reference(activation_stride);
    uint64_t previous_input_digest = 0, previous_output_digest = 0;
    for (int epoch = 0; epoch < 2; ++epoch) {
        for (int input = 0; input < s.m; ++input) {
            for (int b = 0; b < s.blocks; ++b) {
                const float scale = std::ldexp(1.0f, -8 - (input + b + epoch) % 3);
                for (int j = 0; j < elements; ++j) {
                    const int quant = j == 0 ? ((input + b + epoch) % 2 ? -127 : 127)
                        : int((unsigned(input * 31 + b * 19 + j * 23 + epoch * 47) % 193u)) - 96;
                    inputs[input * k + b * elements + j] = float(quant) * scale;
                }
            }
            const float * row = inputs.data() + input * k;
            const auto expected_bytes = scalar_activation(row, q8_k, s.blocks);
            if (q8_k) quantize_row_q8_K_ref(row, reinterpret_cast<block_q8_K *>(reference.data()), k);
            else quantize_row_q8_0_ref(row, reinterpret_cast<block_q8_0 *>(reference.data()), k);
            const auto * cpu = ggml_get_type_traits_cpu(activation_type);
            require(cpu && cpu->from_float, "missing_production_activation_quantizer");
            cpu->from_float(row, production.data(), k);
            require(reference == expected_bytes, "reference_quantization_differs_from_scalar");
            require(production == expected_bytes, "production_tail_or_wide_quantization_differs_from_scalar");
            decode_row(activation_type, expected_bytes.data(), s.blocks, activation_values.data() + input * k);
        }
        const uint64_t input_digest = digest(inputs);
        require(epoch == 0 || input_digest != previous_input_digest, "activation_did_not_change");
        ggml_backend_tensor_set(activation, inputs.data(), 0, inputs.size() * sizeof(float));
        require(activation->data == activation_address, "activation_address_changed");
        ggml_backend_tensor_get(activation, readback.data(), 0, readback.size() * sizeof(float));
        require(std::memcmp(readback.data(), inputs.data(), inputs.size() * sizeof(float)) == 0,
                "activation_upload_mismatch");
        std::fill(actual.begin(), actual.end(), std::numeric_limits<float>::quiet_NaN());
        ggml_backend_tensor_set(output, actual.data(), 0, actual.size() * sizeof(float));
        std::printf("QBS_TILE_GRAPH_BEGIN case=%u type=%s m=%d n=37 k_blocks=%d threads=%d epoch=%d\n",
                    case_index, ggml_type_name(s.type), s.m, s.blocks, threads, epoch);
        std::fflush(stdout);
        require(ggml_backend_graph_compute(backend, graph) == GGML_STATUS_SUCCESS, "graph_compute");
        ggml_backend_tensor_get(output, actual.data(), 0, actual.size() * sizeof(float));
        double max_error = 0;
        for (int input = 0; input < s.m; ++input) {
            for (int row = 0; row < n; ++row) {
                double expected = 0;
                for (int i = 0; i < k; ++i)
                    expected += weight_values[row * k + i] * activation_values[input * k + i];
                const double value = actual[input * n + row];
                const double error = std::fabs(value - expected);
                if (!std::isfinite(value) || !std::isfinite(expected) || !std::isfinite(error) ||
                    error > 2e-4 + 2e-5 * std::fabs(expected)) {
                    std::fprintf(stderr, "QBS_TILE_GRAPH_MISMATCH case=%u epoch=%d input=%d row=%d "
                                 "actual=%.17g expected=%.17g error=%.17g\n",
                                 case_index, epoch, input, row, value, expected, error);
                    require(false, "numerical_mismatch");
                }
                max_error = std::max(max_error, error);
            }
        }
        const uint64_t output_digest = digest(actual);
        require(epoch == 0 || output_digest != previous_output_digest, "stale_epoch_output");
        std::printf("QBS_TILE_GRAPH_PASS outputs=%zu digest=%016llx max_error=%.17g\n",
                    actual.size(), static_cast<unsigned long long>(output_digest), max_error);
        std::fflush(stdout);
        previous_input_digest = input_digest;
        previous_output_digest = output_digest;
    }
    ggml_backend_buffer_free(buffer);
    ggml_backend_free(backend);
    ggml_free(context);
    ggml_backend_buffer_free(weight_buffer);
    ggml_free(weight_context);
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    require(enabled("GGML_RISCV_QBS") && !enabled("GGML_RISCV_QBS_EMULATE"), "native_qbs_optin_required");
    const char * threads_env = std::getenv("GGML_QBS_TILE_THREADS");
    require(threads_env && (!std::strcmp(threads_env, "1") || !std::strcmp(threads_env, "3")),
            "GGML_QBS_TILE_THREADS_must_be_1_or_3");
    const int threads = threads_env[0] - '0';
    unsigned requested_segment = 0;
    if (const char * value = std::getenv("GGML_RISCV_QBS_SEGMENT_K_BLOCKS")) {
        char * end = nullptr;
        const unsigned long parsed = std::strtoul(value, &end, 10);
        require(end != value && *end == '\0' && parsed <= 256, "invalid_segment_policy");
        requested_segment = unsigned(parsed);
    }
    require(ggml_riscv_qbs_weight_segment_blocks() == requested_segment, "effective_segment_policy_mismatch");
    qbs_device_t device{};
    require(qbs_device_query(qbs_native_info, nullptr, &device) == QBS_STATUS_OK, "native_capability_query");
    require(qbs_native_info(nullptr, 3) == UINT64_C(0x0000000100001240) &&
            device.capabilities.activation_context_capacity_bytes == 4672 &&
            device.capabilities.activation_context_max_m == 8 &&
            device.capabilities.activation_context_max_k_blocks == 32, "extended_context_capability_required");
    constexpr unsigned count = sizeof(shapes) / sizeof(shapes[0]);
    for (unsigned i = 0; i < count; ++i) run_shape(i, threads, requested_segment);
    std::printf("QBS_TILE_GRAPH_SUITE_PASS cases=%u\n", count * 2);
    return 0;
}
