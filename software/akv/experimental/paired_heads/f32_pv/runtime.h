#ifndef AKV_EXPERIMENTAL_F32_PAIR_RUNTIME_H
#define AKV_EXPERIMENTAL_F32_PAIR_RUNTIME_H

#include "akv/akv.h"

extern void akv_v2_update_outputs_f32_generic(
    const float *,float *,const float *,uint32_t,uint32_t,uint32_t);
extern void akv_experimental_pv_f32_pair(
    const float *,float *,const float *,uint32_t,uint32_t);

static inline int akv_prefill_pair_pv_capable(
    unsigned requested,uintptr_t vlenb,const akv_capabilities_t *c,
    unsigned heads,unsigned dim) {
  if (requested != 1 || vlenb != 128 || c == NULL || heads < 2 ||
      heads > AKV_MAX_Q_ROWS || (dim != 64 && dim != 96 && dim != 128) ||
      (heads == 6 && dim == 128))
    return 0;
  return c->valid && c->enabled && c->f16_payload && c->context_count &&
      c->max_q_rows >= heads && c->token_axis_valid && c->token_axis_enabled &&
      c->token_axis_tail && c->token_axis_row_view && c->token_axis_tile_tokens == 64 &&
      (dim == 64 ? c->head_dim_64 : dim == 96 ? c->token_axis_d_axis_tail : c->head_dim_128);
}

/* Exact existing F32 output-row layout, unlike Decode's padded F16 workspace. */
static inline void akv_prefill_pair_pv_dispatch(
    int enabled,const float *score,float *output,const float *scale,
    uint32_t tokens,uint32_t heads,uint32_t dim) {
  if (!enabled) {
    akv_v2_update_outputs_f32_generic(score,output,scale,tokens,heads,dim);
    return;
  }
  uint32_t head = 0;
  for (; head+1 < heads; head += 2)
    akv_experimental_pv_f32_pair(score+head*64,output+head*dim,scale+head,tokens,dim);
  if (head < heads)
    akv_v2_update_outputs_f32_generic(score+head*64,output+head*dim,
                                    scale+head,tokens,1,dim);
}

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector)
extern char *getenv(const char *) __attribute__((weak));
static int akv_prefill_pair_pv_enabled(const akv_device_t *device,unsigned heads,unsigned dim) {
  if (getenv == NULL || heads < 2 || heads > AKV_MAX_Q_ROWS ||
      (dim != 64 && dim != 96 && dim != 128) || (heads == 6 && dim == 128))
    return 0;
  const char *value = getenv("AKV_PREFILL_PAIR_PV");
  if (value == NULL || value[0] != '1' || value[1] != '\0')
    return 0;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  return akv_prefill_pair_pv_capable(1,vlenb,&device->capabilities,heads,dim);
}
#endif

#endif
