/* Expose the canonical private lifecycle operations without copying encodings. */
#include "software/akv/src/akv_v2_native_riscv.c"

void rtl_akv_full(const akv_descriptor_t *descriptor) {
  issue_full(descriptor, 0);
}

void rtl_akv_release(void) {
  issue_release();
}
