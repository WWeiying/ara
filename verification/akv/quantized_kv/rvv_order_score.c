#include "verification/qbs/qbs_ref.h"
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

static uint32_t flags(void) {
  const int f=fetestexcept(FE_ALL_EXCEPT);
  return ((f&FE_INEXACT)?1u:0u)|((f&FE_UNDERFLOW)?2u:0u)|
      ((f&FE_OVERFLOW)?4u:0u)|((f&FE_DIVBYZERO)?8u:0u)|((f&FE_INVALID)?16u:0u);
}

/* Host model of the actual pinned RVV kernels' scalar FP instruction order.
 * It is not a new native RVV execution or a replacement GGML implementation.
 * The exported ABI matches HostOracle, but this library is separate from the
 * QBS oracle. Integer products/reductions fit I16/I32 for both input formats. */
int quant_kv_host_score(unsigned kind,const unsigned char *weights,
    const unsigned char *query,uint32_t *bits,uint32_t *fflags) {
  if(kind>1 || !weights || !query || !bits || !fflags) return -1;
  const unsigned wb=kind?18:34;
  for(unsigned b=0;b<4;++b) {
    uint16_t wd,qd;
    memcpy(&wd,weights+b*wb,2); memcpy(&qd,query+b*34,2);
    if((wd&0x7c00)==0x7c00 || (qd&0x7c00)==0x7c00) return -1;
  }
  fenv_t previous;
  if(fegetenv(&previous) || fesetround(FE_TONEAREST)) return -2;
  feclearexcept(FE_ALL_EXCEPT);
  float sum=0.0f;
  for(unsigned b=0;b<4;++b) {
    const unsigned char *w=weights+b*wb,*q=query+b*34;
    uint16_t wh,qh; memcpy(&wh,w,2); memcpy(&qh,q,2);
    const float dw=qbs_ref_fp16_to_fp32(wh),dq=qbs_ref_fp16_to_fp32(qh);
    int dot=0;
    for(unsigned i=0;i<32;++i) {
      const int wi=kind?((i<16?(w[2+i]&15):(w[2+i-16]>>4))-8):(int8_t)w[2+i];
      dot+=wi*(int8_t)q[2+i];
    }
    if(kind) {
      volatile float first=(float)dot*dw;
      sum=fmaf(first,dq,sum);
    } else {
      volatile float scales=dw*dq;
      sum=fmaf((float)dot,scales,sum);
    }
  }
  memcpy(bits,&sum,4);
  *fflags=flags();
  return fesetenv(&previous)?-2:0;
}
