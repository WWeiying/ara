/* Reuse fixture data generation and the independent descriptor arithmetic
 * model. This is not a GGML quantizer or actual QBS hardware execution. */
#define main unused_contiguous_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "runtime_candidate.h"
#include <stdlib.h>

static unsigned char interleaved_keys[sizeof(keys)] __attribute__((aligned(64)));
static unsigned char interleaved_values[sizeof(values)] __attribute__((aligned(64)));
static float expected[16][136];

static qbs_status_t execute_panel(void *opaque,const qbs_descriptor_t *descriptor,
    unsigned m,const void *activation,float *out,size_t stride,unsigned n,int segmented) {
  executor_t *e=opaque;++e->calls;
  if(e->fail_at && e->calls==e->fail_at) return QBS_STATUS_EXECUTION;
  const qbs_descriptor_fields_t f=qbs_unpack_descriptor_header(descriptor->header);
  assert(!segmented && f.n==n && m<=4 && n<=32 && stride>=n &&
         f.activation_access==QBS_ACTIVATION_ACCESS_DIRECT);
  const size_t row=f.k_blocks*(e->input->key_encoding==QBS_WEIGHT_ENCODING_Q4_0?18u:34u);
  float packed[128];qbs_ref_result_t result;
  assert(qbs_ref_execute(descriptor,m,8,1024,(uintptr_t)activation,
      (const void *)(uintptr_t)descriptor->weight_base,n*row,
      activation,m*f.k_blocks*34u,packed,128,NULL,NULL,&result)==QBS_REF_OK);
  assert(!result.fflags);
  for(unsigned h=0;h<m;++h) memcpy(out+h*stride,packed+h*32,n*sizeof(float));
  return QBS_STATUS_OK;
}

static unsigned read_flags(void) {
  unsigned long f;__asm__ volatile("frcsr %0":"=r"(f));return (unsigned)f;
}
static void clear_flags(void) { __asm__ volatile("csrwi fcsr,0":::"memory"); }

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  const size_t bytes=quant_register_workspace_bytes();
  assert(bytes==akv_quant_strided_workspace_bytes() && !(bytes%64));
  void *scratch=aligned_alloc(64,bytes);assert(scratch);
  uintptr_t vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  const unsigned dims[]={32,96,128},groups[]={1,3,6,7},lengths[]={1,31,32,33,64,65};
  unsigned count=0;
  if(vlenb==128) {
    for(unsigned d=0;d<3;++d) for(unsigned g=0;g<4;++g)
      for(unsigned kv=1;kv<=2;++kv) for(unsigned t=0;t<6;++t)
        for(unsigned q4=0;q4<2;++q4) {
          akv_quant_selection_input_t p=prepare(dims[d],groups[g],kv,lengths[t],q4);
          const size_t kr=p.key.token_stride,vr=p.value.token_stride;
          for(unsigned token=0;token<65;++token) for(unsigned h=0;h<kv;++h) {
            memcpy(interleaved_keys+(token*kv+h)*kr,keys+(h*65+token)*kr,kr);
            memcpy(interleaved_values+(token*kv+h)*vr,values+(h*65+token)*vr,vr);
          }
          p.key.data=interleaved_keys;p.key.token_stride=kv*kr;p.key.head_stride=kr;
          p.value.data=interleaved_values;p.value.token_stride=kv*vr;p.value.head_stride=vr;
          executor_t e={.input=&p};
          akv_quant_native_bindings_t b={quantize,decode,scale,mad,execute_panel,&e};
          akv_quant_strided_report_t original,candidate;
          clear_flags();
          assert(akv_quant_strided_execute(&p,&b,scratch,bytes,&original)==0);
          unsigned flags=read_flags();memcpy(expected,output,sizeof(output));
          e.calls=quant_calls=decode_calls=0;memset(output,0xa5,sizeof(output));
          clear_flags();
          assert(quant_register_execute(&p,&b,scratch,bytes,&candidate)==0);
          assert(read_flags()==flags && memcmp(output,expected,sizeof(output))==0);
          assert(candidate.native.command_attempts==original.native.command_attempts &&
                 candidate.native.value_decodes==kv*lengths[t] &&
                 candidate.native.completed_groups==kv &&
                 candidate.key_panels==original.key_panels &&
                 candidate.key_bytes==original.key_bytes &&
                 quant_calls==kv*groups[g] && decode_calls==0);
          ++count;
        }
  }
  akv_quant_selection_input_t p=prepare(128,6,2,33,0);
  executor_t e={.input=&p,.fail_at=1};
  akv_quant_native_bindings_t b={quantize,decode,scale,mad,execute_panel,&e};
  akv_quant_strided_report_t report;
  if(vlenb==128) {
    assert(quant_register_execute(&p,&b,scratch,bytes,&report)==AKV_QUANT_NATIVE_EXECUTION_FAILED);
    assert(e.calls==1 && report.native.command_attempts==1 && !decode_calls &&
           !report.native.completed_groups);
    p.key.bytes=1;
  }
  memset(output,0xa5,sizeof(output));e.calls=quant_calls=decode_calls=0;
  clear_flags();
  assert(quant_register_execute(&p,&b,scratch,bytes,&report)==AKV_QUANT_NATIVE_FALLBACK);
  assert(!e.calls && !quant_calls && !decode_calls && !read_flags());
  for(size_t i=0;i<sizeof(output);++i) assert(((unsigned char *)output)[i]==0xa5);
  free(scratch);
  if(vlenb==128)
    printf("REGISTER_RUNTIME_PASS cases=%u exact=1 flags=1 panels=1 failure_no_retry=1\n",count);
  else puts("REGISTER_RUNTIME_UNSUPPORTED_VLEN_PASS no_effects=1");
  return 0;
}
