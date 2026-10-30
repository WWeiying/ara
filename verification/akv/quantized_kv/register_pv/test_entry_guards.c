/* Reuse fixture construction, but exercise rejection with actual machine CSRs. */
#define main unused_contiguous_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "software/akv/experimental/quantized_kv/register_pv/runtime.h"
#include <stdlib.h>

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  const size_t bytes=quant_register_workspace_bytes();
  void *scratch=aligned_alloc(64,bytes);assert(scratch);
  uintptr_t vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  unsigned count=0;
  for(unsigned q4=0;q4<2;++q4) {
    akv_quant_selection_input_t p=prepare(128,2,1,20,q4);
    executor_t e={.input=&p};
    akv_quant_native_bindings_t b={quantize,decode,scale,mad,execute,&e};
    for(unsigned frm=0;frm<=4;++frm) for(unsigned index=0;index<3;++index) {
      const uintptr_t start=index==0?0:index==1?1:31;
      if(vlenb==128 && !frm && !start) continue;
      const uintptr_t fcsr=(frm<<5)|8;
      akv_quant_strided_report_t report;
      memset(output,0xa5,sizeof(output));memset(scratch,0x5a,bytes);
      e.calls=quant_calls=decode_calls=0;
      __asm__ volatile("csrw fcsr,%0;csrw vstart,%1"::"r"(fcsr),"r"(start):"memory");
      const int status=quant_register_execute(&p,&b,scratch,bytes,&report);
      uintptr_t after_fcsr,after_start;
      __asm__ volatile("frcsr %0;csrr %1,vstart;csrwi fcsr,0;csrwi vstart,0"
                       :"=r"(after_fcsr),"=r"(after_start)::"memory");
      assert(status==AKV_QUANT_NATIVE_FALLBACK);
      assert(report.native.selection_reason==AKV_QUANT_SELECT_CAPABILITY);
      assert(!e.calls && !quant_calls && !decode_calls && !report.native.command_attempts);
      assert(after_fcsr==fcsr && after_start==start);
      for(size_t i=0;i<sizeof(output);++i) assert(((unsigned char *)output)[i]==0xa5);
      for(size_t i=0;i<bytes;++i) assert(((unsigned char *)scratch)[i]==0x5a);
      ++count;
    }
  }
  free(scratch);
  printf("REGISTER_GUARD_PASS vlen=%lu cases=%u no_effects=1 csr_preserved=1\n",
         (unsigned long)vlenb*8,count);
  return 0;
}
