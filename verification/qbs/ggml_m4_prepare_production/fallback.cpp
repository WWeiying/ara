#include "arch/riscv/q8_0-m4.h"

#if GGML_RISCV_Q8_0_M4_VECTOR
#error "This compile-only target must select the generic fallback"
#endif

bool m4_fallback_compile_probe(const float * x, void * y, int64_t k) {
    return ggml_riscv_q8_0_m4::quantize(x, y, k);
}
