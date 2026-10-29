#define GGML_COMMON_IMPL_CPP
#define GGML_COMMON_DECL_CPP
#include "ggml-common.h"
#include "ggml-cpu-impl.h"
#include "arch/riscv/q8_K-prepared-reuse.h"
#include "schedule_census.h"

/* Same inline worker_state/COMDAT as repack.cpp; no cache reset or mutation. */
extern "C" void graph_cache_snapshot(uint64_t out[14]) {
    const auto &state = ggml_riscv_q8_K_prepared::worker_state();
    const auto &s = state.bytes.statistics();
    out[0] = s.queries; out[1] = s.hits; out[2] = s.misses;
    out[3] = s.stores; out[4] = s.evictions; out[5] = s.rejected;
    out[6] = s.allocation_failures; out[7] = s.conflicts;
    out[8] = s.comparison_bytes_requested; out[9] = s.copied_payload_bytes;
    out[10] = state.computations; out[11] = state.generic_computations;
    out[12] = state.bytes.retained_bytes(); out[13] = state.bytes.size();
}
