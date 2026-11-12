#include "q8_K-m8.h"
extern "C" const float real_attn[];
extern "C" void test_text(const char *);
extern "C" void test_exit(unsigned) __attribute__((noreturn));
extern "C" void frozen_generic(const float *, void *, int64_t);
extern "C" {
alignas(64) unsigned char export_m4[8*8*292], export_m8[8*8*292];
unsigned export_flags;
char *getenv(const char *) noexcept { return nullptr; }
int strcmp(const char *a, const char *b) noexcept {
    while (*a && *a == *b) { ++a; ++b; }
    return static_cast<unsigned char>(*a) - static_cast<unsigned char>(*b);
}
void ggml_abort(const char *, int, const char *, ...) { test_text("M8_EXPORT_FAIL\n"); test_exit(1); }
void ggml_quantize_mat_q8_K_4x1_ara_generic(const float *x, void *y, int64_t k) { frozen_generic(x, y, k); }
}
int main() {
    asm volatile("csrwi fcsr,0;csrwi vcsr,5;csrwi vstart,0":::"memory");
    for (int row = 0; row < 8; row += 4)
        if (!ggml_riscv_q8_K_m4_packed::selected_quantize(real_attn + row*2048, export_m4 + row*8*292, 2048)) test_exit(2);
    asm volatile("frflags %0":"=r"(export_flags)::"memory");
    asm volatile("csrwi fflags,0":::"memory");
    if (!ggml_riscv_q8_K_m8::quantize(real_attn, export_m8, 8, 2048)) test_exit(3);
    unsigned flags, vc;
    asm volatile("frflags %0;csrr %1,vcsr":"=r"(flags),"=r"(vc)::"memory");
    if (flags != export_flags || vc != 5) test_exit(4);
    test_text("M8_EXPORT_PASS\n");
    return 0;
}
