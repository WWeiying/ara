#include <cstdint>
#include <cstdlib>
#include <cstring>
#include "accel-options.h"

#define AKV_ATTENTION_KERNEL_VERSION_V2 2u
#define GGML_UNUSED(x) (void)(x)
#include "portable_selection.inc"

extern "C" void test_text(const char *);
extern "C" void test_number(uint64_t);
static const char *portable_value;
static const char *master_value;

extern "C" char *getenv(const char *name) noexcept {
    if (std::strcmp(name, "GGML_RISCV_AKV_PORTABLE") == 0) return const_cast<char *>(portable_value);
    if (std::strcmp(name, "GGML_RISCV_ACCEL_AUTO") == 0) return const_cast<char *>(master_value);
    return nullptr;
}

extern "C" int strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return int(static_cast<unsigned char>(*a)) - int(static_cast<unsigned char>(*b));
}

int main() {
    const char *const portable_modes[] = {nullptr, "auto", "0", "1", "invalid", "TRUE", ""};
    const char *const master_modes[] = {nullptr, "0", "1", "invalid"};
    const uint32_t sizes[] = {1, 8, 9, 32};
    unsigned checks = 0;
    for (unsigned m = 0; m < 4; ++m) {
        master_value = master_modes[m];
        for (unsigned p = 0; p < 7; ++p) {
            portable_value = portable_modes[p];
            for (uint32_t rows : sizes)
                for (uint32_t version = 1; version <= 2; ++version)
                    for (unsigned features = 0; features <= 1; ++features) {
                        bool expected = false;
#ifdef GGML_AKV_PORTABLE_FEATURES
                        if (version == 2) {
                            if (p == 3 || p == 5) expected = true;
                            if (p < 2 && GGML_RISCV_ACCEL_AUTO && (m == 0 || m == 2))
                                expected = features || rows > 8;
                        }
#endif
                        if (portable_decode_selected(version, rows, 8, features != 0) != expected) {
                            test_text("PORTABLE_TARGET_FAIL check="); test_number(checks); return 1;
                        }
                        ++checks;
                    }
        }
    }
    test_text("PORTABLE_TARGET_PASS checks="); test_number(checks);
    test_text(" profile="); test_number(GGML_RISCV_ACCEL_AUTO);
    test_text(" features=");
#ifdef GGML_AKV_PORTABLE_FEATURES
    test_number(1);
#else
    test_number(0);
#endif
    test_text(" selector_only=1 native_execution=0\n");
    return 0;
}
