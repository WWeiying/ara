#include "q8_K-m8.h"
#include "qbs/qbs.h"
#include "sdk_pair_config.h"
#include "printf.h"

enum { M = 8, K = 2048, N = 32, KB = 8, AB = M*KB*292, WB = N*KB*144, Guard = 64 };
extern "C" const float pair_input[M*K];
extern "C" const unsigned char pair_weights[WB], pair_m4[AB], pair_m8[AB];
extern "C" const float pair_expected[M*N];
extern "C" const unsigned pair_engine_flags, pair_prep_flags;
extern "C" void frozen_generic(const float *, void *, int64_t);
extern "C" void ggml_quantize_mat_q8_K_4x1_ara_generic(const float *x, void *y, int64_t k) { frozen_generic(x, y, k); }
static struct { unsigned char before[Guard], data[AB], after[Guard]; } activation __attribute__((aligned(64)));
static struct { unsigned char before[Guard]; float data[M*N]; unsigned char after[Guard]; } output __attribute__((aligned(64)));
static float snapshots[4][M*N];
static unsigned char payloads[4][AB];
static const unsigned modes[4] = {4, 8, 8, 4}, seeds[4] = {0, 8, 0, 8};
struct record { uint64_t t[5]; unsigned flags, prep_flags, vcsr, status, commands, coop, payload_bad, output_bad, guard_bad; };
static inline uint64_t cycles() { uint64_t v; asm volatile("rdcycle %0":"=r"(v)::"memory"); return v; }
static qbs_status_t native(void *context, const qbs_descriptor_t *d, unsigned m, const void *a,
                         float *out, size_t stride, unsigned n, int segmented) {
    ++static_cast<record *>(context)->commands;
    return qbs_native_execute_command(nullptr, d, m, a, out, stride, n, segmented);
}
extern "C" void ggml_abort(const char *, int, const char *, ...) {
    printf("EXTENSION_M8_ABORT\n"); asm volatile("unimp"); __builtin_unreachable();
}
__attribute__((noinline, noclone)) static void trial(unsigned mode, unsigned seed, record *r) {
    qbs_device_t device{};
    qbs_plan_t plan{};
    qbs_execution_options_t options{};
    const qbs_problem_t problem = {QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_K,
        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        uint8_t(mode == 8 ? QBS_ACTIVATION_STORAGE_M8_GROUPED : QBS_ACTIVATION_STORAGE_M4_GROUPED), M, N, K};
    asm volatile("csrw fflags,%0;csrwi vcsr,5;csrwi vstart,0"::"r"(seed):"memory");
    r->t[0] = cycles();
    bool produced = true;
    if (mode == 8) produced = ggml_riscv_q8_K_m8::quantize(pair_input, activation.data, M, K);
    else for (unsigned row = 0; row < M; row += 4)
        produced = ggml_riscv_q8_K_m4_packed::selected_quantize(pair_input + row*K, activation.data + row*KB*292, K) && produced;
    r->t[1] = cycles();
    asm volatile("frflags %0":"=r"(r->prep_flags)::"memory");
    qbs_status_t status = produced ? qbs_device_query(qbs_native_info, nullptr, &device) : QBS_STATUS_SHAPE;
    r->coop = device.capabilities.q4_k_cooperative;
    if (status == QBS_STATUS_OK && !r->coop) status = QBS_STATUS_CAPABILITY;
    if (status == QBS_STATUS_OK) status = qbs_plan_create(&device, &problem, &plan);
    if (status == QBS_STATUS_OK && (plan.command_m != mode || plan.command_n != 32 || plan.wide_command_n != 16 ||
        plan.k_blocks != KB || plan.split_k || plan.needs_activation_gather || plan.workspace_bytes ||
        qbs_plan_supports_activation_context(&plan))) status = QBS_STATUS_SHAPE;
    r->t[2] = cycles();
    if (status == QBS_STATUS_OK) status = qbs_execute_with_options(&plan, pair_weights, WB,
        activation.data, AB, output.data, M*N, N, nullptr, 0, &options, native, r);
    r->t[3] = cycles();
    asm volatile("fence rw,rw":::"memory");
    r->t[4] = cycles();
    asm volatile("frflags %0;csrr %1,vcsr":"=r"(r->flags),"=r"(r->vcsr)::"memory");
    r->status = status;
}
static unsigned bits(float value) { unsigned v; std::memcpy(&v, &value, 4); return v; }
int main() {
    record records[4]{};
    std::memset(&activation, 0xa5, sizeof(activation)); std::memset(&output, 0xa5, sizeof(output));
    asm volatile("csrwi fcsr,0;csrwi vstart,0":::"memory");
    for (unsigned t = 0; t < 4; ++t) {
        std::memset(output.data, 0x5a, sizeof(output.data));
        trial(modes[t], seeds[t], &records[t]);
        std::memcpy(snapshots[t], output.data, sizeof(output.data));
        std::memcpy(payloads[t], activation.data, AB);
        for (unsigned i = 0; i < Guard; ++i) records[t].guard_bad +=
            activation.before[i] != 0xa5 || activation.after[i] != 0xa5 || output.before[i] != 0xa5 || output.after[i] != 0xa5;
    }
    unsigned errors = 0;
    printf("EXTENSION_M8_META id=%s m=8 k=2048 n=32 trials=4 whole_model=0 cache=0\n", SDK_PAIR_ID);
    for (unsigned t = 0; t < 4; ++t) {
        auto &r = records[t];
        const auto *expected_payload = modes[t] == 8 ? pair_m8 : pair_m4;
        for (unsigned i = 0; i < AB; ++i) r.payload_bad += payloads[t][i] != expected_payload[i];
        for (unsigned i = 0; i < M*N; ++i) r.output_bad += bits(snapshots[t][i]) != bits(pair_expected[i]);
        const unsigned wanted = pair_engine_flags | pair_prep_flags | seeds[t];
        errors += r.status != QBS_STATUS_OK || r.coop != 1 || r.commands != 2 || r.payload_bad || r.output_bad || r.guard_bad ||
            r.flags != wanted || r.prep_flags != (pair_prep_flags | seeds[t]) || r.vcsr != 5;
        printf("EXTENSION_M8_TRIAL id=%u mode=%u status=%u commands=%u coop=%u prep=%lu plan=%lu execute=%lu drain=%lu total=%lu "
            "flags=%u prep_flags=%u vcsr=%u payload_bad=%u output_bad=%u guard_bad=%u\n", t, modes[t], r.status, r.commands, r.coop,
            r.t[1]-r.t[0], r.t[2]-r.t[1], r.t[3]-r.t[2], r.t[4]-r.t[3], r.t[4]-r.t[0], r.flags, r.prep_flags, r.vcsr,
            r.payload_bad, r.output_bad, r.guard_bad);
        for (unsigned row = 0; row < M; ++row) for (unsigned col = 0; col < N; ++col)
            printf("EXTENSION_M8_OUTPUT trial=%u row=%u col=%u bits=%08x\n", t, row, col, bits(snapshots[t][row*N+col]));
    }
    printf("EXTENSION_M8_%s errors=%u\n", errors ? "FAIL" : "PASS", errors);
    return errors != 0;
}
