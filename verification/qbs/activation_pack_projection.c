#include "activation_pack_rvv_candidate.h"

/* Link-time substitution for a private performance ELF, never production. */
qbs_status_t __wrap_qbs_pack_activation_m4(
    unsigned profile, const void *source, size_t source_bytes, size_t k,
    void *destination, size_t destination_bytes) {
  switch (qbs_pack_activation_candidate(profile, 4, 4, k, source, source_bytes,
                                       0, destination, destination_bytes)) {
    case QBS_PACK_CANDIDATE_OK: return QBS_STATUS_OK;
    case QBS_PACK_CANDIDATE_PROFILE: return QBS_STATUS_PROFILE;
    case QBS_PACK_CANDIDATE_OVERFLOW: return QBS_STATUS_SIZE_OVERFLOW;
    case QBS_PACK_CANDIDATE_BUFFER: return QBS_STATUS_BUFFER_TOO_SMALL;
    default: return QBS_STATUS_BAD_ARGUMENT;
  }
}
