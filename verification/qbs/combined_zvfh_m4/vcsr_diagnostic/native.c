#include "ggml-quants.h"
#include "ggml-cpu/quants.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned read_fcsr(void) {
    unsigned value;
    __asm__ volatile("frcsr %0" : "=r"(value) : : "memory");
    return value;
}

static unsigned read_vcsr(void) {
    unsigned value;
    __asm__ volatile("csrr %0,vcsr" : "=r"(value) : : "memory");
    return value;
}

static void set_csrs(unsigned fcsr, unsigned vcsr) {
    __asm__ volatile("fscsr %0\n\tcsrw vcsr,%1" : : "r"(fcsr), "r"(vcsr) : "memory");
}

static uint64_t digest(const void * data, size_t size) {
    const unsigned char * bytes = data;
    uint64_t value = UINT64_C(14695981039346656037);
    for (size_t j = 0; j < size; ++j) value = (value ^ bytes[j]) * UINT64_C(1099511628211);
    return value;
}

static int check(unsigned nonzero, unsigned initial_vcsr) {
    _Static_assert(sizeof(block_q8_K) == 292 && QK_K == 256, "Q8_K layout changed");
    float input[QK_K + 32], saved[QK_K + 32];
    block_q8_K output[3], expected;
    unsigned char guard[sizeof(block_q8_K)];
    memset(input, 0xa5, sizeof(input));
    memset(output, 0xa5, sizeof(output));
    memset(guard, 0xa5, sizeof(guard));
    memset(&expected, 0, sizeof(expected));
    expected.d = nonzero ? 1.0f : 0.0f;
    // Signed maximum is -127, giving iscale=1: every conversion is exact.
    for (int j = 0; j < QK_K; ++j) {
        int q = nonzero ? j % 255 - 127 : 0;
        input[16 + j] = (float) q;
        expected.qs[j] = (int8_t) q;
        expected.bsums[j / 16] += q;
    }
    memcpy(saved, input, sizeof(input));
    set_csrs(9, initial_vcsr);
    const unsigned before_fcsr = read_fcsr(), before_vcsr = read_vcsr();
    quantize_row_q8_K(input + 16, output + 1, QK_K);
    const unsigned after_fcsr = read_fcsr(), after_vcsr = read_vcsr();
    set_csrs(0, 0);
    const int bytes = !memcmp(output + 1, &expected, sizeof(expected));
    const int intact = !memcmp(input, saved, sizeof(input));
    const int canaries = !memcmp(output, guard, sizeof(guard)) &&
                         !memcmp(output + 2, guard, sizeof(guard));
    printf("VCSR_DIAG_CASE kind=%s before_vcsr=%u after_vcsr=%u before_fcsr=%u after_fcsr=%u "
           "bytes=%d input=%d canaries=%d digest=%016llx\n",
           nonzero ? "nonzero" : "zero", before_vcsr, after_vcsr, before_fcsr, after_fcsr,
           bytes, intact, canaries, (unsigned long long) digest(output + 1, sizeof(expected)));
    return !(before_fcsr == 9 && after_fcsr == 9 && before_vcsr == initial_vcsr &&
             after_vcsr == (nonzero ? 2 | (initial_vcsr & 1) : initial_vcsr) &&
             bytes && intact && canaries);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    const unsigned saved_fcsr = read_fcsr(), saved_vcsr = read_vcsr();
    int failed = 0;
    for (unsigned initial = 5; initial >= 4; --initial) {
        failed |= check(0, initial);
        failed |= check(1, initial);
    }
    set_csrs(saved_fcsr, saved_vcsr);
    printf("VCSR_DIAG_%s cases=4\n", failed ? "FAIL" : "PASS");
    return failed;
}
