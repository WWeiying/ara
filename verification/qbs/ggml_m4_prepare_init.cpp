#define main m4_prepare_test_main
#include "test_ggml_m4_prepare_candidate.cpp"
#undef main
#include <sys/reboot.h>
#include <unistd.h>

int main() {
    const int result = m4_prepare_test_main();
    std::vector<float> capture(4 * 896);
    FILE * stream = std::fopen("/capture.bin", "rb");
    if (!stream || std::fread(capture.data(), sizeof(float), capture.size(), stream) != capture.size()
            || std::fgetc(stream) != EOF) {
        std::fprintf(stderr, "M4_PREPARE_FAIL invalid_real_capture\n");
        return 1;
    }
    std::fclose(stream);
    const size_t previous_checks = checks, previous_vector = vector_checks;
    const size_t previous_fallback = fallback_checks;
    check("real_qwen25_projection_m4_k896", capture, true);
    std::printf("M4_CAPTURE_PASS elements=%zu checks=%zu vector=%zu fallback=%zu\n",
                capture.size(), checks - previous_checks, vector_checks - previous_vector,
                fallback_checks - previous_fallback);
    std::printf("M4_PREPARE_GUEST_EXIT=%d\n", result);
    std::fflush(nullptr);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
