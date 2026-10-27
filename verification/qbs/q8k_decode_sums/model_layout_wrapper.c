#include <stdio.h>
#include <stdlib.h>
#include "quantizers.h"

static unsigned long original_calls, candidate_calls;
extern void __real_quantize_row_q8_K(const float *, void *, int64_t);

void __wrap_quantize_row_q8_K(const float *x, void *y, int64_t k) {
    const char *mode = getenv("GGML_QBS_DECODE_LAYOUT_TEST");
    if (mode != NULL && strcmp(mode, "1") == 0) {
        ++candidate_calls;
        decode_candidate(x, y, k);
    } else {
        ++original_calls;
        __real_quantize_row_q8_K(x, y, k);
    }
}

__attribute__((destructor)) static void report_layout_calls(void) {
    if (original_calls || candidate_calls) {
        fprintf(stderr, "DECODE_LAYOUT_DISPATCH original=%lu candidate=%lu\n",
                original_calls, candidate_calls);
    }
}
