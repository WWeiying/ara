#ifndef STAGE5_MODEL_OBSERVE_V1_H
#define STAGE5_MODEL_OBSERVE_V1_H
#include "entry.h"

#ifndef STAGE5_BINDING_ID
#error "An independently reviewed binding identity is required"
#endif

static void binding_snapshot(unsigned mode, unsigned step, const char *when) {
    ggml_akv_resident_counters_v1 c{};
    ggml_akv_resident_snapshot_v1(&c);
    std::printf("BIND_COUNTER case=%s requested=%u step=%u when=%s"
        " denied=%llu unsupported=%llu lease_denied=%llu resident_calls=%llu native_calls=%llu"
        " resident_groups=%llu native_groups=%llu completed=%llu failed=%llu"
        " legacy_calls=%llu legacy_completed=%llu legacy_fallback=%llu\n",
        case_id, mode, step, when,
        (unsigned long long)c.denied, (unsigned long long)c.unsupported,
        (unsigned long long)c.lease_denied, (unsigned long long)c.resident_calls,
        (unsigned long long)c.native_calls, (unsigned long long)c.resident_groups,
        (unsigned long long)c.native_groups, (unsigned long long)c.completed,
        (unsigned long long)c.failed, (unsigned long long)c.legacy_calls,
        (unsigned long long)c.legacy_completed, (unsigned long long)c.legacy_fallback);
}

static void binding_logits(unsigned mode, unsigned step, const float *logits, uint32_t count) {
    // Export bits after the post-decode CSR snapshot, never through FP formatting.
    for (uint32_t first = 0; first < count; first += 32) {
        const uint32_t n = std::min(uint32_t(32), count - first);
        char words[32 * 9 + 1];
        for (uint32_t j = 0; j < n; ++j) {
            uint32_t bits;
            std::memcpy(&bits, logits + first + j, sizeof(bits));
            std::snprintf(words + j * 9, 10, "%08x%c", bits, j + 1 == n ? '\0' : ',');
        }
        std::printf("BIND_LOGITS case=%s requested=%u step=%u offset=%u count=%u bits=%s\n",
                    case_id, mode, step, first, n, words);
    }
}
#endif
