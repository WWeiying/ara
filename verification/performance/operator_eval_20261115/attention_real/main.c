#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "resident_attention/executor.h"
#include "resident_attention/dispatch.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "fixture.h"

enum { STRIDE = 128, GUARD = 64 };
_Static_assert(sizeof(akv_attention_v2_workspace_t) == 6272, "Workspace ABI");
_Static_assert(AKV_MAX_Q_ROWS == 8 && AKV_V2_TILE_TOKENS == 64, "Tile ABI");
extern const unsigned char data_begin[], data_end[], data_guard_before[], data_guard_after[];
void attention_rvv_reset(void);
int attention_rvv_guards(void);
akv_status_t attention_rvv_group(const akv_attention_plan_t *, akv_attention_v2_workspace_t *);
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; akv_attention_v2_workspace_t value; unsigned char after[GUARD];
} workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; uint16_t value[8][STRIDE]; unsigned char after[GUARD];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; float value[8][STRIDE]; unsigned char after[GUARD];
} output;
int attention_strong_replay;
int attention_replay_rotation_always = 1;
static struct {
  uint64_t begin, returned, end, initial_fcsr, initial_vcsr, initial_vstart;
  uint64_t fcsr, vcsr, vstart, groups, errors, query_hash, guard_hash, guard_bytes;
  struct { uint32_t first, rows; uint64_t q, k, v, out; } group[8];
  uint32_t bits[ATTN_HEADS*ATTN_DIM];
  uint64_t output_hash, model_errors;
} results[ATTN_CALLS];

char *getenv(const char *name) { (void)name; return NULL; }
static inline uint64_t cycles(void) {
  uint64_t x;
  __asm__ volatile("rdcycle %0" : "=r"(x) : : "memory");
  return x;
}
static inline void drain(void) {
  uintptr_t x;
  __asm__ volatile("vmv.x.s %0,v0\nfence rw,rw" : "=r"(x) : : "memory");
}
static inline void csrs(uint64_t *f, uint64_t *v, uint64_t *s) {
  __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart"
      : "=r"(*f), "=r"(*v), "=r"(*s) : : "memory");
}
static uint64_t hash(uint64_t x, const volatile void *ptr, size_t n) {
  const volatile unsigned char *p = ptr;
  for (size_t i = 0; i < n; ++i) x = (x^p[i])*UINT64_C(1099511628211);
  return x;
}
static uint64_t guards(uint64_t *count) {
  uint64_t x = UINT64_C(14695981039346656037);
  *count = 0;
#define HASH(p,n) do { const size_t size = (n); x = hash(x,p,size); *count += size; } while (0)
  HASH(workspace.before,GUARD); HASH(workspace.after,GUARD);
  HASH(query.before,GUARD); HASH(query.after,GUARD);
  HASH(output.before,GUARD); HASH(output.after,GUARD);
  HASH(data_guard_before,GUARD); HASH(data_guard_after,GUARD);
  for (unsigned h = 0; h < 8; ++h) {
    const unsigned start = h < ATTN_HEADS ? ATTN_DIM : 0;
    HASH(query.value[h]+start,(STRIDE-start)*2);
    HASH(output.value[h]+start,(STRIDE-start)*4);
  }
  for (unsigned h = 0; h < 8; ++h) {
    const unsigned start = h < ATTN_HEADS/ATTN_KVHEADS ? ATTN_DIM : 0;
    HASH(workspace.value.accumulator[h]+start,(256-start)*2);
    if (h >= ATTN_HEADS/ATTN_KVHEADS) {
      HASH(workspace.value.score[h],sizeof(workspace.value.score[h]));
      HASH(&workspace.value.maximum[h],4); HASH(&workspace.value.sum[h],4);
      HASH(&workspace.value.old_scale[h],4);
    }
  }
  const size_t tail = offsetof(akv_attention_v2_workspace_t,old_scale)+sizeof(workspace.value.old_scale);
  HASH((const unsigned char *)&workspace.value+tail,sizeof(workspace.value)-tail);
#undef HASH
  return x;
}
typedef struct {
  const akv_device_t *device;
  akv_resident_attention_options_t options;
  unsigned trial, mode, preflight, visited;
} context_t;

static akv_status_t group(void *opaque, const akv_attention_plan_t *p,
                          uint32_t batch, uint32_t first) {
  context_t *c = opaque;
  const unsigned rows = ATTN_HEADS/ATTN_KVHEADS, g = first/rows;
  if (batch || first != c->visited*rows || g >= ATTN_KVHEADS ||
      p->descriptor.q_rows != rows || p->descriptor.head_dim != ATTN_DIM ||
      p->descriptor.q_base != (uintptr_t)&query.value[first][0] ||
      p->descriptor.k_base != (uintptr_t)fixture_key+g*ATTN_CAPACITY*256 ||
      p->descriptor.v_base != (uintptr_t)fixture_value+g*ATTN_CAPACITY*256 ||
      p->output != &output.value[first][0] || p->output_row_stride_bytes != 512)
    return AKV_STATUS_LAYOUT;
  ++c->visited;
  if (c->preflight) {
    if ((c->mode == 2 || c->mode == 3) &&
        akv_resident_attention_select(c->device,p,&c->options,0) !=
        (c->mode == 2 ? AKV_RESIDENT_USE_SHARED : AKV_RESIDENT_KEEP_NATIVE))
      return AKV_STATUS_CAPABILITY;
    return AKV_STATUS_OK;
  }
  results[c->trial].group[g].first = first;
  results[c->trial].group[g].rows = rows;
  results[c->trial].group[g].q = p->descriptor.q_base;
  results[c->trial].group[g].k = p->descriptor.k_base;
  results[c->trial].group[g].v = p->descriptor.v_base;
  results[c->trial].group[g].out = (uintptr_t)p->output;
  if (c->mode == 0) return attention_rvv_group(p,&workspace.value);
  attention_strong_replay = c->mode == 4;
  if (c->mode == 1 || c->mode == 4)
    return akv_attention_execute_v2_native_auto(c->device,p,&workspace.value);
  return akv_experimental_attention_execute_v2_native(
      c->device,p,&workspace.value,NULL,&c->options,1u);
}
static int disjoint(uintptr_t a, size_t n, uintptr_t b, size_t m) {
  uintptr_t ae, be;
  return n && m && !__builtin_add_overflow(a,n,&ae) &&
      !__builtin_add_overflow(b,m,&be) && (ae <= b || be <= a);
}
__attribute__((noinline, noclone)) akv_status_t attention_full_call(unsigned trial, uint64_t *groups) {
  for (unsigned h = 0; h < ATTN_HEADS; ++h)
    for (unsigned d = 0; d < ATTN_DIM; ++d) {
      uint32_t bits;
      __asm__ volatile("fcvt.h.s ft0,%1\nfmv.x.h %0,ft0"
          : "=r"(bits) : "f"(fixture_query[h*128+d]) : "ft0");
      query.value[h][d] = bits;
    }
  akv_device_t device;
  if (akv_device_query(akv_native_info,NULL,&device) != AKV_STATUS_OK)
    return AKV_STATUS_CAPABILITY;
  const akv_decode_problem_t p = {
    .query=&query.value[0][0], .key=fixture_key, .value=fixture_value, .mask=fixture_mask,
    .output=&output.value[0][0], .query_bytes=sizeof(query.value),
    .key_bytes=ATTN_CAPACITY*ATTN_KVHEADS*256, .value_bytes=ATTN_CAPACITY*ATTN_KVHEADS*256,
    .mask_bytes=ATTN_CAPACITY*2, .output_bytes=sizeof(output.value),
    .q_head_stride=256, .q_batch_stride=ATTN_HEADS*256,
    .k_token_stride=256, .k_head_stride=ATTN_CAPACITY*256,
    .k_batch_stride=ATTN_CAPACITY*ATTN_KVHEADS*256,
    .v_token_stride=256, .v_head_stride=ATTN_CAPACITY*256,
    .v_batch_stride=ATTN_CAPACITY*ATTN_KVHEADS*256,
    .mask_batch_stride=0, .output_head_stride=512, .output_batch_stride=ATTN_HEADS*512,
    .batches=1, .query_heads=ATTN_HEADS, .kv_heads=ATTN_KVHEADS,
    .kv_length=ATTN_TOKENS, .head_dim=ATTN_DIM, .scale=ATTN_SCALE,
  };
  const uintptr_t bases[] = {(uintptr_t)p.query,(uintptr_t)p.key,(uintptr_t)p.value,
      (uintptr_t)p.mask,(uintptr_t)p.output};
  const size_t sizes[] = {p.query_bytes,p.key_bytes,p.value_bytes,p.mask_bytes,p.output_bytes};
  for (unsigned i = 0; i < 5; ++i)
    if (!disjoint((uintptr_t)&workspace.value,sizeof(workspace.value),bases[i],sizes[i]))
      return AKV_STATUS_ALIAS;
  context_t context = {
    .device=&device, .trial=trial, .mode=attention_order[trial], .preflight=1,
    .options={.requested=1,.validated_available=1,.platform_admitted=1,
      .whole_call_owned=1,.decode_head_rows=1,.query_tokens=1,.plain_scores=1,
      .refill_overlap=0,.vlenb=128,.frm=0,.vstart=0},
  };
  if (context.mode == 3) {
    context.options.requested = 0;
    context.options.validated_available = 0;
  }
  uint64_t preflight_groups;
  akv_status_t status = akv_decode_execute(&device,&p,group,&context,&preflight_groups);
  if (status != AKV_STATUS_OK || preflight_groups != ATTN_KVHEADS) return AKV_STATUS_SHAPE;
  context.preflight = context.visited = 0;
  return akv_decode_execute(&device,&p,group,&context,groups);
}
int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb\nvsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v0,0"
      : "=r"(vlenb) : : "v0","memory");
  drain();
  if (vlenb != 128) { printf("OP_ATTN_FAIL vlenb=%lu\n",vlenb); return 1; }
  uint64_t errors = 0;
  for (unsigned t = 0; t < ATTN_CALLS; ++t) {
    memset(&workspace,0xa5,sizeof(workspace));
    memset(&query,0xa5,sizeof(query)); memset(&output,0xa5,sizeof(output));
    attention_rvv_reset(); drain();
    __asm__ volatile("csrw fcsr,%0\ncsrwi vcsr,0\ncsrwi vstart,0"
        : : "r"((uintptr_t)ATTN_INITIAL_FLAGS) : "memory");
    csrs(&results[t].initial_fcsr,&results[t].initial_vcsr,&results[t].initial_vstart);
    __asm__ volatile("csrr zero,cycle" : : : "memory");
    results[t].begin = cycles();
    const akv_status_t status = attention_full_call(t,&results[t].groups);
    results[t].returned = cycles(); drain(); results[t].end = cycles();
    __asm__ volatile("csrr zero,cycle" : : : "memory");
    csrs(&results[t].fcsr,&results[t].vcsr,&results[t].vstart);
    results[t].query_hash = hash(UINT64_C(14695981039346656037),query.value,sizeof(query.value));
    results[t].guard_hash = guards(&results[t].guard_bytes);
    results[t].errors = status != AKV_STATUS_OK || results[t].groups != ATTN_KVHEADS ||
        results[t].initial_fcsr != ATTN_INITIAL_FLAGS || results[t].initial_vcsr ||
        results[t].initial_vstart || results[t].fcsr != ATTN_EXPECT_FLAGS ||
        results[t].vcsr || results[t].vstart || !attention_rvv_guards() ||
        results[t].query_hash != ATTN_QUERY_HASH || results[t].guard_hash != ATTN_GUARD_HASH ||
        results[t].guard_bytes != ATTN_GUARD_BYTES;
    for (unsigned h = 0; h < ATTN_HEADS; ++h)
      for (unsigned d = 0; d < ATTN_DIM; ++d) {
        const unsigned i = h*ATTN_DIM+d;
        memcpy(&results[t].bits[i],&output.value[h][d],4);
        results[t].errors += results[t].bits[i] != fixture_golden[i];
        float delta = output.value[h][d]-fixture_model_golden[i];
        if (delta < 0) delta = -delta;
        float model_abs = fixture_model_golden[i];
        if (model_abs < 0) model_abs = -model_abs;
        uint32_t mbits;
        memcpy(&mbits,&fixture_model_golden[i],4);
        results[t].model_errors += (results[t].bits[i] & 0x7f800000u) == 0x7f800000u ||
            (mbits & 0x7f800000u) == 0x7f800000u ||
            !(delta <= 0.003f+0.02f*model_abs);
      }
    results[t].output_hash = hash(UINT64_C(14695981039346656037),results[t].bits,
                                 sizeof(results[t].bits));
    results[t].errors += results[t].model_errors;
    errors += results[t].errors;
  }
  const uint64_t bytes = (uintptr_t)data_end-(uintptr_t)data_begin;
  const uint64_t fingerprint = hash(UINT64_C(14695981039346656037),data_begin,bytes);
  errors += bytes != ATTN_DATA_BYTES || fingerprint != ATTN_DATA_HASH;
  for (unsigned t = 0; t < ATTN_CALLS; ++t) {
    printf("OP_ATTN_CALL trial=%u mode=%u d=%u heads=%u kvheads=%u tokens=%u begin=%lu returned=%lu end=%lu initial_fcsr=%lu initial_vcsr=%lu initial_vstart=%lu fcsr=%lu vcsr=%lu vstart=%lu groups=%lu errors=%lu\n",
        t,attention_order[t],(unsigned)ATTN_DIM,(unsigned)ATTN_HEADS,(unsigned)ATTN_KVHEADS,(unsigned)ATTN_TOKENS,results[t].begin,
        results[t].returned,results[t].end,results[t].initial_fcsr,results[t].initial_vcsr,
        results[t].initial_vstart,results[t].fcsr,results[t].vcsr,results[t].vstart,
        results[t].groups,results[t].errors);
    for (unsigned g = 0; g < ATTN_KVHEADS; ++g)
      printf("OP_ATTN_GROUP trial=%u group=%u first_head=%u rows=%u q=%lx k=%lx v=%lx output=%lx\n",
          t,g,results[t].group[g].first,results[t].group[g].rows,results[t].group[g].q,
          results[t].group[g].k,results[t].group[g].v,results[t].group[g].out);
    printf("OP_ATTN_MEMORY trial=%u query_hash=%lx guard_hash=%lx guard_bytes=%lu\n",
        t,results[t].query_hash,results[t].guard_hash,results[t].guard_bytes);
    printf("OP_ATTN_CHECK trial=%u values=%u output_hash=%lx model_errors=%lu\n",
        t,(unsigned)(ATTN_HEADS*ATTN_DIM),results[t].output_hash,results[t].model_errors);
    for (unsigned i = 0; i < ATTN_PRINT_VALUES; ++i)
      printf("OP_ATTN_OUT trial=%u index=%u bits=%08x\n",t,i,results[t].bits[i]);
  }
  printf("OP_ATTN_DATA bytes=%lu hash=%lx\n",bytes,fingerprint);
  printf("OP_ATTN_DONE calls=%u errors=%lu\n",(unsigned)ATTN_CALLS,errors);
  return errors != 0;
}
