/* Full direct-PV instruction boundaries, not SDK admission or a speed benchmark. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "printf.h"
#include "boundary_data.h"

typedef struct {
  uint64_t before_fcsr, before_vstart, traps, cause, pc, mtval;
  uint64_t trap_fcsr, trap_vstart, after_fcsr, after_vstart, unexpected;
  uint64_t armed, expected_pc, resume_pc;
  uint64_t before_mstatus, trap_mstatus, after_mstatus;
  uint64_t before_vl, before_vtype, after_vl, after_vtype, trap_csrs_valid;
} observation_t;
volatile observation_t boundary_observation;
uint32_t boundary_dest_capture[128] __attribute__((aligned(64)));
_Static_assert(offsetof(observation_t, armed) == 88 &&
               offsetof(observation_t, resume_pc) == 104 &&
               offsetof(observation_t, trap_csrs_valid) == 168, "Assembly observation ABI");

extern void resident_pv_prepare(const uint32_t *, const uint16_t *, const uint32_t *,
                                uint64_t, uint64_t, uint64_t);
extern void boundary_fill(const akv_descriptor_t *, uint64_t);
extern void boundary_release(void), boundary_dest_set(const uint32_t *);
extern void boundary_mixed_load(const uint16_t *, const uint64_t *);
extern void boundary_mixed_capture(uint16_t *, uint64_t *);
extern uint64_t boundary_issue(uint64_t, uint64_t, uint64_t, uint64_t,
                               uint16_t *, uint64_t, uint64_t, uint64_t);
extern unsigned boundary_compat(void);

static struct {
  uint64_t before[8];
  uint16_t value[512];
  uint64_t after[8];
} output __attribute__((aligned(64)));
static uint16_t source_capture[384] __attribute__((aligned(64)));
static uint64_t guard_capture[32] __attribute__((aligned(64)));
static unsigned errors, successes, rejected;

static uint64_t fcsr(void) {
  uint64_t x;
  __asm__ volatile("frcsr %0" : "=r"(x) : : "memory");
  return x;
}

static void set_fcsr(uint64_t value) {
  __asm__ volatile("csrw fcsr, %0\ncsrwi vstart, 0\ncsrwi vcsr, 0" : : "r"(value) : "memory");
}

static void drain(void) {
  uint64_t unused;
  __asm__ volatile("vmv.x.s %0, v8\nfence rw, rw" : "=r"(unused) : : "memory");
}

static void fill(const boundary_case_t *c, unsigned d, unsigned t) {
  akv_descriptor_t descriptor = {0};
  descriptor.version = AKV_DESCRIPTOR_VERSION;
  descriptor.element_format = AKV_ELEMENT_FORMAT_F16;
  descriptor.q_rows = c->heads;
  descriptor.head_dim = d;
  descriptor.kv_length = t;
  descriptor.q_row_stride_bytes = 256;
  descriptor.k_token_stride_bytes = 256;
  descriptor.v_token_stride_bytes = 256;
  descriptor.q_base = (uintptr_t)c->query;
  descriptor.k_base = (uintptr_t)c->key;
  descriptor.v_base = (uintptr_t)c->value;
  if (!akv_v2_descriptor_is_valid(&descriptor)) {
    errors++;
    return;
  }
  boundary_fill(&descriptor, 0);
}

static unsigned output_guards(const boundary_case_t *c, unsigned bad) {
  unsigned n = 0;
  for (unsigned i = 0; i < 8; ++i)
    n += output.before[i] != UINT64_C(0xa5a5a5a5a5a5a5a5) ||
         output.after[i] != UINT64_C(0xa5a5a5a5a5a5a5a5);
  for (unsigned h = 0; h < 2; ++h)
    for (unsigned i = (bad || h >= c->heads) ? 0 : c->dimension; i < 256; ++i)
      n += output.value[h*256+i] != 0xa5a5;
  return n;
}

static void data16(unsigned id, const char *kind, const uint16_t *data, unsigned n) {
  printf("PV_BOUNDARY_DATA id=%u phase=1 kind=%s bits=", id, kind);
  for (unsigned i = 0; i < n; ++i) printf("%04x", (unsigned)data[i]);
  printf("\n");
}

static void attempt(const boundary_case_t *c, unsigned bad) {
  memset((void *)&boundary_observation, 0, sizeof(boundary_observation));
  memset(&output, 0xa5, sizeof(output));
  set_fcsr((c->rm << 5) | c->initial_flags);
  if (c->kind == KIND_MIXED) boundary_mixed_load(c->source, boundary_guard_pattern);
  else resident_pv_prepare(c->probability, c->seed, c->scale,
                            c->tokens, c->dimension, c->heads);
  drain();
  const uint64_t prep_fcsr = fcsr();
  errors += prep_fcsr != ((c->rm << 5) | c->initial_flags | c->prepared_flags);
  boundary_dest_set(boundary_dest_pattern);
  const uint64_t issue_rm = bad && c->kind == KIND_FRM ? 5 : c->rm;
  const uint64_t issue_vstart = bad && c->kind == KIND_VSTART ? 1 : 0;
  boundary_issue(bad ? c->bad_control : c->control, issue_rm, issue_vstart, bad,
                  output.value, c->dimension, c->heads, bad ? c->bad_mode : c->vtype_mode);
  const observation_t o = *(const volatile observation_t *)&boundary_observation;
  const unsigned guard_errors = output_guards(c, bad);
  errors += guard_errors + o.unexpected + (o.traps != bad);
  if (bad) {
    rejected++;
    errors += o.cause != 2 || o.pc != o.expected_pc || o.armed != 0;
    const unsigned status_off = c->kind == KIND_FS_OFF || c->kind == KIND_VS_OFF;
    errors += o.trap_csrs_valid != !status_off;
    if (!status_off)
      errors += o.trap_fcsr != o.before_fcsr || o.trap_vstart != issue_vstart;
    else {
      const uint64_t mask = c->kind == KIND_FS_OFF ? 0x6000 : 0x600;
      errors += (o.before_mstatus | o.trap_mstatus | o.after_mstatus) & mask ? 1 : 0;
    }
    errors += o.after_fcsr != o.before_fcsr || o.after_vstart != issue_vstart;
    for (unsigned i = 0; i < 128; ++i)
      errors += boundary_dest_capture[i] != boundary_dest_pattern[i];
  } else {
    successes++;
    errors += o.after_fcsr != ((c->rm << 5) | c->initial_flags | c->prepared_flags | c->pv_flags);
    errors += o.before_vstart != 0 || o.after_vstart != 0;
    errors += o.before_vl != o.after_vl || o.before_vtype != o.after_vtype;
    if (c->vtype_mode == 1) errors += o.after_vl != 0 || o.after_vtype != 0xc0;
    if (c->vtype_mode == 2) errors += o.after_vl != 0 || o.after_vtype != (UINT64_C(1) << 63);
    for (unsigned h = 0; h < c->heads; ++h)
      for (unsigned i = 0; i < c->dimension; ++i)
        errors += output.value[h*256+i] != c->expected[h*c->dimension+i];
  }
  printf("PV_BOUNDARY_CASE id=%lu phase=%u d=%lu heads=%lu tokens=%lu rm=%lu prep_fcsr=%lu before_fcsr=%lu before_vstart=%lu after_fcsr=%lu after_vstart=%lu traps=%lu cause=%lu pc=%016lx mtval=%016lx trap_fcsr=%lu trap_vstart=%lu unexpected=%lu guard_errors=%u before_mstatus=%016lx trap_mstatus=%016lx after_mstatus=%016lx before_vl=%lu before_vtype=%016lx after_vl=%lu after_vtype=%016lx trap_csrs_valid=%lu\n",
         c->id, !bad, c->dimension, c->heads, c->tokens, c->rm, prep_fcsr,
         o.before_fcsr, o.before_vstart, o.after_fcsr, o.after_vstart, o.traps,
         o.cause, o.pc, o.mtval, o.trap_fcsr, o.trap_vstart, o.unexpected, guard_errors,
         o.before_mstatus, o.trap_mstatus, o.after_mstatus, o.before_vl, o.before_vtype,
         o.after_vl, o.after_vtype, o.trap_csrs_valid);
  if (bad) {
    printf("PV_BOUNDARY_DATA id=%lu phase=0 kind=dest32 bits=", c->id);
    for (unsigned i = 0; i < 128; ++i) printf("%08x", boundary_dest_capture[i]);
    printf("\n");
  } else {
    printf("PV_BOUNDARY_DATA id=%lu phase=1 kind=result bits=", c->id);
    for (unsigned h = 0; h < c->heads; ++h)
      for (unsigned i = 0; i < c->dimension; ++i) printf("%04x", (unsigned)output.value[h*256+i]);
    printf("\n");
  }
  if (!bad && c->kind == KIND_MIXED) {
    boundary_mixed_capture(source_capture, guard_capture);
    for (unsigned i = 0; i < 384; ++i) errors += source_capture[i] != c->source[i];
    for (unsigned i = 0; i < 32; ++i) errors += guard_capture[i] != boundary_guard_pattern[i];
    data16(c->id, "source", source_capture, 384);
    printf("PV_BOUNDARY_DATA id=%lu phase=1 kind=guard64 bits=", c->id);
    for (unsigned i = 0; i < 32; ++i) printf("%016lx", guard_capture[i]);
    printf("\n");
  }
}

int main(void) {
  uint64_t vlenb;
  __asm__ volatile("csrr %0, vlenb\nvsetivli zero, 1, e16, m1, ta, ma\nvmv.v.i v8, 0"
                   : "=r"(vlenb) : : "memory");
  printf("PV_BOUNDARY_BEGIN cases=21 vlenb=%lu data=%s\n", vlenb, BOUNDARY_DATA_SHA256);
  if (vlenb != 128) return 1;
  for (unsigned i = 0; i < BOUNDARY_CASES; ++i) {
    const boundary_case_t *c = &boundary_cases[i];
    set_fcsr(0);
    fill(c, c->context_dimension, c->context_tokens);
    if (c->rejection) {
      if (c->kind == KIND_NO_CONTEXT) boundary_release();
      attempt(c, 1);
      /* attempt has captured raw fault CSRs and restored software access.
       * Keep resident hardware state intact; only the released case may reload. */
      if (c->kind == KIND_NO_CONTEXT) fill(c, c->context_dimension, c->context_tokens);
      boundary_case_t recovery = *c;
      recovery.dimension = c->context_dimension;
      recovery.heads = c->context_heads;
      recovery.tokens = c->context_tokens;
      recovery.control = (recovery.tokens-1) | ((recovery.heads-1) << 6) |
          ((recovery.dimension == 64 ? 0 : recovery.dimension == 128 ? 1 : 2) << 7);
      recovery.prepared_flags = c->recovery_prepared_flags;
      recovery.pv_flags = c->recovery_pv_flags;
      recovery.expected = c->recovery_expected;
      attempt(&recovery, 0);
    } else {
      attempt(c, 0);
    }
    boundary_release();
  }
  errors += boundary_compat();
  printf("PV_BOUNDARY_DONE cases=21 successes=%u rejected=%u compat=1 errors=%u\n", successes, rejected, errors);
  return errors != 0;
}
