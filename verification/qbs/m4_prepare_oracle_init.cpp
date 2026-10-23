#include "arch-fallback.h"
#include "repack.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <sys/reboot.h>
#include <unistd.h>

static constexpr int k = 896;
static constexpr int elements = 4 * k;
static constexpr size_t bytes = (k / QK8_0) * sizeof(block_q8_0x4);
static_assert(QK8_0 == 32 && bytes == 3808, "production M4 layout changed");
alignas(64) static float activation[elements];
static block_q8_0x4 output[k / QK8_0 + 2];

[[noreturn]] static void finish(int code) {
    std::printf("M4_ORACLE_EXIT=%d\n", code);
    std::fflush(nullptr);
    sync();
    reboot(RB_POWER_OFF);
    std::printf("M4_ORACLE_FAIL reason=reboot_failed\n");
    std::fflush(nullptr);
    for (;;) pause();
}

[[noreturn]] static void fail(const char * reason) {
    std::printf("M4_ORACLE_FAIL reason=%s\n", reason);
    finish(1);
}

__attribute__((noinline)) static void production_generic() {
    ggml_quantize_mat_q8_0_4x1_generic(activation, output + 1, k);
}

int main() {
    FILE * stream = std::fopen("/capture.bin", "rb");
    if (!stream || std::fread(activation, sizeof(float), elements, stream) != elements ||
        std::fgetc(stream) != EOF || std::ferror(stream)) fail("capture_read");
    if (std::fclose(stream)) fail("capture_close");
    std::memset(output, 0xa5, sizeof(output));
    unsigned long vlenb;
    asm volatile("csrr %0, vlenb" : "=r"(vlenb) : : "memory");
    unsigned before_fcsr, before_vcsr, after_fcsr, after_vcsr;
    asm volatile("csrwi vcsr, 5\n\tcsrwi fcsr, 0\n\t"
                 "csrr %0, fcsr\n\tcsrr %1, vcsr"
                 : "=r"(before_fcsr), "=r"(before_vcsr) : : "memory");
    production_generic();
    asm volatile("csrr %0, fcsr\n\tcsrr %1, vcsr"
                 : "=r"(after_fcsr), "=r"(after_vcsr) : : "memory");
    if (before_fcsr != 0 || before_vcsr != 5 || after_fcsr > 31 || after_vcsr != 5) {
        fail("csr_contract");
    }
    const auto * guard0 = reinterpret_cast<const unsigned char *>(output);
    const auto * guard1 = reinterpret_cast<const unsigned char *>(output + k / QK8_0 + 1);
    for (size_t i = 0; i < sizeof(output[0]); ++i) {
        if (guard0[i] != 0xa5 || guard1[i] != 0xa5) fail("output_overrun");
    }
    std::printf("M4_ORACLE_BEGIN m=4 k=896 elements=3584 bytes=3808 vlen=%lu\n", vlenb * 8);
    std::printf("M4_ORACLE_CSR initial_fcsr=%u initial_vcsr=%u fcsr=%u vcsr=%u\n",
                before_fcsr, before_vcsr, after_fcsr, after_vcsr);
    const auto * data = reinterpret_cast<const unsigned char *>(output + 1);
    for (size_t offset = 0; offset < bytes; offset += 64) {
        std::printf("M4_ORACLE_HEX offset=%zu data=", offset);
        for (size_t i = offset; i < bytes && i < offset + 64; ++i) {
            std::printf("%02x", static_cast<unsigned>(data[i]));
        }
        std::putchar('\n');
    }
    std::printf("M4_ORACLE_END bytes=3808\n");
    finish(0);
}
