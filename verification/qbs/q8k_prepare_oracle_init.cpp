#include "arch-fallback.h"
#include "repack.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <sys/reboot.h>
#include <unistd.h>

static constexpr int k = 1536;
static_assert(QK_K == 256 && sizeof(block_q8_Kx4) == 1168, "layout changed");
alignas(64) static float input[4 * k];
alignas(64) static block_q8_Kx4 output[k / QK_K + 2];

[[noreturn]] static void finish(int code) {
    std::printf("Q8K_ORACLE_EXIT=%d\n", code);
    std::fflush(nullptr);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}

int main() {
    FILE * stream = std::fopen("/capture.bin", "rb");
    if (!stream || std::fread(input, sizeof(float), 4*k, stream) != 4*k ||
        std::fgetc(stream) != EOF || std::ferror(stream)) finish(1);
    if (std::fclose(stream)) finish(2);
    std::memset(output, 0xa5, sizeof(output));
    asm volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
    ggml_quantize_mat_q8_K_4x1_ara_generic(input, output + 1, k);
    unsigned fcsr, vcsr;
    asm volatile("frcsr %0; csrr %1, vcsr" : "=r"(fcsr), "=r"(vcsr) : : "memory");
    if (fcsr > 31 || vcsr != 5) finish(3);
    for (int index : {0, k / QK_K + 1}) {
        const auto * guard = reinterpret_cast<const unsigned char *>(&output[index]);
        for (size_t j = 0; j < sizeof(output[0]); ++j) if (guard[j] != 0xa5) finish(4);
    }
    constexpr size_t bytes = (k / QK_K) * sizeof(output[0]);
    std::printf("Q8K_ORACLE_BEGIN m=4 k=1536 bytes=7008\n");
    std::printf("Q8K_ORACLE_CSR fcsr=%u vcsr=%u\n", fcsr, vcsr);
    const auto * data = reinterpret_cast<const unsigned char *>(output + 1);
    for (size_t offset = 0; offset < bytes; offset += 64) {
        std::printf("Q8K_ORACLE_HEX offset=%zu data=", offset);
        for (size_t j = offset; j < bytes && j < offset + 64; ++j) std::printf("%02x", unsigned(data[j]));
        std::putchar('\n');
    }
    std::printf("Q8K_ORACLE_END bytes=7008\n");
    finish(0);
}
