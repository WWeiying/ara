#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "resident_attention/executor.h"
#include "resident_attention/dispatch.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "fixture.h"

enum { CALLS = 3, HEADS = 6, STRIDE = 128, GUARD = 64 };
_Static_assert(sizeof(akv_attention_v2_workspace_t) == 6272, "Workspace ABI");
_Static_assert(AKV_MAX_Q_ROWS == 8 && AKV_V2_TILE_TOKENS == 64, "Tile ABI");
extern const unsigned char data_begin[], data_end[], data_guard_before[], data_guard_after[];
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; akv_attention_v2_workspace_t value; unsigned char after[GUARD];
} workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; uint16_t value[HEADS][STRIDE]; unsigned char after[GUARD];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; float value[HEADS][STRIDE]; unsigned char after[GUARD];
} output;
static struct {
  uint64_t begin, returned, end, initial_fcsr, initial_vcsr, initial_vstart;
  uint64_t fcsr, vcsr, vstart, groups, errors, query_hash, guard_hash, guard_bytes;
  struct { uint32_t first, rows; uint64_t q, k, v, out; } group[2];
  uint32_t bits[HEADS*STRIDE];
} results[CALLS];

/* A deterministic freestanding environment, not a selector for this gate. */
char *getenv(const char *name) { (void)name; return NULL; }

static inline uint64_t cycles(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
  return value;
}

static inline void drain(void) {
  uintptr_t value;
  __asm__ volatile("vmv.x.s %0, v0\nfence rw, rw" : "=r"(value) : : "memory");
}

static inline void read_csr(uint64_t *f, uint64_t *v, uint64_t *s) {
  __asm__ volatile("frcsr %0\ncsrr %1, vcsr\ncsrr %2, vstart"
                   : "=r"(*f), "=r"(*v), "=r"(*s) : : "memory");
}

static uint64_t hash_bytes(uint64_t value, const volatile void *pointer, size_t bytes) {
  const volatile unsigned char *p = pointer;
  for (size_t i = 0; i < bytes; ++i) value = (value ^ p[i])*UINT64_C(1099511628211);
  return value;
}

static uint64_t guard_hash(const sdk_case_t *c, uint64_t *count) {
  uint64_t value = UINT64_C(14695981039346656037);
  *count = 0;
#define HASH(p,n) do { const size_t bytes = (n); value = hash_bytes(value,p,bytes); *count += bytes; } while (0)
  HASH(workspace.before,GUARD); HASH(workspace.after,GUARD);
  HASH(query.before,GUARD); HASH(query.after,GUARD);
  HASH(output.before,GUARD); HASH(output.after,GUARD);
  HASH(data_guard_before,GUARD); HASH(data_guard_after,GUARD);
  for (unsigned h = 0; h < HEADS; ++h) {
    const unsigned start = h < c->heads ? c->dimension : 0;
    HASH(query.value[h]+start,(STRIDE-start)*2);
    HASH(output.value[h]+start,(STRIDE-start)*4);
  }
  for (unsigned h = 0; h < AKV_MAX_Q_ROWS; ++h) {
    const unsigned start = h < c->heads/c->kv_heads ? c->dimension : 0;
    HASH(workspace.value.accumulator[h]+start,(AKV_HEAD_DIM_256-start)*2);
    if (h >= c->heads/c->kv_heads) {
      HASH(workspace.value.score[h],sizeof(workspace.value.score[h]));
      HASH(&workspace.value.maximum[h],4); HASH(&workspace.value.sum[h],4);
      HASH(&workspace.value.old_scale[h],4);
    }
  }
  const size_t tail = offsetof(akv_attention_v2_workspace_t,old_scale)+sizeof(workspace.value.old_scale);
  HASH((const unsigned char *)&workspace.value+tail,sizeof(workspace.value)-tail);
#undef HASH
  return value;
}

typedef struct {
  const sdk_case_t *c;
  const akv_device_t *device;
  const akv_decode_problem_t *problem;
  akv_resident_attention_options_t options;
  unsigned trial, preflight, visited;
} call_context_t;

static int disjoint(uintptr_t a, size_t n, uintptr_t b, size_t m) {
  uintptr_t ae, be;
  return n && m && !__builtin_add_overflow(a,n,&ae) &&
      !__builtin_add_overflow(b,m,&be) && (ae <= b || be <= a);
}

static akv_status_t execute_group(void *opaque, const akv_attention_plan_t *plan,
                                  uint32_t batch, uint32_t first_head) {
  call_context_t *ctx = opaque;
  const sdk_case_t *c = ctx->c;
  const unsigned rows = c->heads/c->kv_heads;
  const unsigned group = first_head/rows;
  if (batch || first_head != ctx->visited*rows || group >= c->kv_heads ||
      plan->descriptor.q_rows != rows || plan->descriptor.head_dim != c->dimension ||
      plan->descriptor.q_base != (uintptr_t)&query.value[first_head][0] ||
      plan->descriptor.k_base != (uintptr_t)c->key+group*c->capacity*256 ||
      plan->descriptor.v_base != (uintptr_t)c->value+group*c->capacity*256 ||
      plan->output != &output.value[first_head][0] || plan->output_row_stride_bytes != 512)
    return AKV_STATUS_LAYOUT;
  if (ctx->preflight) {
    const akv_resident_attention_route_t route = akv_resident_attention_select(
        ctx->device,plan,&ctx->options,0);
    if (route != (c->requested ? AKV_RESIDENT_USE_SHARED : AKV_RESIDENT_KEEP_NATIVE))
      return AKV_STATUS_CAPABILITY;
    if (c->requested) {
      akv_resident_attention_tile_t tile;
      for (unsigned start = 0; start < c->tokens; start += 64)
        if (akv_resident_attention_dispatch_plan(route,&plan->descriptor,start,&tile) != AKV_STATUS_OK)
          return AKV_STATUS_SHAPE;
    }
    ++ctx->visited;
    return AKV_STATUS_OK;
  }
  results[ctx->trial].group[group].first = first_head;
  results[ctx->trial].group[group].rows = rows;
  results[ctx->trial].group[group].q = plan->descriptor.q_base;
  results[ctx->trial].group[group].k = plan->descriptor.k_base;
  results[ctx->trial].group[group].v = plan->descriptor.v_base;
  results[ctx->trial].group[group].out = (uintptr_t)plan->output;
  ++ctx->visited;
  /* Both OFF and ON enter the same enabled SDK executor. No wrapping/retry. */
  return akv_experimental_attention_execute_v2_native(
      ctx->device,plan,&workspace.value,NULL,&ctx->options,1u);
}

static __attribute__((noinline)) akv_status_t full_call(unsigned trial, uint64_t *groups) {
  const sdk_case_t *c = &sdk_cases[trial];
  for (unsigned h = 0; h < c->heads; ++h)
    for (unsigned d = 0; d < c->dimension; ++d) {
      uint32_t bits;
      __asm__ volatile("fcvt.h.s ft0, %1\nfmv.x.h %0, ft0"
          : "=r"(bits) : "f"(c->query[h*STRIDE+d]) : "ft0");
      query.value[h][d] = bits;
    }
  akv_device_t device;
  if (akv_device_query(akv_native_info,NULL,&device) != AKV_STATUS_OK)
    return AKV_STATUS_CAPABILITY;
  const akv_decode_problem_t problem = {
    .query=&query.value[0][0], .key=c->key, .value=c->value, .mask=c->mask,
    .output=&output.value[0][0], .query_bytes=sizeof(query.value),
    .key_bytes=c->capacity*c->kv_heads*256, .value_bytes=c->capacity*c->kv_heads*256,
    .mask_bytes=c->capacity*2, .output_bytes=sizeof(output.value),
    .q_head_stride=256, .q_batch_stride=c->heads*256,
    .k_token_stride=256, .k_head_stride=c->capacity*256,
    .k_batch_stride=c->capacity*c->kv_heads*256,
    .v_token_stride=256, .v_head_stride=c->capacity*256,
    .v_batch_stride=c->capacity*c->kv_heads*256,
    .mask_batch_stride=0, .output_head_stride=512, .output_batch_stride=c->heads*512,
    .batches=1, .query_heads=c->heads, .kv_heads=c->kv_heads,
    .kv_length=c->tokens, .head_dim=c->dimension, .scale=0x1.6a09e6p-4f,
  };
  const uintptr_t bases[] = {(uintptr_t)problem.query,(uintptr_t)problem.key,
      (uintptr_t)problem.value,(uintptr_t)problem.mask,(uintptr_t)problem.output};
  const size_t sizes[] = {problem.query_bytes,problem.key_bytes,problem.value_bytes,
                         problem.mask_bytes,problem.output_bytes};
  for (unsigned i = 0; i < 5; ++i)
    if (!disjoint((uintptr_t)&workspace.value,sizeof(workspace.value),bases[i],sizes[i]))
      return AKV_STATUS_ALIAS;
  call_context_t context = {
    .c=c, .device=&device, .problem=&problem, .trial=trial, .preflight=1,
    .options={.requested=c->requested,.validated_available=1,.platform_admitted=1,
      .whole_call_owned=1,.decode_head_rows=1,.query_tokens=1,.plain_scores=1,
      .refill_overlap=0,.vlenb=128,.frm=0,.vstart=0},
  };
  uint64_t preflight_groups;
  akv_status_t status = akv_decode_execute(&device,&problem,execute_group,&context,&preflight_groups);
  if (status != AKV_STATUS_OK || preflight_groups != c->kv_heads)
    return AKV_STATUS_SHAPE;
  context.preflight = context.visited = 0;
  return akv_decode_execute(&device,&problem,execute_group,&context,groups);
}

int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0, vlenb\nvsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v0,0"
      : "=r"(vlenb) : : "v0","memory");
  drain();
  if (vlenb != 128) { printf("SDK_ATTENTION_FAIL vlenb=%lu\n",vlenb); return 1; }
  uint64_t errors = 0;
  for (unsigned t = 0; t < CALLS; ++t) {
    const sdk_case_t *c = &sdk_cases[t];
    memset(&workspace,0xa5,sizeof(workspace));
    memset(&query,0xa5,sizeof(query));
    memset(&output,0xa5,sizeof(output));
    drain();
    /* Caller-only CSR initialization is outside the complete-call interval. */
    __asm__ volatile("csrw fcsr,%0\ncsrwi vcsr,0\ncsrwi vstart,0"
        : : "r"(c->initial_flags) : "memory");
    read_csr(&results[t].initial_fcsr,&results[t].initial_vcsr,&results[t].initial_vstart);
    results[t].begin = cycles();
    akv_status_t status = full_call(t,&results[t].groups);
    results[t].returned = cycles();
    drain();
    results[t].end = cycles();
    read_csr(&results[t].fcsr,&results[t].vcsr,&results[t].vstart);
    results[t].query_hash = hash_bytes(UINT64_C(14695981039346656037),query.value,sizeof(query.value));
    results[t].guard_hash = guard_hash(c,&results[t].guard_bytes);
    results[t].errors = status != AKV_STATUS_OK || results[t].groups != c->kv_heads ||
        results[t].initial_fcsr != c->initial_flags || results[t].initial_vcsr || results[t].initial_vstart ||
        results[t].fcsr != c->expected_fcsr || results[t].vcsr || results[t].vstart ||
        results[t].query_hash != c->query_hash || results[t].guard_hash != c->guard_hash ||
        results[t].guard_bytes != c->guard_bytes;
    for (unsigned h = 0; h < c->heads; ++h)
      for (unsigned d = 0; d < c->dimension; ++d)
        memcpy(&results[t].bits[h*c->dimension+d],&output.value[h][d],4);
    errors += results[t].errors;
  }
  const uint64_t bytes = (uintptr_t)data_end-(uintptr_t)data_begin;
  const uint64_t hash = hash_bytes(UINT64_C(14695981039346656037),data_begin,bytes);
  errors += bytes != SDK_DATA_BYTES || hash != SDK_DATA_HASH;
  for (unsigned t = 0; t < CALLS; ++t) {
    const sdk_case_t *c = &sdk_cases[t];
    printf("SDK_ATTENTION_CALL trial=%u requested=%lu d=%lu heads=%lu kvheads=%lu tokens=%lu begin=%lu returned=%lu end=%lu initial_fcsr=%lu initial_vcsr=%lu initial_vstart=%lu fcsr=%lu vcsr=%lu vstart=%lu groups=%lu errors=%lu\n",
        t,c->requested,c->dimension,c->heads,c->kv_heads,c->tokens,results[t].begin,results[t].returned,
        results[t].end,results[t].initial_fcsr,results[t].initial_vcsr,results[t].initial_vstart,
        results[t].fcsr,results[t].vcsr,results[t].vstart,results[t].groups,results[t].errors);
    for (unsigned g = 0; g < c->kv_heads; ++g)
      printf("SDK_ATTENTION_GROUP trial=%u group=%u first_head=%u rows=%u q=%lx k=%lx v=%lx output=%lx\n",
          t,g,results[t].group[g].first,results[t].group[g].rows,results[t].group[g].q,
          results[t].group[g].k,results[t].group[g].v,results[t].group[g].out);
    printf("SDK_ATTENTION_MEMORY trial=%u query_hash=%lx guard_hash=%lx guard_bytes=%lu\n",
        t,results[t].query_hash,results[t].guard_hash,results[t].guard_bytes);
    for (unsigned i = 0; i < c->heads*c->dimension; ++i)
      printf("SDK_ATTENTION_OUT trial=%u index=%u bits=%08x\n",t,i,results[t].bits[i]);
  }
  printf("SDK_ATTENTION_DATA bytes=%lu hash=%lx\n",bytes,hash);
  printf("SDK_ATTENTION_DONE calls=3 errors=%lu\n",errors);
  return errors != 0;
}
