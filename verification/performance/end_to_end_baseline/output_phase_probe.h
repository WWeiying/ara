#ifndef OUTPUT_PHASE_PROBE_H
#define OUTPUT_PHASE_PROBE_H

#include <stdint.h>

enum output_phase_id {
  OUTPUT_PHASE_INIT, OUTPUT_PHASE_QUANTIZE, OUTPUT_PHASE_QK,
  OUTPUT_PHASE_COEFFICIENTS, OUTPUT_PHASE_PV, OUTPUT_PHASE_FINISH,
  OUTPUT_PHASE_BINDING, OUTPUT_PHASE_COUNT
};

typedef struct {
  uint64_t cycles[OUTPUT_PHASE_COUNT];
  unsigned calls[OUTPUT_PHASE_COUNT];
} output_phase_stats_t;

extern output_phase_stats_t output_phase_stats;

/* Complete pending FP/vector state and memory before sampling. Both variants
 * use this same whole-call boundary. Internal samples intentionally serialize;
 * their complete-call perturbation must be measured, never assumed negligible. */
static inline uint64_t output_phase_stamp(void) {
  uint64_t tick;
  uintptr_t vc, fc, start;
  __asm__ volatile("csrr %1,vcsr; frcsr %2; csrr %3,vstart; fence rw,rw; rdcycle %0"
      : "=r"(tick), "=r"(vc), "=r"(fc), "=r"(start) :: "memory");
  return tick;
}

static inline void output_phase_end(enum output_phase_id id, uint64_t begin) {
  const uint64_t end = output_phase_stamp();
  output_phase_stats.cycles[id] += end - begin;
  ++output_phase_stats.calls[id];
}

#endif
