/* Test-only failure diagnostics; the unchanged implementation is included. */
#include <stdio.h>
#include "software/akv/experimental/quantized_kv/output_tile/kernel.h"
static int traced_update(unsigned h,unsigned d,size_t stride,float *out,
    const void *v,size_t ts,size_t bytes,unsigned t,
    const akv_output_tile_coefficients_t *c) {
  uintptr_t start,frm;
  __asm__ volatile("csrr %0,vstart;csrr %1,frm":"=r"(start),"=r"(frm));
  const int rc=akv_output_tile_update(h,d,stride,out,v,ts,bytes,t,c);
  if(rc) printf("TILE_DIAGNOSTIC rc=%d h=%u d=%u t=%u stride=%zu ts=%zu bytes=%zu vstart=%lu frm=%lu coeff=%p out=%p v=%p\n",
    rc,h,d,t,stride,ts,bytes,(unsigned long)start,(unsigned long)frm,(const void*)c,(void*)out,v);
  return rc;
}
#define akv_output_tile_update traced_update
#include "software/akv/experimental/quantized_kv/output_tile/online.h"
#undef akv_output_tile_update
static int traced_online(const akv_quant_online_plan_t *p,float *out,size_t stride,
    akv_quant_online_workspace_t *w,const quant_register_pv_view_t *v) {
  uintptr_t start,frm;
  __asm__ volatile("csrr %0,vstart;csrr %1,frm":"=r"(start),"=r"(frm));
  const int rc=akv_output_tile_online(p,out,stride,w,v);
  if(rc) printf("ONLINE_DIAGNOSTIC rc=%d h=%u d=%u t=%u stride=%zu ts=%zu bytes=%zu vstart=%lu frm=%lu p=%p out=%p w=%p view=%p data=%p\n",
    rc,p->heads,p->dim,p->tokens,stride,v->token_stride,v->bytes,(unsigned long)start,
    (unsigned long)frm,(const void*)p,(void*)out,(void*)w,(const void*)v,(const void*)v->data);
  return rc;
}
#define akv_output_tile_online traced_online
#include "software/akv/experimental/quantized_kv/output_tile/runtime.c"
#undef akv_output_tile_online
