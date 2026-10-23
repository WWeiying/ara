#include "../src/akv_refill_schedule.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
  akv_descriptor_t d = {0};
  d.version=AKV_DESCRIPTOR_VERSION;d.element_format=AKV_ELEMENT_FORMAT_F16;
  d.head_dim=128;d.q_rows=6;d.kv_length=72;
  d.q_base=0x10000;d.k_base=0x20000;d.v_base=0x40000;
  d.q_row_stride_bytes=256;d.k_token_stride_bytes=256;d.v_token_stride_bytes=256;
  assert(akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x60000,0x2000));
  assert(!akv_refill_workspace_disjoint(&d,NULL,0x2000));
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x60000,0));
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x20000,0x2000));
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x3ff00,0x2000));
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)(UINTPTR_MAX-63),128));
  const uint64_t kend=d.k_base+(uint64_t)(d.kv_length-1)*d.k_token_stride_bytes+256;
  assert(akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)kend,64));
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)(kend-1),64));
  d.kv_length=64;
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x60000,0x2000));
  d.kv_length=72;d.q_rows=5;
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x60000,0x2000));
  d.q_rows=6;d.head_dim=64;
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x60000,0x2000));
  d.head_dim=128;d.v_base=UINT64_MAX-15;
  assert(!akv_refill_workspace_disjoint(&d,(void *)(uintptr_t)0x60000,0x2000));
  puts("AKV_REFILL_SCHEDULE_PASS checks=12");
  return 0;
}
