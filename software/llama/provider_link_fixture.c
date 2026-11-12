/* Link test only: deny all deployment authority. */
#include "entry.h"

const akv_resident_platform_provider_v1 * akv_resident_platform_current_v1(void) {
    return NULL;
}

const ggml_akv_legacy_contract_v1 * ggml_akv_legacy_current_v1(void) {
    return NULL;
}
