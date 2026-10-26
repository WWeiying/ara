// Preserve the existing context/alias/barrier scenarios and their policy matrix.
#define main context_suite_main
#include "../../ggml_segmented_init.c"
#undef main

int main(void) {
    if (setenv("GGML_RISCV_QBS_M4_PREPARE", "1", 1) ||
        setenv("GGML_RISCV_QBS_TRACE_M4_PREPARE", "1", 1)) {
        perror("M4 preparation environment");
        return 1;
    }
    return context_suite_main();
}
