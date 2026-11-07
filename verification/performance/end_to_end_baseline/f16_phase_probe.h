#ifndef F16_PHASE_PROBE_H
#define F16_PHASE_PROBE_H
#include <stddef.h>
#include <stdint.h>

enum f16_phase_id {
  F16_PHASE_PREFLIGHT, F16_PHASE_INIT, F16_PHASE_QUERY,
  F16_PHASE_KV_FULL, F16_PHASE_KV_REFILL, F16_PHASE_QK,
  F16_PHASE_SOFTMAX, F16_PHASE_PV, F16_PHASE_RELEASE,
  F16_PHASE_NORMALIZE, F16_PHASE_SCHEDULE,
  F16_PHASE_BARRIER, F16_PHASE_COMPLETED, F16_PHASE_REJECTED,
  F16_PHASE_ERRORS, F16_PHASE_COUNT
};
enum { F16_PHASE_EXCLUSIVE_COUNT = F16_PHASE_BARRIER };

static const char *const f16_phase_names[F16_PHASE_COUNT] __attribute__((unused)) = {
  "preflight", "init", "query", "kv_full", "kv_refill", "qk",
  "softmax", "pv", "release", "normalize", "schedule",
  "barrier_subset", "completed", "rejected", "errors"
};

/* Caller owns both arrays and reset. Single private thread/context only;
 * reset/snapshot/printing must be OUTSIDE an observed call. */
extern uint64_t f16_phase_cycles[F16_PHASE_COUNT];
extern uint64_t f16_phase_calls[F16_PHASE_COUNT];
extern void f16_phase_reset(void);

#ifdef F16_PHASE_HOST_TEST
#ifdef __riscv
#error "Host clock model must never be enabled in a target image"
#endif
uint64_t f16_phase_test_raw(void);
uint64_t f16_phase_test_drained(void);
static inline uint64_t f16_phase_raw(void) { return f16_phase_test_raw(); }
static inline uint64_t f16_phase_stamp(void) { return f16_phase_test_drained(); }
#else
#if !defined(__riscv) || __riscv_xlen != 64 || !defined(__riscv_vector)
#error "F16 observation clock requires the reviewed RV64 vector target"
#endif
static inline uint64_t f16_phase_raw(void) {
  uint64_t tick;
  __asm__ volatile("rdcycle %0" : "=r"(tick) :: "memory");
  return tick;
}
static inline uint64_t f16_phase_stamp(void) {
  uint64_t tick;
  uintptr_t vc, fc, start;
  /* Accepted target completed-state CSR sequence, plus memory fence. Reads
   * only: no VL/VTYPE/vector/FP modifications. Requires the target's reviewed
   * CSR/vector-completion ordering; fence alone is NOT an AKV DMA completion. */
  __asm__ volatile("csrr %1,vcsr; frcsr %2; csrr %3,vstart; fence rw,rw; rdcycle %0"
      : "=&r"(tick), "=&r"(vc), "=&r"(fc), "=&r"(start) :: "memory");
  return tick;
}
#endif

typedef struct { uint64_t start, last; unsigned phase, active; } f16_phase_scope_t;

/* Phase slots [0,EXCLUSIVE_COUNT) partition the inner observed interval and
 * include probe bookkeeping/terminal drains. BARRIER is an OVERLAPPING SUBSET:
 * raw pre-drain rdcycle -> drained sample, including pending useful work.
 * Never add BARRIER again or subtract it as if it were pure fixed overhead.
 * COMPLETED/REJECTED/ERRORS have counts only. Outer caller boundaries remain
 * mandatory for original/control/observed perturbation comparison. */
static inline void f16_phase_add(unsigned id, uint64_t cycles, uint64_t calls) {
  volatile uint64_t *c = f16_phase_cycles, *n = f16_phase_calls;
  c[id] += cycles; n[id] += calls;
}

static inline f16_phase_scope_t f16_phase_begin(unsigned target) {
  f16_phase_scope_t scope = {0, 0, F16_PHASE_PREFLIGHT, 0};
  if (!target) return scope;
  scope.active = 1;
  scope.start = f16_phase_raw();
  scope.last = f16_phase_stamp();
  f16_phase_add(F16_PHASE_PREFLIGHT, scope.last-scope.start, 1);
  f16_phase_add(F16_PHASE_BARRIER, scope.last-scope.start, 1);
  return scope;
}

static inline uint64_t f16_phase_close(f16_phase_scope_t *scope) {
  const uint64_t before = f16_phase_raw();
  const uint64_t after = f16_phase_stamp();
  f16_phase_add(scope->phase, after-scope->last, 0);
  f16_phase_add(F16_PHASE_BARRIER, after-before, 1);
  scope->last = after;
  return after;
}

static inline void f16_phase_switch(f16_phase_scope_t *scope, unsigned phase) {
  if (!scope->active) return;
  if (phase >= F16_PHASE_EXCLUSIVE_COUNT) { f16_phase_add(F16_PHASE_ERRORS, 0, 1); return; }
  (void)f16_phase_close(scope);
  scope->phase = phase;
  f16_phase_add(phase, 0, 1);
}

static inline void f16_phase_end(f16_phase_scope_t *scope, int status) {
  if (!scope->active) return;
  (void)f16_phase_close(scope);
  f16_phase_add(F16_PHASE_COMPLETED, 0, 1);
  if (status != 0) f16_phase_add(F16_PHASE_REJECTED, 0, 1);
  scope->active = 0;
}

/* Explicit volatile scalar reads/writes avoid compiler-vectorized memcpy
 * consuming a deliberately injected VSTART in a caller's control checks. */
static inline int f16_phase_snapshot(uint64_t *cycles, uint64_t *calls) {
  if (!cycles || !calls) return -1;
  volatile uint64_t *dc = cycles, *dn = calls;
  const volatile uint64_t *sc = f16_phase_cycles, *sn = f16_phase_calls;
  for (unsigned i=0; i<F16_PHASE_COUNT; ++i) { dc[i] = sc[i]; dn[i] = sn[i]; }
  return 0;
}

#define F16_PHASE_SCOPE(name, target) f16_phase_scope_t name = f16_phase_begin(target)
#define F16_PHASE_SWITCH(scope, phase) f16_phase_switch(&(scope), phase)
#define F16_PHASE_RETURN(scope, expression) do { \
  const akv_status_t f16_phase_status_ = (expression); \
  f16_phase_end(&(scope), (int)f16_phase_status_); \
  return f16_phase_status_; \
} while (0)

/* Optional SDK-typed declarations; original SDK headers remain unchanged. */
#ifdef F16_PHASE_DECLARE_NATIVE
#include "akv/akv.h"
#include "akv/akv_features.h"
akv_status_t f16_phase_execute_v2_native(const akv_attention_plan_t *, akv_attention_v2_workspace_t *);
akv_status_t f16_phase_execute_v2_with_features_native(const akv_attention_plan_t *, akv_attention_v2_workspace_t *, const akv_attention_features_t *);
akv_status_t f16_phase_execute_v2_prefill_native(const akv_device_t *, const akv_attention_v2_prefill_problem_t *, akv_attention_v2_prefill_workspace_t *);
akv_status_t f16_phase_control_execute_v2_native(const akv_attention_plan_t *, akv_attention_v2_workspace_t *);
akv_status_t f16_phase_control_execute_v2_with_features_native(const akv_attention_plan_t *, akv_attention_v2_workspace_t *, const akv_attention_features_t *);
akv_status_t f16_phase_control_execute_v2_prefill_native(const akv_device_t *, const akv_attention_v2_prefill_problem_t *, akv_attention_v2_prefill_workspace_t *);
#endif
#endif
