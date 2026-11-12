#include PORTABLE_BACKEND_SOURCE

#define main portability_original_main
#include PORTABLE_ORACLE_SOURCE
#undef main

static unsigned checks;

static void expect(bool value) {
    assert(value);
    ++checks;
}

static void option(const char *value) {
    if (value) setenv("GGML_RISCV_AKV_PORTABLE", value, 1);
    else unsetenv("GGML_RISCV_AKV_PORTABLE");
}

static void check_case(test_case &c, bool accepted, bool selected) {
    ggml_compute_params params{};
    params.nth = 1;
    int active = 0;
    uint32_t version = 0, rows = 0, dim = 0;
    bool portable = false;
    const auto reason = supports_decode(&params, c.output, &active, &version, &rows, &dim, &portable);
    expect((reason == support_reason::supported) == accepted);
    if (accepted) {
        expect(portable == selected);
        const auto before = trace.groups.load();
        c.run();
        const uint64_t groups = 2u * ((unsigned(c.gqa) + (selected ? device().capabilities.max_q_rows : c.gqa) - 1u) /
                                      (selected ? device().capabilities.max_q_rows : c.gqa));
        expect(trace.groups.load() - before == groups);
    } else {
        c.reject();
    }
}

int main() {
    unsetenv("GGML_RISCV_AKV_EMULATE");
    unsetenv("GGML_RISCV_AKV");
    unsetenv("GGML_RISCV_ACCEL_AUTO");
    unsetenv("GGML_RISCV_AKV_KERNEL");
    unsetenv("GGML_RISCV_AKV_PORTABLE");
    // No provider must reject before touching even a null tensor/worker.
    expect(!ggml_riscv_akv_flash_attn(nullptr, nullptr));
    setenv("GGML_RISCV_AKV_EMULATE", "1", 1);
    setenv("GGML_RISCV_AKV_TRACE", "1", 1);
    const bool profile = GGML_RISCV_ACCEL_AUTO != 0;
    std::vector<test_case *> cases;
    for (int dim : {64, 96, 128})
        for (int rows : {3, 9, 32})
            for (int flags : {0, 1, 2, 8, 15}) cases.push_back(new test_case(rows, flags, dim, 17));
    for (const char *value : {static_cast<const char *>(nullptr), "auto", "0", "1", "invalid", ""}) {
        option(value);
        const bool forced = value && std::strcmp(value, "1") == 0;
        const bool automatic = profile && (!value || std::strcmp(value, "auto") == 0);
        for (auto *c : cases) {
            const bool needs_portable = c->features != 0 || c->gqa > device().capabilities.max_q_rows;
            const bool selected = forced || (automatic && needs_portable);
            check_case(*c, !needs_portable || selected, selected);
        }
    }
    // The master opt-out disables conditional defaults, not explicit overrides.
    setenv("GGML_RISCV_ACCEL_AUTO", "0", 1);
    option(nullptr);
    check_case(*cases[0], true, false);
    check_case(*cases[1], false, false);
    option("1");
    check_case(*cases[1], true, true);
    unsetenv("GGML_RISCV_ACCEL_AUTO");
    test_case holes(3, 4), plain(3, 0), d256(3, 0, 256, 17);
    option(nullptr);
    check_case(holes, false, false);
    option("1");
    check_case(holes, true, true);
    check_case(d256, false, false);
    option("0");
    check_case(d256, false, false);
    option(nullptr);
    check_case(d256, false, false);
    option("1");
    setenv("GGML_RISCV_AKV_KERNEL", "v1", 1);
    expect(!portable_decode_selected(AKV_ATTENTION_KERNEL_VERSION_V1, 32, 8, true));
    check_case(*cases[1], false, false);
    unsetenv("GGML_RISCV_AKV_KERNEL");
    const auto old_stride = plain.output->src[1]->nb[1];
    plain.output->src[1]->nb[1] += 2;
    check_case(plain, false, false);
    plain.output->src[1]->nb[1] = old_stride;
    for (float invalid : {-1.0f, INFINITY, NAN}) {
        std::memcpy(reinterpret_cast<float *>(plain.output->op_params) + 1, &invalid, sizeof(invalid));
        check_case(plain, false, false);
    }
    for (auto *c : cases) delete c;
    // Reuse the complete existing oracle, including both graph owners.
    setenv("GGML_RISCV_ACCEL_AUTO", "0", 1);
    expect(portability_original_main() == 0);
    std::printf("PORTABLE_HOST_PASS profile=%d checks=%u backend_cases=45 legacy_cases=18 native_execution=0\n",
                int(profile), checks);
}
