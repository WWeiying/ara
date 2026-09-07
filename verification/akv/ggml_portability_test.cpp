#include "ggml.h"
#include "ggml-cpu.h"
#include "ggml-cpu-impl.h"
#include "arch/riscv/akv.h"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <unistd.h>

struct test_case {
    ggml_context *ctx;
    ggml_tensor *output;
    std::vector<void *> buffers;
    std::vector<float> expected;
    int gqa, features;

    test_case(int rows, int flags) : gqa(rows), features(flags) {
        ctx = ggml_init({2 * 1024 * 1024, nullptr, true});
        assert(ctx);
        const int d = 64, kv = 65, heads = rows * 2;
        auto *q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, d, 1, heads, 1);
        auto *k = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, d, kv, 2, 1);
        auto *v = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, d, kv, 2, 1);
        auto *mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, kv, 1, 1, 1);
        auto allocate = [&](ggml_tensor *t) {
            void *p = nullptr;
            assert(posix_memalign(&p, 64, ggml_nbytes(t)) == 0);
            std::memset(p, 0, ggml_nbytes(t));
            t->data = p;
            buffers.push_back(p);
        };
        for (auto *t : {q, k, v, mask}) allocate(t);
        for (int i = 0; i < heads * d; ++i)
            static_cast<float *>(q->data)[i] = (i % 13 - 6) * 0.03125f;
        for (int i = 0; i < kv * d * 2; ++i) {
            static_cast<ggml_fp16_t *>(k->data)[i] = ggml_fp32_to_fp16((i % 17 - 8) * 0.03125f);
            static_cast<ggml_fp16_t *>(v->data)[i] = ggml_fp32_to_fp16((i % 19 - 9) * 0.0625f);
        }
        for (int t = 0; t < kv; ++t) {
            float bias = flags & 1 ? -0.0625f * (kv - 1 - t) : 0.0f;
            if ((flags & 4) && (t < 64 || t % 3 == 0)) bias = -INFINITY;
            static_cast<ggml_fp16_t *>(mask->data)[t] = ggml_fp32_to_fp16(bias);
        }
        output = ggml_flash_attn_ext(ctx, q, k, v, mask, 0.125f,
                                      flags & 1 ? 2.0f : 0.0f,
                                      flags & 2 ? 1.5f : 0.0f);
        allocate(output);
        if (flags & 8) {
            auto *sinks = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, heads);
            allocate(sinks);
            for (int h = 0; h < heads; ++h) static_cast<float *>(sinks->data)[h] = 0.25f * h;
            ggml_flash_attn_ext_add_sinks(output, sinks);
        }
        auto *graph = ggml_new_graph(ctx);
        ggml_build_forward_expand(graph, output);
        assert(ggml_graph_compute_with_ctx(ctx, graph, 1) == GGML_STATUS_SUCCESS);
        const float *values = static_cast<float *>(output->data);
        expected.assign(values, values + heads * d);
    }

    ~test_case() {
        for (void *p : buffers) std::free(p);
        ggml_free(ctx);
    }

    void run() {
        ggml_compute_params params{};
        params.nth = 1;
        assert(ggml_riscv_akv_flash_attn(&params, output));
        const float *values = static_cast<float *>(output->data);
        float maximum = 0;
        for (size_t i = 0; i < expected.size(); ++i) {
            assert(std::isfinite(expected[i]) && std::isfinite(values[i]));
            maximum = std::max(maximum, std::fabs(expected[i] - values[i]));
        }
        std::printf("AKV_GGML gqa=%d features=%d max_abs=%g\n", gqa, features, maximum);
        assert(maximum < 0.002f);
    }
};

int main() {
    if (getpid() == 1) {
        mkdir("/proc", 0755); mkdir("/sys", 0755);
        mount("proc", "/proc", "proc", 0, nullptr);
        mount("sysfs", "/sys", "sysfs", 0, nullptr);
    }
    unsetenv("GGML_RISCV_AKV");
    unsetenv("GGML_RISCV_AKV_EMULATE");
    std::vector<test_case *> cases;
    for (int gqa : {3, 9, 17})
        for (int flags : {0, 1, 2, 4, 8, 15}) cases.push_back(new test_case(gqa, flags));
    setenv("GGML_RISCV_AKV_EMULATE", "1", 1);
    setenv("GGML_RISCV_AKV_PORTABLE", "1", 1);
    // Two independent graph owners exercise the process-local context mutex.
    std::thread first([&] { for (size_t i = 0; i < cases.size(); i += 2) cases[i]->run(); });
    std::thread second([&] { for (size_t i = 1; i < cases.size(); i += 2) cases[i]->run(); });
    first.join(); second.join();
    ggml_compute_params params{};
    params.nth = 1;
    setenv("GGML_RISCV_AKV_PORTABLE", "0", 1);
    assert(!ggml_riscv_akv_flash_attn(&params, cases[6]->output)); // GQA9 fallback.
    assert(!ggml_riscv_akv_flash_attn(&params, cases[1]->output)); // ALiBi fallback.
    cases[0]->run(); // Original default Decode path remains usable.
    for (auto *c : cases) delete c;
    std::puts("AKV GGML portability: PASS cases=18 concurrent_graphs=2 fallbacks=2 legacy=1");
    std::fflush(nullptr);
    if (getpid() == 1) {
        sync();
        reboot(RB_POWER_OFF);
        for (;;) pause();
    }
    return 0;
}
