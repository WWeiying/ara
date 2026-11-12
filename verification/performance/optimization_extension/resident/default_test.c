#include "resident_deployment.h"
#include <assert.h>
#include <stdio.h>

akv_platform_result_t akv_resident_platform_read_state_v1(void *c, akv_platform_thread_state_v1 *s) {
    (void)c; (void)s;
    __builtin_trap();
}

int main(void) {
    assert(ara_resident_deployment_current_v1() == NULL);
    assert(akv_resident_platform_current_v1() == NULL);
    assert(ggml_akv_legacy_current_v1() == NULL);
    assert(ggml_akv_platform_entry_v1(NULL) == AKV_PLATFORM_KEEP_NATIVE);
    assert(akv_resident_platform_admit_v1(NULL, (void *)1, (void *)1) == AKV_PLATFORM_KEEP_NATIVE);
    puts("RESIDENT_DEFAULT_DENY_PASS csr_reads=0 native_execution=0");
    return 0;
}
