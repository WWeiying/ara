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

#ifndef AKV_TEST_D256
#define AKV_TEST_D256 0
#endif

struct test_case {
    struct buffer {
        unsigned char *allocation;
        size_t bytes;
    };
    ggml_context *ctx;
    ggml_tensor *output;
    std::vector<buffer> buffers;
    std::vector<float> expected;
    int gqa, features, dim, length;

    test_case(int rows, int flags, int d = 64, int kv = 65)
        : gqa(rows), features(flags), dim(d), length(kv) {
        ctx = ggml_init({2 * 1024 * 1024, nullptr, true});
        assert(ctx);
        const int heads = rows * 2;
        auto *q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, d, 1, heads, 1);
        auto *k = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, d, kv, 2, 1);
        auto *v = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, d, kv, 2, 1);
        auto *mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, kv, 1, 1, 1);
        auto allocate = [&](ggml_tensor *t) {
            void *p = nullptr;
            const size_t bytes = ggml_nbytes(t);
            assert(posix_memalign(&p, 64, bytes + 128) == 0);
            auto *allocation = static_cast<unsigned char *>(p);
            std::memset(allocation, 0xa5, bytes + 128);
            t->data = allocation + 64;
            std::memset(t->data, 0, bytes);
            buffers.push_back({allocation, bytes});
        };
        for (auto *t : {q, k, v, mask}) allocate(t);
        for (int i = 0; i < heads * d; ++i)
            static_cast<float *>(q->data)[i] = (i % 13 - 6) * 0.03125f;
        for (int i = 0; i < kv * d * 2; ++i) {
            static_cast<ggml_fp16_t *>(k->data)[i] = ggml_fp32_to_fp16((i % 17 - 8) * 0.03125f);
            static_cast<ggml_fp16_t *>(v->data)[i] = ggml_fp32_to_fp16((i % 19 - 9) * 0.0625f);
        }
        for (int t = 0; t < kv; ++t) {
            float bias = flags & (1 | 32) ? -0.0625f * (kv - 1 - t) : 0.0f;
            if ((flags & 4) && (t < 64 || t % 3 == 0)) bias = -INFINITY;
            if ((flags & 16) && t >= kv - 3) bias = -INFINITY;
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
        check_guards();
        for (const auto &b : buffers) std::free(b.allocation);
        ggml_free(ctx);
    }

    void check_guards() const {
        for (const auto &b : buffers)
            for (size_t i = 0; i < 64; ++i) {
                assert(b.allocation[i] == 0xa5);
                assert(b.allocation[64 + b.bytes + i] == 0xa5);
            }
    }

    void reject() const {
        ggml_compute_params params{};
        params.nth = 1;
        std::vector<unsigned char> before(ggml_nbytes(output));
        std::memcpy(before.data(), output->data, before.size());
        assert(!ggml_riscv_akv_flash_attn(&params, output));
        assert(std::memcmp(before.data(), output->data, before.size()) == 0);
        check_guards();
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
        std::printf("AKV_GGML d=%d kv=%d gqa=%d features=%d max_abs=%g\n",
                    dim, length, gqa, features, maximum);
        assert(maximum < 0.002f);
        check_guards();
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
    unsetenv("GGML_RISCV_AKV_D256");
    unsetenv("GGML_RISCV_AKV_KERNEL");
    std::vector<test_case *> cases;
    for (int gqa : {3, 9, 17})
        for (int flags : {0, 1, 2, 4, 8, 15}) cases.push_back(new test_case(gqa, flags));
#if AKV_TEST_D256
    std::vector<test_case *> d256_cases;
    for (int gqa : {1, 3, 4, 8, 9})
        for (int kv : {17, 65, 140}) d256_cases.push_back(new test_case(gqa, 0, 256, kv));
    d256_cases.push_back(new test_case(4, 16, 256, 140));
    std::vector<test_case *> d256_fallbacks;
    for (int flags : {1, 2, 4, 8, 32}) d256_fallbacks.push_back(new test_case(4, flags, 256, 140));
    test_case d96(4, 0, 96, 17), d128(4, 0, 128, 17);
#endif
    setenv("GGML_RISCV_AKV_EMULATE", "1", 1);
    setenv("GGML_RISCV_AKV_PORTABLE", "1", 1);
    // Two independent graph owners exercise the process-local context mutex.
    std::thread first([&] { for (size_t i = 0; i < cases.size(); i += 2) cases[i]->run(); });
    std::thread second([&] { for (size_t i = 1; i < cases.size(); i += 2) cases[i]->run(); });
    first.join(); second.join();
#if AKV_TEST_D256
    for (auto *c : d256_cases) c->reject(); // Default D256 admission stays off.
    setenv("GGML_RISCV_AKV_D256", "1", 1);
    for (auto *c : d256_cases) c->run();
    for (auto *c : d256_fallbacks) c->reject();
    auto *layout = d256_cases[0]->output->src[1];
    const size_t old_stride = layout->nb[1];
    layout->nb[1] += 2;
    d256_cases[0]->reject();
    layout->nb[1] = old_stride;
    setenv("GGML_RISCV_AKV_KERNEL", "v1", 1);
    d256_cases[0]->reject();
    unsetenv("GGML_RISCV_AKV_KERNEL");
    d96.run(); d128.run();
#endif
    ggml_compute_params params{};
    params.nth = 1;
    setenv("GGML_RISCV_AKV_PORTABLE", "0", 1);
    assert(!ggml_riscv_akv_flash_attn(&params, cases[6]->output)); // GQA9 fallback.
    assert(!ggml_riscv_akv_flash_attn(&params, cases[1]->output)); // ALiBi fallback.
    cases[0]->run(); // Original default Decode path remains usable.
#if AKV_TEST_D256
    d256_cases[0]->run(); // D256 does not require optional feature handling.
    d256_cases[12]->reject(); // GQA9 needs the portable grouping adapter.
    unsetenv("GGML_RISCV_AKV_D256");
    d256_cases[0]->reject();
    for (auto *c : d256_cases) delete c;
    for (auto *c : d256_fallbacks) delete c;
#endif
    for (auto *c : cases) delete c;
    std::puts("AKV GGML portability: PASS cases=18 concurrent_graphs=2 fallbacks=2 legacy=1");
#if AKV_TEST_D256
    std::puts("AKV GGML D256: PASS cases=16 default_fallbacks=16 feature_fallbacks=5 layout=1 v1=1 gqa=1 optout=1 legacy_dims=2 guards=1");
#endif
    std::fflush(nullptr);
    if (getpid() == 1) {
        sync();
        reboot(RB_POWER_OFF);
        for (;;) pause();
    }
    return 0;
}
