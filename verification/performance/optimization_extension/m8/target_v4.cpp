#include "q8_K-m8.h"
#include "qbs.h"
#include "qbs/qbs.h"

extern "C" const unsigned test_case;
extern "C" const float real_attn[], real_ffn[];
extern "C" void test_text(const char *);
extern "C" void test_number(uint64_t);
extern "C" void test_exit(unsigned) __attribute__((noreturn));
extern "C" void frozen_generic(const float *, void *, int64_t);

extern "C" int strcmp(const char *a, const char *b) noexcept {
    while (*a && *a == *b) { ++a; ++b; }
    return static_cast<unsigned char>(*a) - static_cast<unsigned char>(*b);
}

static constexpr int K = 2048, Rows = 16;
static constexpr size_t Bytes = Rows*(K/256)*sizeof(block_q8_K);
alignas(64) static float input[Rows*K], saved[Rows*K];
alignas(64) static unsigned char actual[Bytes + 128], expected[Bytes + 128], m4[Bytes];
static unsigned checks, generic_calls, info5_reads;

static unsigned fcsr() { unsigned v; asm volatile("frcsr %0":"=r"(v)::"memory"); return v; }
static unsigned vcsr() { unsigned v; asm volatile("csrr %0,vcsr":"=r"(v)::"memory"); return v; }
static unsigned vstart() { unsigned v; asm volatile("csrr %0,vstart":"=r"(v)::"memory"); return v; }
static void state(unsigned f, unsigned v) {
    asm volatile("csrw fcsr,%0; csrw vcsr,%1; csrwi vstart,0"::"r"(f),"r"(v):"memory");
}
static void need(bool ok, const char *why) {
    ++checks;
    if (!ok) { test_text("M8_FAIL "); test_text(why); test_text("\n"); test_exit(1); }
}
static bool untouched() {
    for (auto byte : actual) if (byte != 0xa5) return false;
    return true;
}
extern "C" void ggml_abort(const char *, int, const char *, ...) {
    if (test_case == 11 && vstart() == 1 && fcsr() == 17 && vcsr() == 5 &&
        !generic_calls && untouched()) {
        test_text("M8_VSTART_ABORT_PASS output_untouched=1 generic_calls=0\n"); test_exit(0);
    }
    test_text("M8_UNEXPECTED_ABORT\n"); test_exit(3);
}
extern "C" void ggml_quantize_mat_q8_K_4x1_ara_generic(const float *x, void *y, int64_t k) {
    ++generic_calls; frozen_generic(x, y, k);
}
extern "C" char *getenv(const char *name) noexcept {
    const char *value = nullptr;
    if (std::strcmp(name, "GGML_RISCV_QBS_WIDE_M") == 0) {
        if (test_case == 13) value = "0";
        if (test_case == 15) value = "1";
    }
    if (test_case == 14 && std::strcmp(name, "GGML_RISCV_ACCEL_AUTO") == 0) value = "0";
    if (test_case == 16 && std::strcmp(name, "GGML_RISCV_QBS_M4_PREPARE") == 0) value = "0";
    if (test_case == 17 && std::strcmp(name, "GGML_RISCV_QBS_M4_PACKED") == 0) value = "0";
    if (test_case == 26 && std::strcmp(name, "GGML_RISCV_QBS_M4_PARALLEL_SUMS") == 0) value = "0";
    return const_cast<char *>(value);
}

// Only the hardware information transport is supplied by this test.
extern "C" uint64_t qbs_native_info(void *, unsigned index) {
    if (index == 5) { ++info5_reads; return test_case == 12 ? 0 : 1; }
    return qbs_capability_word(index, 1024);
}

static void interleave(int rows, int k) {
    auto *dst = reinterpret_cast<ggml_riscv_q8_K_m8::block *>(expected + 64);
    for (int first = 0; first < rows; first += 8) for (int b = 0; b < k/256; ++b) {
        auto &out = dst[(first/8)*(k/256) + b];
        for (int row = 0; row < 8; ++row) {
            const auto &in = reinterpret_cast<const block_q8_Kx4 *>(m4)[((first + row)/4)*(k/256) + b];
            out.d[row] = in.d[row%4];
            for (int j = 0; j < 256; ++j) out.qs[8*j + row] = in.qs[4*j + row%4];
            for (int j = 0; j < 16; ++j) out.bsums[8*j + row] = in.bsums[4*j + row%4];
        }
    }
}

int main() {
    const int rows = (test_case == 5 || test_case == 23) ? 16 : 8;
    const int k = test_case == 4 ? 256 : (test_case == 25 ? 1536 : K);
    for (int r = 0; r < Rows; ++r) {
        std::memcpy(input + r*k, (test_case == 1 ? real_ffn : real_attn) + (r%8)*K, k*sizeof(float));
    }
    if (test_case == 2) {
        for (int r = 0; r < rows; ++r) for (int b = 0; b < k/256; ++b) {
            float *x = input + r*k + b*256;
            for (int i = 0; i < 256; ++i) x[i] = (i%2 ? -1.0f : 1.0f)*(float(i%127) + 0.5f);
            x[0] = r%2 ? -127.0f : 127.0f;
            x[1] = -x[0];
            const uint32_t near_half[] = {0x3f000000u, 0x3effffffu, 0x3f000001u};
            std::memcpy(x + 3, near_half, sizeof(near_half));
        }
    }
    if (test_case == 3) {
        for (int i = 0; i < rows*k; ++i) { const uint32_t zero = i%2 ? 0x80000000u : 0; std::memcpy(input + i, &zero, 4); }
    }
    if ((test_case >= 6 && test_case <= 9) || test_case == 23) {
        const uint32_t bad[] = {1u, 0x7f800000u, 0x7fc01234u, 0x7f801234u};
        const uint32_t value = bad[test_case == 23 ? 3 : test_case - 6];
        std::memcpy(input + rows*k - 1, &value, 4);
    }
    std::memcpy(saved, input, sizeof(input));
    std::memset(actual, 0xa5, sizeof(actual));
    std::memset(expected, 0xa5, sizeof(expected));
    state(17, 5);
    ggml_riscv_qbs_activation_plan plan{};
    const auto type = test_case == 18 ? GGML_TYPE_Q5_K : GGML_TYPE_Q4_K;
    const int plan_rows = test_case == 19 ? 4 : rows;
    const int n = test_case == 20 ? 16 : 64;
    need(ggml_riscv_qbs_plan_activations(type, plan_rows, n, k, &plan, test_case != 27), "plan_valid");
    const bool selected = (test_case < 12 && test_case != 4) || (test_case >= 21 && test_case <= 24) || test_case >= 28;
    need(plan.direct_m8 == selected && plan.wide_m == (selected || test_case == 15), "capability_shape_options");
    need(info5_reads == unsigned(test_case != 14), "actual_sdk_device_query_reads_info5");
    if (selected) {
        need(plan.packed_bytes == size_t(rows*(k/256))*sizeof(block_q8_K), "payload_exact_no_marker");
        need(plan.workspace_bytes == plan.packed_bytes + 1 && !plan.row_major_offset, "only_one_decision_byte");
    }
    need(fcsr() == 17 && vcsr() == 5 && vstart() == 0, "plan_csr");
    if (!selected) {
        need(untouched(), "selection_no_output");
    } else {
        const bool reject = (test_case >= 6 && test_case <= 10) || test_case >= 21;
        const unsigned f = test_case == 10 ? 49 : 17;
        state(reject ? f : 0, 5);
        if (test_case == 11) state(17, 5);
        if (test_case == 11) asm volatile("csrwi vstart,1":::"memory");
        const float *source = input;
        void *destination = actual + 64;
        int64_t call_rows = rows, call_k = k;
        size_t row_stride = size_t(k)*4 + (test_case == 21 ? 4 : 0);
        if (test_case == 30) call_rows = INT64_MAX - 7;
        if (test_case == 31) { call_k = INT64_MAX - 255; row_stride = size_t(call_k)*4; }
        if (test_case == 32) source = reinterpret_cast<const float *>(UINTPTR_MAX - 3);
        if (test_case == 33) destination = reinterpret_cast<void *>(UINTPTR_MAX - 3);
        if (test_case == 34) destination = input;
        if (test_case == 35) destination = input + 1;
        if (test_case == 36) destination = actual + 65;
        if (test_case == 37) source = reinterpret_cast<const float *>(reinterpret_cast<const char *>(input) + 1);
        const bool produced = ggml_riscv_qbs_prepare_m8(source, destination, call_rows, call_k,
            test_case == 22 ? 8 : 4, row_stride, test_case == 24 ? 2 : 1,
            test_case == 28, test_case == 29);
        need(produced != reject, "admission");
        if (reject) {
            need(untouched() && !generic_calls && fcsr() == f && vcsr() == 5 && !vstart(), "reject_no_partial_write_or_flags");
        } else {
            const unsigned raised = fcsr() & 31;
            need(!generic_calls && vcsr() == 5 && !vstart(), "direct_no_generic_or_vcsr_change");
            state(0, 5);
            for (int row = 0; row < rows; row += 4) {
                need(ggml_riscv_q8_K_m4_packed::selected_quantize(input + row*k,
                    m4 + size_t(row)*(k/256)*sizeof(block_q8_K), k), "oracle_actual_selected_m4");
            }
            need((fcsr() & 31) == raised && vcsr() == 5, "m4_m8_exact_fflags");
            interleave(rows, k);
            need(std::memcmp(expected, actual, sizeof(actual)) == 0, "exact_m4_bytes_layout_guards");
            for (unsigned flags = 0; flags < 32; ++flags) {
                std::memset(actual, 0xa5, sizeof(actual)); state(flags, flags%8);
                need(ggml_riscv_qbs_prepare_m8(input, actual + 64, rows, k, 4, size_t(k)*4), "sticky_production");
                need(fcsr() == (flags | raised) && vcsr() == flags%8 && !vstart(), "sticky_fflags_vcsr");
                need(std::memcmp(expected, actual, sizeof(actual)) == 0, "sticky_bytes");
            }
        }
    }
    need(std::memcmp(input, saved, sizeof(input)) == 0, "input_immutable");
    test_text("M8_TARGET_PASS case="); test_number(test_case);
    test_text(" checks="); test_number(checks); test_text("\n");
    return 0;
}
