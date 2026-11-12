#define GGML_COMMON_DECL_CPP
#include "ggml-common.h"
#include <cassert>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "qbs/qbs.h"
#include "software/akv/experimental/quantized_kv/selection.h"
#include "repack.h"
#include SOFTWARE_REPACK_FRAGMENT
#include "software/qbs/experimental/m4_preflight/m4_preflight.h"

static unsigned checks;
static void need(bool ok) { ++checks; if (!ok) std::abort(); }
static float fp(uint32_t bits) { float v; std::memcpy(&v, &bits, 4); return v; }
static int bias_integer(float value) {
    uint32_t bits; std::memcpy(&bits, &value, 4);
    return int(bits & 0x007fffffu) - 0x00400000;
}
enum class ggml_riscv_quant_kv_status { complete, fallback, failed };
struct pv_selection { bool register_pv, grouped_pv; };
static ggml_riscv_quant_kv_status pv_guard(pv_selection call) {
#include SOFTWARE_PV_GUARD_FRAGMENT
    return ggml_riscv_quant_kv_status::complete;
}

int main() {
    need(std::fesetround(FE_TONEAREST) == 0);
    need(pv_guard({false, false}) == ggml_riscv_quant_kv_status::complete);
    need(pv_guard({true, false}) == ggml_riscv_quant_kv_status::complete);
    need(pv_guard({false, true}) == ggml_riscv_quant_kv_status::complete);
    need(pv_guard({true, true}) == ggml_riscv_quant_kv_status::fallback);
    qbs_device_t device{};
    need(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
    auto wide = [&](unsigned profile, size_t m, size_t k) {
        return qbs_recommend_activation_storage(&device, profile,
            QBS_ACTIVATION_PROFILE_Q8_K, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, m, 64, k);
    };
    need(wide(QBS_WEIGHT_PROFILE_Q4_K, 4, 1536) == QBS_ACTIVATION_STORAGE_M4_GROUPED);
    need(wide(QBS_WEIGHT_PROFILE_Q4_K, 8, 1536) == QBS_ACTIVATION_STORAGE_M8_GROUPED);
    need(wide(QBS_WEIGHT_PROFILE_Q6_K, 8, 1536) == QBS_ACTIVATION_STORAGE_M8_GROUPED);
    need(wide(QBS_WEIGHT_PROFILE_Q4_K, 10, 1536) == QBS_ACTIVATION_STORAGE_M4_GROUPED);
    device.capabilities.max_m = 4;
    need(wide(QBS_WEIGHT_PROFILE_Q4_K, 8, 1536) == QBS_ACTIVATION_STORAGE_M4_GROUPED);
    device.capabilities.max_m = 8;
    need(wide(QBS_WEIGHT_PROFILE_Q4_K, 8, 256 * 257) == QBS_ACTIVATION_STORAGE_M4_GROUPED);
    qbs_profile_binding_t binding{};
    need(qbs_device_bind_encodings(&device, QBS_WEIGHT_ENCODING_Q4_K,
        QBS_ACTIVATION_ENCODING_Q8_K, &binding) == QBS_STATUS_OK);

    // Existing RVV witness: multiply-round then integer-round differs from fused bias.
    volatile float maximum = fp(0x3f800001u), input = fp(0xbda952a7u);
    const float scale = -127.0f / maximum;
    volatile float product = input * scale;
    const int rowwise = int(std::nearbyint(float(product)));
    const int fused = bias_integer(std::fma(float(input), scale, 12582912.0f));
    need(rowwise != fused);
    std::printf("rounding_witness rowwise=%d fused=%d q4k_activation=Q8_K\n", rowwise, fused);

    alignas(64) float x[4 * 256]{};
    for (int row = 0; row < 4; ++row) {
        x[row * 256] = maximum; x[row * 256 + 1] = input;
    }
    block_q8_Kx4 baseline{}, candidate{};
    ggml_quantize_mat_q8_K_4x1_ara_generic(x, &baseline, 256);
    const bool vector = qbs_experimental_m4_preflight::quantize(x, &candidate, 256);
    need(!vector && std::memcmp(&baseline, &candidate, sizeof(baseline)) == 0);
    std::printf("retained_maxima_host_fallback_bytes=%zu vector_executed=0\n", sizeof(baseline));

    alignas(64) float query[32]{}, output[32]{};
    alignas(64) unsigned char key[18]{}, value[34]{};
    uint16_t mask = 0;
    akv_quant_selection_input_t in{};
    in.requested = 1; in.vlen_bits = 1024; in.normal_memory = 1; in.device = &device;
    in.key_encoding = QBS_WEIGHT_ENCODING_Q4_0;
    in.value_encoding = QBS_WEIGHT_ENCODING_Q8_0_WEIGHT; in.scale = 1;
    in.query = {query, sizeof(query), sizeof(query), sizeof(query), 32, 1, 1};
    in.key = {key, sizeof(key), sizeof(key), sizeof(key), 32, 1, 1};
    in.value = {value, sizeof(value), sizeof(value), sizeof(value), 32, 1, 1};
    in.output = {output, sizeof(output), sizeof(output), sizeof(output), 32, 1, 1};
    in.mask = &mask; in.mask_bytes = sizeof(mask);
    akv_quant_selection_t selection{};
    need(akv_quant_select(&in, &selection) == AKV_QUANT_SELECT_OK);
    in.normal_memory = 0;
    need(akv_quant_select(&in, &selection) == AKV_QUANT_SELECT_CAPABILITY);
    in.normal_memory = 1; in.frm = 1;
    need(akv_quant_select(&in, &selection) == AKV_QUANT_SELECT_CAPABILITY);
    in.frm = 0; in.vstart = 1;
    need(akv_quant_select(&in, &selection) == AKV_QUANT_SELECT_CAPABILITY);
    in.vstart = 0; in.softcap = 1;
    need(akv_quant_select(&in, &selection) == AKV_QUANT_SELECT_FEATURE);
    in.softcap = 0; in.value_encoding = QBS_WEIGHT_ENCODING_Q4_0;
    need(akv_quant_select(&in, &selection) == AKV_QUANT_SELECT_CAPABILITY);
    std::printf("SOFTWARE_CONTRACT_HOST_PASS checks=%u native_execution=0 performance_measured=0\n", checks);
}
