// Production kernel + SDK slice, not the GGML allocator/threadpool/selector.
#include "arch/riscv/q8_K-m4.h"
#include "qbs/qbs.h"
#include "printf.h"
#include "contract.h"
#include <cstring>

#if !defined(__riscv_zfh) || !defined(__riscv_zvfh) || !defined(__riscv_vector)
#error "The slice must compile under the combined ISA"
#endif

extern "C" const float projection_input[];
extern "C" const unsigned char projection_weights[], projection_golden[];
extern "C" const unsigned char projection_weights_reference[];
extern "C" const float projection_oracle[];
extern "C" const unsigned char input_before[], input_after[], weights_before[], weights_after[];
alignas(64) static block_q8_Kx4 packed[8];
alignas(64) static float output[6144 + 32];

static uint64_t cycle() {
    uint64_t value;
    asm volatile("fence rw, rw; rdcycle %0" : "=r"(value) : : "memory");
    return value;
}
static unsigned fcsr() {
    unsigned value;
    asm volatile("frcsr %0" : "=r"(value) : : "memory");
    return value;
}
static unsigned vcsr() {
    unsigned value;
    asm volatile("csrr %0,vcsr" : "=r"(value) : : "memory");
    return value;
}
static uint64_t digest(const void * data, size_t size) {
    const auto * bytes = static_cast<const volatile unsigned char *>(data);
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * UINT64_C(1099511628211);
    return hash;
}
static bool canary(const void * data, size_t size) {
    const auto * bytes = static_cast<const unsigned char *>(data);
    for (size_t i = 0; i < size; ++i) if (bytes[i] != 0xa5) return false;
    return true;
}
static bool weights_equal() {
    if (uintptr_t(projection_weights) == uintptr_t(projection_weights_reference)) return false;
    for (size_t offset = 0; offset < 1327104;) {
        const size_t vl = __riscv_vsetvl_e8m8(1327104 - offset);
        const auto actual = __riscv_vle8_v_u8m8(projection_weights + offset, vl);
        const auto expected = __riscv_vle8_v_u8m8(projection_weights_reference + offset, vl);
        const auto mismatch = __riscv_vmsne_vv_u8m8_b1(actual, expected, vl);
        if (__riscv_vcpop_m_b1(mismatch, vl)) return false;
        offset += vl;
    }
    return true;
}
__attribute__((noinline)) static bool prepare() {
    return ggml_riscv_q8_K_m4::quantize(projection_input, packed + 1, 1536);
}

static unsigned check_plan(const qbs_plan_t & plan) {
    unsigned errors = plan.k_blocks != 6 || plan.command_m != 4 || plan.command_n != 32 ||
        plan.weight_segment_k_blocks != 256 || plan.uses_wide_m || plan.split_k ||
        plan.needs_activation_gather || plan.workspace_bytes || qbs_plan_supports_activation_context(&plan);
    qbs_plan_cursor_t cursor{};
    qbs_plan_cursor_reset(&cursor);
    for (unsigned index = 0; index <= 48; ++index) {
        qbs_command_t command{};
        int present = 0;
        if (qbs_plan_next(&plan, &cursor, &command, &present) != QBS_STATUS_OK) return errors + 1;
        if (index == 48) return errors + (present != 0);
        if (!present) return errors + 1;
        errors += command.m != 4 || command.n != 32 || command.k_blocks != 6 ||
            command.k_block_start || command.input_start || command.output_start != index * 32 ||
            command.activation_layout != QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED ||
            command.accumulate || command.gather_activation || command.activation_offset_bytes ||
            command.output_offset_elements != index * 32 ||
            command.weight_offset_bytes != size_t(index) * 32 * 6 * 144;
    }
    return errors + 1;
}

int main() {
    static_assert(sizeof(block_q8_Kx4) == 1168, "M4 ABI");
    uint64_t info[4];
    for (unsigned i = 0; i < 4; ++i) info[i] = qbs_native_info(nullptr, i);
    qbs_device_t device{};
    const auto query = qbs_device_query(qbs_native_info, nullptr, &device);
    printf("Q8K_CURRENT_BEGIN info0=%016lx info1=%016lx info2=%016lx info3=%016lx\n",
           (unsigned long) info[0], (unsigned long) info[1], (unsigned long) info[2], (unsigned long) info[3]);
    unsigned errors = query != QBS_STATUS_OK;
    for (unsigned i = 0; i < 4; ++i) errors += info[i] != qbs_capability_word(i, 1024);
    errors += device.capabilities.activation_context_capacity_bytes != 4672 ||
              device.capabilities.activation_context_max_m != 8 ||
              device.capabilities.activation_context_max_k_blocks != 32;
    if (errors) {
        printf("Q8K_CURRENT_FAIL reason=capabilities errors=%u\n", errors);
        return 1;
    }
    const qbs_problem_t problem = {QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_K,
        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, QBS_ACTIVATION_STORAGE_M4_GROUPED, 4, 1536, 1536};
    // Full weight integrity is checked before/after ABBA, never in a timed phase.
    const uint64_t weights_baseline = Q8K_WEIGHTS_DIGEST;
    if (!weights_equal()) {
        printf("Q8K_CURRENT_FAIL reason=initial_weights\n");
        return 1;
    }
    // Even enabling wide-M policy must select M4 for this shape.
    if (qbs_recommend_activation_storage(&device, problem.weight_profile, problem.activation_profile,
            problem.weight_layout, 4, 1536, 1536) != QBS_ACTIVATION_STORAGE_M4_GROUPED) {
        printf("Q8K_CURRENT_FAIL reason=storage_policy\n");
        return 1;
    }
    uint64_t output_hashes[4] = {};
    unsigned final_flags[4] = {};
    const bool vector[4] = {false, true, true, false};
    for (unsigned trial = 0; trial < 4; ++trial) {
        std::memset(packed, 0xa5, sizeof(packed));
        std::memset(output, 0xa5, sizeof(output));
        qbs_plan_t plan{};
        bool used = false;
        asm volatile("fscsr zero; csrwi vcsr, 5" ::: "memory");
        const uint64_t begin = cycle();
        // Segment-256 storage has one segment here; no K split or context fitting.
        const auto admission = qbs_plan_create_segmented_r4(&device, &problem, 256, &plan);
        const bool context = qbs_plan_supports_activation_context(&plan);
        const uint64_t admitted = cycle();
        if (admission != QBS_STATUS_OK || context) {
            printf("Q8K_CURRENT_FAIL reason=plan_or_context\n");
            return 1;
        }
        if (vector[trial]) used = prepare();
        else ggml_quantize_mat_q8_K_4x1_ara_generic(projection_input, packed + 1, 1536);
        const unsigned prep_fcsr = fcsr(), prep_vcsr = vcsr();
        const uint64_t prepared = cycle();
        const auto execution = qbs_execute(&plan, projection_weights, 1327104, packed + 1, 7008,
            output + 16, 6144, 1536, nullptr, 0, qbs_native_execute_command, nullptr);
        const unsigned final_fcsr = fcsr(), final_vcsr = vcsr();
        const uint64_t finished = cycle();
        asm volatile("fscsr zero" ::: "memory");

        unsigned local = execution != QBS_STATUS_OK || used != vector[trial] ||
            prep_fcsr != Q8K_GOLDEN_FCSR || prep_vcsr != 5 || final_vcsr != 5 || final_fcsr > 31;
        local += check_plan(plan);
        local += std::memcmp(packed + 1, projection_golden, 7008) != 0;
        for (unsigned block = 1; block <= 6; ++block) {
            for (unsigned group = 0; group < 16; ++group) {
                for (unsigned row = 0; row < 4; ++row) {
                    int sum = 0;
                    for (unsigned j = 0; j < 16; ++j) sum += packed[block].qs[4 * (group * 16 + j) + row];
                    local += sum != packed[block].bsums[4 * group + row];
                }
            }
        }
        local += !canary(packed, sizeof(packed[0])) || !canary(packed + 7, sizeof(packed[0])) ||
                 !canary(output, 16 * sizeof(float)) || !canary(output + 6160, 16 * sizeof(float)) ||
                 !canary(input_before, 64) || !canary(input_after, 64) ||
                 !canary(weights_before, 64) || !canary(weights_after, 64);
        for (unsigned i = 0; i < 6144; ++i) {
            const float actual = output[16 + i], expected = projection_oracle[i];
            local += !std::isfinite(actual) || !std::isfinite(expected) ||
                     fabsf(actual - expected) > 2e-4f + 2e-5f * fabsf(expected);
        }
        const uint64_t ih = digest(projection_input, 24576);
        const uint64_t ph = digest(packed + 1, 7008), oh = digest(output + 16, 24576);
        local += ih != Q8K_INPUT_DIGEST || ph != Q8K_PACKED_DIGEST;
        output_hashes[trial] = oh;
        final_flags[trial] = final_fcsr;
        if (trial) local += oh != output_hashes[0] || final_fcsr != final_flags[0];
        errors += local;
        printf("Q8K_CURRENT_TRIAL id=%u path=%s admit=%lu prep=%lu execute=%lu total=%lu "
               "used=%u context=%u wide=0 segment=256 commands=48 prep_fcsr=%u final_fcsr=%u "
               "prep_vcsr=%u final_vcsr=%u input=%016lx weights=%016lx packed=%016lx output=%016lx errors=%u\n",
               trial, vector[trial] ? "canonical" : "generic", (unsigned long)(admitted - begin),
               (unsigned long)(prepared - admitted), (unsigned long)(finished - prepared),
               (unsigned long)(finished - begin), unsigned(used), unsigned(context), prep_fcsr, final_fcsr,
               prep_vcsr, final_vcsr, (unsigned long)ih, (unsigned long)weights_baseline, (unsigned long)ph,
               (unsigned long)oh, local);
    }
    const unsigned weight_errors = !weights_equal();
    errors += weight_errors;
    printf("Q8K_CURRENT_INTEGRITY scope=before_after_abba method=exact_vector_compare bytes=1327104 "
           "reference=%016lx before_equal=1 after_equal=%u errors=%u\n",
           (unsigned long)weights_baseline, unsigned(!weight_errors), weight_errors);
    printf("Q8K_CURRENT_RESULT errors=%u m=4 n=1536 k=1536 outputs=6144 trials=4 commands=192 "
           "planner=current_sdk context=direct checks=bytes_bsums_oracle_canaries_input\n", errors);
    return errors ? 1 : 0;
}
