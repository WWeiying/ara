/* Host control-flow differential test, not a numerical or hardware emulator. */
#include "qbs/qbs.h"
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char label[256];
#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "FIRST_FAILURE %s line=%d: %s\n", label, __LINE__, #x); \
  exit(1); } } while (0)

#ifdef SDK_GUARD_UNIT
#include "qbs_runtime.c"
static unsigned fast_visits, next_visits;
void __attribute__((no_instrument_function))
__cyg_profile_func_enter(void *fn, void *caller) {
  (void)caller;
  if (fn == (void *)qbs_execute_single_input) ++fast_visits;
  if (fn == (void *)qbs_plan_next) ++next_visits;
}
void __attribute__((no_instrument_function))
__cyg_profile_func_exit(void *fn, void *caller) { (void)fn; (void)caller; }

static qbs_status_t noop(void *c, const qbs_descriptor_t *d, unsigned m,
    const void *a, float *o, size_t s, unsigned n, int seg) {
  (void)c; (void)d; (void)m; (void)a; (void)o; (void)s; (void)n; (void)seg;
  return QBS_STATUS_OK;
}

int main(void) {
  qbs_device_t d;
  CHECK(qbs_device_init_reference(1024, &d) == QBS_STATUS_OK);
  qbs_problem_t p = {QBS_WEIGHT_PROFILE_Q4_0, QBS_ACTIVATION_PROFILE_Q8_0,
      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      1, 65, 96};
  qbs_plan_t good, t;
  CHECK(qbs_plan_create(&d, &p, &good) == QBS_STATUS_OK);
  CHECK(qbs_single_input_eligible(&good));
  unsigned guards = 0;
#define REJECT(name, mutation) do { t = good; mutation; \
  snprintf(label, sizeof(label), "guard/%s", name); \
  CHECK(!qbs_single_input_eligible(&t)); ++guards; \
  printf("GUARD_REJECT %s\n", name); } while (0)
  REJECT("m", t.problem.m = 2);
  REJECT("split", t.split_k = 1);
  REJECT("gather", t.needs_activation_gather = 1);
  REJECT("command_m_zero", t.command_m = 0);
  REJECT("k_zero", t.k_blocks = 0);
  REJECT("k_over_max", t.k_blocks = QBS_MAX_K_BLOCKS + 1);
  REJECT("command_k_short", t.command_k_blocks = t.k_blocks - 1);
  REJECT("command_n_zero", t.command_n = 0);
  REJECT("command_n_over_max", t.command_n = QBS_MAX_N + 1);
  REJECT("segment", t.weight_segment_k_blocks = 1);
  REJECT("storage_rows", t.weight_storage_rows = 68);
  REJECT("row_start", t.weight_row_start = 4);
  REJECT("layout_invalid", t.problem.weight_layout = 0);
  REJECT("r4_unaligned_n", t.command_n = 6);
  REJECT("storage_invalid", t.problem.activation_storage = 0);
  REJECT("storage_m8", t.problem.activation_storage = QBS_ACTIVATION_STORAGE_M8_GROUPED);
  t = good; t.problem.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
  t.command_n = 7; CHECK(qbs_single_input_eligible(&t));
  t = good; t.problem.activation_storage = QBS_ACTIVATION_STORAGE_M4_GROUPED;
  CHECK(qbs_single_input_eligible(&t));
  /* Only constructor-produced plans are executed. Invalid guard states above
     are observations, never claimed to be legal public execution inputs. */
  unsigned char weights[524288] = {0}, acts[65536] = {0}, work[65536] = {0};
  float output[8192] = {0};
  unsigned paths = 0;
  for (unsigned kind = 0; kind < 7; ++kind) {
    snprintf(label, sizeof(label), "observed_path/%u", kind);
    p.m = kind == 1 ? 4 : kind == 2 ? 8 : 1;
    p.activation_storage = kind == 1 ? QBS_ACTIVATION_STORAGE_M4_GROUPED :
        kind == 2 ? QBS_ACTIVATION_STORAGE_M8_GROUPED : QBS_ACTIVATION_STORAGE_ROW_MAJOR;
    p.k_elements = kind == 4 ? 257 * 32 : kind == 3 ? 17 * 32 : 96;
    d.capabilities.max_k_blocks = kind == 3 ? 3 : QBS_MAX_K_BLOCKS;
    if (kind == 5)
      CHECK(qbs_plan_create_segmented_r4(&d, &p, 2, &t) == QBS_STATUS_OK);
    else if (kind == 6)
      CHECK(qbs_plan_create_segmented_r4_view(&d, &p, 3, 72, 4, &t) == QBS_STATUS_OK);
    else CHECK(qbs_plan_create(&d, &p, &t) == QBS_STATUS_OK);
    if (kind == 3) CHECK(t.needs_activation_gather);
    fast_visits = next_visits = 0;
    CHECK(qbs_execute_with_options(&t, weights, sizeof(weights), acts, sizeof(acts),
        output, 8192, 68, work, sizeof(work), NULL, noop, NULL) == QBS_STATUS_OK);
    CHECK(fast_visits == (kind == 0 ? 1u : 0u));
    CHECK(kind == 0 ? next_visits == 0 : next_visits > 0);
    printf("PATH kind=%u fast=%u generic_next=%u\n", kind, fast_visits, next_visits);
    ++paths;
  }
  printf("{\"guard_rejections\":%u,\"guard_acceptances\":3,\"observed_paths\":%u}\n", guards, paths);
  return 0;
}
#else
extern qbs_status_t baseline_qbs_execute_with_options(
    const qbs_plan_t *, const void *, size_t, const void *, size_t, float *,
    size_t, size_t, void *, size_t, const qbs_execution_options_t *,
    qbs_command_executor_t, void *);
extern qbs_status_t baseline_qbs_device_init_reference(unsigned, qbs_device_t *);
extern qbs_status_t baseline_qbs_plan_create(const qbs_device_t *, const qbs_problem_t *, qbs_plan_t *);
extern qbs_status_t baseline_qbs_plan_create_segmented_r4(const qbs_device_t *, const qbs_problem_t *, unsigned, qbs_plan_t *);
extern qbs_status_t baseline_qbs_plan_create_segmented_r4_view(const qbs_device_t *, const qbs_problem_t *, unsigned, uint32_t, uint32_t, qbs_plan_t *);

typedef struct { unsigned char *allocation, *data; size_t size; } buffer_t;
static buffer_t buffer(size_t n, unsigned seed) {
  buffer_t b = {malloc(n + 128), NULL, n};
  CHECK(b.allocation); b.data = b.allocation + 64;
  memset(b.allocation, 0xa5, n + 128);
  for (size_t i = 0; i < n; ++i) b.data[i] = (unsigned char)(seed + i * 13 + i / 251);
  return b;
}
static void guards(buffer_t b) {
  for (unsigned i = 0; i < 64; ++i) {
    CHECK(b.allocation[i] == 0xa5); CHECK(b.data[b.size + i] == 0xa5);
  }
}
static uint64_t hash(const void *data, size_t n) {
  const unsigned char *p = data;
  uint64_t h = UINT64_C(1469598103934665603);
  for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * UINT64_C(1099511628211);
  return h;
}
typedef struct {
  uint64_t header, activation_hash, state_after;
  size_t weight_offset, activation_offset, output_offset, stride;
  unsigned m, n, activation_region, output_region, calls, resident, token;
  int segmented;
} record_t;
typedef struct {
  buffer_t w, a, o, work;
  record_t *trace;
  unsigned capacity, calls, resident, token, replay;
  int fail_at;
  uint64_t state;
} mock_t;
static void locate(const void *ptr, buffer_t primary, buffer_t work,
                   size_t bytes, unsigned *region, size_t *offset) {
  uintptr_t x = (uintptr_t)ptr, base = (uintptr_t)primary.data;
  if (x >= base && x - base <= primary.size && bytes <= primary.size - (x - base)) {
    *region = 0; *offset = x - base; return;
  }
  base = (uintptr_t)work.data;
  CHECK(x >= base && x - base <= work.size && bytes <= work.size - (x - base));
  *region = 1; *offset = x - base;
}
static qbs_status_t execute(void *opaque, const qbs_descriptor_t *d, unsigned m,
    const void *a, float *o, size_t stride, unsigned n, int segmented) {
  mock_t *s = opaque;
  CHECK(s->calls < s->capacity);
  qbs_descriptor_fields_t f = qbs_unpack_descriptor_header(d->header);
  record_t r = {0};
  r.header = d->header; r.m = m; r.n = n; r.stride = stride; r.segmented = segmented;
  CHECK(m && n && f.n == n && f.k_blocks);
  CHECK(d->weight_base >= (uintptr_t)s->w.data);
  r.weight_offset = d->weight_base - (uintptr_t)s->w.data;
  const size_t weight_bytes = (size_t)(f.weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
      ? (n + 3u) & ~3u : n) * f.k_blocks * qbs_weight_block_bytes(f.weight_profile);
  CHECK(r.weight_offset <= s->w.size && weight_bytes <= s->w.size - r.weight_offset);
  const size_t ab = (size_t)(f.activation_layout == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED ? 8 : m)
      * f.k_blocks * qbs_activation_block_bytes(f.activation_profile);
  locate(a, s->a, s->work, ab, &r.activation_region, &r.activation_offset);
  locate(o, s->o, s->work, ((m - 1u) * stride + n) * sizeof(float), &r.output_region, &r.output_offset);
  r.activation_hash = hash(a, ab);
  r.token = (unsigned)f.context_id * 256u + f.context_generation;
  if (f.activation_access == QBS_ACTIVATION_ACCESS_FILL) { s->resident = 1; s->token = r.token; }
  else if (f.activation_access != QBS_ACTIVATION_ACCESS_DIRECT) {
    CHECK(s->resident && s->token == r.token);
    if (f.activation_access == QBS_ACTIVATION_ACCESS_RELEASE) s->resident = 0;
  }
  /* Mutate both output and mock state BEFORE returning an injected failure. */
  s->state = s->state * 33u + d->header + r.activation_hash + r.weight_offset;
  for (unsigned row = 0; row < m; ++row)
    for (unsigned col = 0; col < n; ++col)
      o[row * stride + col] = (float)((s->state % 2048) + s->calls * 3 + row * 7 + col);
  r.calls = s->calls + 1; r.resident = s->resident; r.token = s->token; r.state_after = s->state;
  if (s->replay) CHECK(memcmp(&r, &s->trace[s->calls], sizeof(r)) == 0);
  else s->trace[s->calls] = r;
  const int failed = (int)s->calls == s->fail_at;
  ++s->calls;
  return failed ? QBS_STATUS_EXECUTION : QBS_STATUS_OK;
}
static unsigned cases, failures, unsupported, commands, eligible_cases, fallback_cases;
static unsigned profiles_seen[16], vlens_seen[4], scopes_seen[6];
static void same_plan(const qbs_plan_t *a, const qbs_plan_t *b) {
#define EQ(field) CHECK(a->field == b->field)
  EQ(problem.weight_profile); EQ(problem.activation_profile); EQ(problem.weight_layout);
  EQ(problem.activation_storage); EQ(problem.m); EQ(problem.n); EQ(problem.k_elements);
  EQ(k_blocks); EQ(command_k_blocks); EQ(command_m); EQ(command_n); EQ(wide_command_n);
  EQ(uses_wide_m); EQ(split_k); EQ(needs_activation_gather); EQ(activation_context_eligible);
  EQ(activation_context_count); EQ(activation_context_generation_bits); EQ(workspace_bytes);
  EQ(weight_segment_k_blocks); EQ(weight_storage_rows); EQ(weight_row_start);
#undef EQ
}

/* mode: 0 NULL/DIRECT, 1..4 context scopes, 5 bad id, 6 bad scope,
   7 DIRECT with invalid scope, 8 reduced generation width with invalid token,
   9 explicit DIRECT options, 10 maximum valid generation.
   Plans otherwise always come from constructors. */
static unsigned run(unsigned vlen, unsigned profile, unsigned m, unsigned n,
    unsigned k, unsigned layout, unsigned storage, unsigned segment,
    bool view, unsigned mode, int fail_at, unsigned cap_k, unsigned cap_n) {
  snprintf(label, sizeof(label), "v%u/p%u/m%u/n%u/k%u/l%u/s%u/seg%u/view%u/mode%u/fail%d/capk%u/capn%u",
      vlen, profile, m, n, k, layout, storage, segment, view, mode, fail_at, cap_k, cap_n);
  qbs_device_t d = {0}, old_d = {0};
  CHECK(qbs_device_init_reference(vlen, &d) == QBS_STATUS_OK);
  CHECK(baseline_qbs_device_init_reference(vlen, &old_d) == QBS_STATUS_OK);
  CHECK(memcmp(&d, &old_d, sizeof(d)) == 0);
  if (cap_k) d.capabilities.max_k_blocks = cap_k;
  if (cap_n) d.capabilities.max_n = cap_n;
  if (mode == 8) d.capabilities.activation_context_generation_bits = 4;
  qbs_problem_t problem = {profile, qbs_default_activation_profile(profile), layout,
      storage, m, n, k * qbs_weight_block_elements(profile)};
  qbs_plan_t p, new_p;
  qbs_status_t bs, ns;
  if (view) {
    bs = baseline_qbs_plan_create_segmented_r4_view(&d, &problem, segment, n + 8, 4, &p);
    ns = qbs_plan_create_segmented_r4_view(&d, &problem, segment, n + 8, 4, &new_p);
  } else if (segment) {
    bs = baseline_qbs_plan_create_segmented_r4(&d, &problem, segment, &p);
    ns = qbs_plan_create_segmented_r4(&d, &problem, segment, &new_p);
  } else {
    bs = baseline_qbs_plan_create(&d, &problem, &p);
    ns = qbs_plan_create(&d, &problem, &new_p);
  }
  CHECK(bs == QBS_STATUS_OK && ns == bs); same_plan(&p, &new_p);
  const size_t stride = n + 7;
  buffer_t w = buffer(qbs_weight_storage_bytes(profile, layout, view ? n + 8 : n, k), 17);
  buffer_t a = buffer(qbs_activation_storage_bytes(problem.activation_profile, storage, m, k), 29);
  buffer_t o = buffer((size_t)m * stride * sizeof(float), 41);
  buffer_t work = buffer(p.workspace_bytes, 53);
  const uint64_t wh = hash(w.data, w.size), ah = hash(a.data, a.size);
  unsigned char *saved_o = malloc(o.size), *initial_o = malloc(o.size);
  unsigned char *saved_work = malloc(work.size + 1), *initial_work = malloc(work.size + 1);
  CHECK(saved_o && initial_o && saved_work && initial_work);
  memcpy(initial_o, o.data, o.size); memcpy(initial_work, work.data, work.size);
  unsigned count = 0;
  qbs_plan_cursor_t cursor; qbs_plan_cursor_reset(&cursor);
  for (;;) {
    qbs_command_t c; int has;
    CHECK(qbs_plan_next(&p, &cursor, &c, &has) == QBS_STATUS_OK);
    if (!has) break;
    ++count; CHECK(count < 1000000);
  }
  record_t *trace = calloc(count + 1, sizeof(*trace)); CHECK(trace);
  qbs_execution_options_t options = {1, {0, 7}, mode >= 1 && mode <= 4 ? mode - 1 : 0};
  if (mode == 5) options.activation_context.context_id = p.activation_context_count;
  if (mode == 6) options.activation_context_scope = 255;
  if (mode == 7) { options.use_activation_context = 0; options.activation_context_scope = 1; }
  if (mode == 8) options.activation_context.generation = 16;
  if (mode == 9) { options.use_activation_context = 0; options.activation_context.generation = 255; }
  if (mode == 10) options.activation_context.generation = 255;
  qbs_status_t expected = QBS_STATUS_OK;
  if (mode == 6 || mode == 7) expected = QBS_STATUS_BAD_ARGUMENT;
  else if (mode && options.use_activation_context && (!p.activation_context_eligible ||
      (mode >= 2 && mode <= 4 && m > p.command_m))) expected = QBS_STATUS_CONTEXT_UNSUPPORTED;
  else if (mode == 5 || mode == 8) expected = QBS_STATUS_CONTEXT_TOKEN;
  else if (fail_at >= 0) expected = QBS_STATUS_EXECUTION;
  mock_t old = {w, a, o, work, trace, count, 0, mode == 3 || mode == 4,
      7, 0, fail_at, 123};
  mock_t fresh = old; fresh.replay = 1;
  bs = baseline_qbs_execute_with_options(&p, w.data, w.size, a.data, a.size,
      (float *)o.data, o.size / sizeof(float), stride, work.data, work.size,
      mode ? &options : NULL, execute, &old);
  CHECK(bs == expected); guards(w); guards(a); guards(o); guards(work);
  memcpy(saved_o, o.data, o.size); memcpy(saved_work, work.data, work.size);
  memcpy(o.data, initial_o, o.size); memcpy(work.data, initial_work, work.size);
  ns = qbs_execute_with_options(&p, w.data, w.size, a.data, a.size,
      (float *)o.data, o.size / sizeof(float), stride, work.data, work.size,
      mode ? &options : NULL, execute, &fresh);
  CHECK(ns == bs && fresh.calls == old.calls && fresh.state == old.state);
  CHECK(fresh.resident == old.resident && fresh.token == old.token);
  CHECK(memcmp(saved_o, o.data, o.size) == 0 && memcmp(saved_work, work.data, work.size) == 0);
  CHECK(hash(w.data, w.size) == wh && hash(a.data, a.size) == ah);
  guards(w); guards(a); guards(o); guards(work);
  for (unsigned row = 0; row < m; ++row)
    CHECK(memcmp(o.data + (row * stride + n) * sizeof(float),
        initial_o + (row * stride + n) * sizeof(float), 7 * sizeof(float)) == 0);
  if (bs == QBS_STATUS_EXECUTION) { CHECK(old.calls == (unsigned)fail_at + 1); ++failures; }
  else if (bs != QBS_STATUS_OK) { CHECK(old.calls == 0); ++unsupported; }
  else CHECK(old.calls == count);
  ++cases; commands += old.calls + fresh.calls; ++profiles_seen[profile];
  ++vlens_seen[vlen == 256 ? 0 : vlen == 512 ? 1 : 2];
  ++scopes_seen[mode <= 4 ? mode : 5];
  if (m == 1 && !p.split_k && !p.needs_activation_gather && !segment && !view) ++eligible_cases;
  else ++fallback_cases;
  printf("CASE %u %s status=%u executor_calls=%u\n", cases, label, bs, old.calls + fresh.calls);
  free(w.allocation); free(a.allocation); free(o.allocation); free(work.allocation);
  free(trace); free(saved_o); free(initial_o); free(saved_work); free(initial_work);
  return count;
}

int main(void) {
  const unsigned vlens[] = {256, 512, 1024, 2048};
  const unsigned ks[] = {1, 3, 8, 16, 17, 24, 256};
  for (unsigned vi = 0; vi < 4; ++vi) {
    qbs_device_t a, b;
    qbs_status_t x = baseline_qbs_device_init_reference(vlens[vi], &a);
    CHECK(qbs_device_init_reference(vlens[vi], &b) == x);
    CHECK(x == (vi == 3 ? QBS_STATUS_BAD_ARGUMENT : QBS_STATUS_OK));
    if (vi == 3) { vlens_seen[3] = 1; puts("VLEN 2048 REJECTED bad_argument (both SDKs)"); continue; }
    for (unsigned profile = 1; profile <= 9; ++profile) {
      for (unsigned layout = 1; layout <= 2; ++layout) {
        for (unsigned storage = 1; storage <= 2; ++storage) {
          for (unsigned n = 1; n <= 66; ++n)
            run(vlens[vi], profile, 1, n == 66 ? 128 : n, ks[(n - 1) % 7], layout, storage, 0, false, 0, -1, 0, 0);
          for (unsigned ki = 0; ki < 7; ++ki)
            for (unsigned mode = 0; mode <= 10; ++mode)
              run(vlens[vi], profile, 1, 65, ks[ki], layout, storage, 0, false, mode, -1, 0, 0);
        }
        for (unsigned mode = 0; mode <= 4; ++mode) {
          const unsigned count = run(vlens[vi], profile, 1, 65, 3, layout, 1, 0, false, mode, -1, 0, 0);
          for (unsigned f = 0; f < count; ++f)
            run(vlens[vi], profile, 1, 65, 3, layout, 1, 0, false, mode, f, 0, 0);
        }
      }
      for (unsigned mode = 0; mode <= 4; ++mode) {
        for (unsigned wide = 0; wide < 2; ++wide) {
          unsigned count = run(vlens[vi], profile, wide ? 8 : 4, 65, wide ? 1 : 3,
              2, wide ? 3 : 2, 0, false, mode, -1, 0, 0);
          for (unsigned f = 0; f < count; ++f)
            run(vlens[vi], profile, wide ? 8 : 4, 65, wide ? 1 : 3,
                2, wide ? 3 : 2, 0, false, mode, f, 0, 0);
        }
        run(vlens[vi], profile, 9, 65, 1, 2, 2, 0, false, mode, -1, 0, 0);
        run(vlens[vi], profile, 17, 65, 1, 2, 3, 0, false, mode, -1, 0, 0);
        run(vlens[vi], profile, 5, 65, 3, 2, 1, 0, false, mode, -1, 0, 0);
        run(vlens[vi], profile, 1, 65, 24, 2, 1, 8, false, mode, -1, 0, 0);
        run(vlens[vi], profile, 1, 65, 3, 2, 1, 3, true, mode, -1, 0, 0);
      }
      /* Capacity-limited devices produce legal split plans, not edited plans. */
      for (unsigned layout = 1; layout <= 2; ++layout)
        for (unsigned cap = 0; cap < 2; ++cap) {
          unsigned count = run(vlens[vi], profile, 1, 9, 17, layout, 1, 0, false, 0, -1, cap ? 16 : 8, 0);
          for (unsigned f = 0; f < count; ++f)
            run(vlens[vi], profile, 1, 9, 17, layout, 1, 0, false, 0, f, cap ? 16 : 8, 0);
        }
      run(vlens[vi], profile, 1, 19, 3, 1, 1, 0, false, 0, -1, 0, 7);
      for (unsigned rows = 1; rows <= 3; rows += 2) {
        unsigned count = run(vlens[vi], profile, rows, 9, 17, 1, 1, 0, false, 0, -1, 3, 0);
        for (unsigned f = 0; f < count; ++f)
          run(vlens[vi], profile, rows, 9, 17, 1, 1, 0, false, 0, f, 3, 0);
      }
    }
  }
  /* Exactly one full-N case, K=1. */
  run(1024, QBS_WEIGHT_PROFILE_Q4_K, 1, 151936, 1, 2, 1, 0, false, 1, -1, 0, 0);
  for (unsigned p = 1; p <= 9; ++p) CHECK(profiles_seen[p]);
  for (unsigned i = 0; i < 4; ++i) CHECK(vlens_seen[i]);
  for (unsigned i = 0; i < 6; ++i) CHECK(scopes_seen[i]);
  printf("{\"cases\":%u,\"executor_calls\":%u,\"failure_cases\":%u,\"rejected_option_cases\":%u,"
      "\"eligible_plan_cases\":%u,\"fallback_plan_cases\":%u,\"profiles\":9,\"accepted_vlens\":[256,512,1024],\"rejected_vlens\":[2048]}\n",
      cases, commands, failures, unsupported, eligible_cases, fallback_cases);
  return 0;
}
#endif
