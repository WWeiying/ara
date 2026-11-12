#include "accel-options.h"

#include <climits>
#include <cstdio>
#include <string>
#include <vector>

static unsigned checks;

#ifdef GGML_ACCEL_TEST_WRAP_GETENV
static unsigned getenv_queries, master_queries;
extern "C" char * __real_getenv(const char * name);
extern "C" char * __wrap_getenv(const char * name) {
    ++getenv_queries;
    if (std::strcmp(name, "GGML_RISCV_ACCEL_AUTO") == 0) ++master_queries;
    return __real_getenv(name);
}
#endif

static void check(bool ok, const char * message) {
    ++checks;
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

class Environment {
    struct Saved {
        std::string name, value;
        bool present;
    };
    std::vector<Saved> saved;
public:
    void set(const char * name, const char * value) {
        const char * old = std::getenv(name);
        saved.push_back({name, old ? old : "", old != nullptr});
        check((value ? ::setenv(name, value, 1) : ::unsetenv(name)) == 0, "environment update");
    }
    ~Environment() {
        for (auto i = saved.rbegin(); i != saved.rend(); ++i) {
            if (i->present) {
                ::setenv(i->name.c_str(), i->value.c_str(), 1);
            } else {
                ::unsetenv(i->name.c_str());
            }
        }
    }
};

static bool option_is(const char * name, const char * expected) {
    const char * actual = ggml_riscv_accel_option(name);
    return expected ? actual && std::strcmp(actual, expected) == 0 : actual == nullptr;
}

#ifdef GGML_ACCEL_TEST_WRAP_GETENV
static void check_queries(const char * name, unsigned total, unsigned master) {
    getenv_queries = master_queries = 0;
    (void) ggml_riscv_accel_option(name);
    check(getenv_queries == total, "exact getenv query count");
    check(master_queries == master, "exact master getenv query count");
}
#endif

int main() {
    const bool compiled = GGML_RISCV_ACCEL_AUTO != 0;
    const char * const defaults[] = {
        "GGML_RISCV_QBS", "GGML_RISCV_AKV",
        "GGML_RISCV_QBS_ACTIVATION_CONTEXT", "GGML_RISCV_QBS_CROSS_OP_CONTEXT",
        "GGML_RISCV_QBS_M4_PREPARE", "GGML_RISCV_QBS_M4_PACKED",
        "GGML_RISCV_QBS_M4_PARALLEL_SUMS", "GGML_RISCV_QBS_M4_CACHE",
        "GGML_RISCV_QBS_M4_PREFLIGHT",
        "GGML_RISCV_AKV_QUANT_KV", "GGML_RISCV_AKV_QUANT_PREFILL",
        "GGML_RISCV_AKV_REGISTER_PV",
    };
    const char * const blocked[] = {
        "GGML_RISCV_QBS_WIDE_M", "GGML_RISCV_QBS_EMULATE", "GGML_RISCV_AKV_EMULATE",
        "GGML_RISCV_AKV_NORMAL_MEMORY", "GGML_RISCV_QBS_NORMAL_MEMORY",
        "GGML_RISCV_AKV_CAPABILITY", "GGML_RISCV_AKV_RESIDENT",
        "GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "GGML_RISCV_AKV_GROUPED_PV",
        "GGML_RISCV_QBS_TRACE", "GGML_RISCV_AKV_TRACE", "GGML_RISCV_QBS_TRACE_CALLS",
        "GGML_RISCV_QBS_TRACE_LIFETIME", "GGML_RISCV_QBS_TRACE_M4_PREPARE",
        "GGML_RISCV_ACCEL_UNKNOWN",
    };
    Environment env;
    env.set("GGML_RISCV_ACCEL_AUTO", nullptr);
    env.set("GGML_RISCV_AKV_KERNEL", nullptr);
    for (const char * name : defaults) env.set(name, nullptr);
    for (const char * name : blocked) env.set(name, nullptr);
    check(!ggml_riscv_accel_option(nullptr), "null name");
#ifdef GGML_ACCEL_TEST_WRAP_GETENV
    check_queries(nullptr, 0, 0);
#endif
    check(!ggml_riscv_accel_option(""), "empty name");
    check(!ggml_riscv_accel_true(nullptr), "null boolean");
    for (const char * value : {"1", "true", "TRUE", "yes", "YES", "on", "ON"}) {
        check(ggml_riscv_accel_true(value), "recognized true spelling");
    }
    for (const char * value : {"0", "", "false", "auto", "TRUE ", "2", "invalid"}) {
        check(!ggml_riscv_accel_true(value), "invalid/false boolean");
    }
    check(ggml_riscv_accel_auto_enabled() == compiled, "compile default");
    for (const char * name : defaults) {
        check(option_is(name, compiled ? "1" : nullptr), "allowlisted default");
#ifdef GGML_ACCEL_TEST_WRAP_GETENV
        check_queries(name, 2, 1);
#endif
        for (const char * value : {"0", "", "1", "invalid"}) {
            Environment explicit_value;
            explicit_value.set(name, value);
            check(option_is(name, value), "explicit value wins verbatim");
#ifdef GGML_ACCEL_TEST_WRAP_GETENV
            check_queries(name, 1, 0);
#endif
        }
    }
    check(option_is("GGML_RISCV_AKV_KERNEL", compiled ? "auto" : nullptr), "kernel default");
#ifdef GGML_ACCEL_TEST_WRAP_GETENV
    check_queries("GGML_RISCV_AKV_KERNEL", 2, 1);
#endif
    {
        Environment explicit_kernel;
        explicit_kernel.set("GGML_RISCV_AKV_KERNEL", "v2");
        check(option_is("GGML_RISCV_AKV_KERNEL", "v2"), "explicit kernel");
    }
    for (const char * name : blocked) {
        check(option_is(name, nullptr), "no unsafe/diagnostic/unknown default");
#ifdef GGML_ACCEL_TEST_WRAP_GETENV
        check_queries(name, 1, 0);
#endif
    }
    {
        Environment explicit_unknown;
        explicit_unknown.set("GGML_RISCV_ACCEL_UNKNOWN", "0");
        check(option_is("GGML_RISCV_ACCEL_UNKNOWN", "0"), "explicit getenv precedes default lookup");
    }

    for (const char * master : {"0", "", "invalid", "false", "1", "true", "TRUE", "yes", "YES", "on", "ON"}) {
        Environment master_value;
        master_value.set("GGML_RISCV_ACCEL_AUTO", master);
        const bool automatic = compiled && ggml_riscv_accel_true(master);
        for (const char * name : defaults) {
            check(option_is(name, automatic ? "1" : nullptr), "master default control");
        }
        check(option_is("GGML_RISCV_AKV_KERNEL", automatic ? "auto" : nullptr), "master kernel control");
        for (const char * request : {"auto", "1", "true", "TRUE", "yes", "YES", "on", "ON", "0", "", "invalid", "AUTO"}) {
            Environment resident;
            resident.set("GGML_RISCV_AKV_RESIDENT", request);
            for (unsigned dim : {0u, 64u, 96u, 128u, 256u, UINT_MAX}) {
                for (unsigned rows : {0u, 1u, 2u, 3u, UINT_MAX}) {
                    for (unsigned tokens : {0u, 127u, 128u, 129u, 255u, 256u, 257u, UINT_MAX}) {
                        const bool expected = std::strcmp(request, "auto") == 0
                            ? automatic && dim == 128 && rows == 2 && tokens >= 128 && tokens <= 256
                            : ggml_riscv_accel_true(request);
                        check(ggml_riscv_accel_resident_requested(dim, rows, tokens) == expected,
                              "resident explicit/auto bounds");
                    }
                }
            }
        }
        for (unsigned tokens : {127u, 128u, 256u, 257u}) {
            check(ggml_riscv_accel_resident_requested(128, 2, tokens) ==
                  (automatic && tokens >= 128 && tokens <= 256), "unset resident bounds");
        }
        Environment explicit_value;
        explicit_value.set("GGML_RISCV_QBS", "1");
        check(option_is("GGML_RISCV_QBS", "1"), "master cannot suppress explicit flag");
    }
    std::printf("PASS AUTO=%d checks=%u\n", int(compiled), checks);
}
