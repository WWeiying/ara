#include "printf.h"
#include <cstdlib>

// Bare-metal replacement for GGML's process-abort service, not arithmetic.
extern "C" [[noreturn]] void ggml_abort(const char *file, int line, const char *format, ...) {
    (void)file;
    (void)format;
    printf("RVV_DECODE_FAIL reason=ggml_abort line=%d\n", line);
    std::exit(1);
}
