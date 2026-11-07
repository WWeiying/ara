#include "rms-norm.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

static unsigned cases, rejected;
#define CHECK(x) do { if (!(x)) { std::printf("RMS_GGML_RUNTIME_FAIL line=%d cases=%u\n",__LINE__,cases); std::exit(1); } } while (0)
static float actual[2060];
#if GGML_RISCV_ORDERED_RMS_AVAILABLE
static unsigned aliases;
static float x[2060], w[2060], expected[2060];
static float bits_float(uint32_t b) { float f; std::memcpy(&f,&b,4); return f; }
static uint32_t float_bits(float f) { uint32_t b; std::memcpy(&b,&f,4); return b; }
static void state(unsigned mode,unsigned start=0) {
  const uintptr_t fc=(mode<<5)|8u;
  __asm__ volatile("csrw fcsr,%0;csrwi vcsr,5;csrw vstart,%1" :: "r"(fc),"r"((uintptr_t)start) : "memory");
}
static unsigned flags() { uintptr_t f; __asm__ volatile("frcsr %0":"=r"(f)::"memory");return f; }
static void check_vector() {
  uintptr_t c,s;__asm__ volatile("csrr %0,vcsr;csrr %1,vstart":"=r"(c),"=r"(s)::"memory");
  CHECK(c==5 && s==0);
}

/* No C++ copies between VSTART injection and wrapper's entry capture. This
 * separately named noinline shim is also checked in the actual disassembly. */
extern "C" __attribute__((noinline)) unsigned rms_runtime_gate(unsigned mode,unsigned start) {
  state(mode,start);
  const auto c=ggml_rvv_rms_begin(true,2048,0,1);
  uintptr_t fc,vc,vs;
  __asm__ volatile("frcsr %0;csrr %1,vcsr;csrr %2,vstart":"=r"(fc),"=r"(vc),"=r"(vs)::"memory");
  const unsigned result=unsigned(c.enabled) | (unsigned(fc==((mode<<5)|8u) && vc==5)<<1);
  __asm__ volatile("csrwi vstart,0;csrwi frm,0" ::: "memory");
  (void)vs; // libc/ABI copies after entry capture are outside the guard itself.
  return result;
}

static void valid(unsigned mode,size_t n) {
  for(size_t i=0;i<2060;++i) { x[i]=bits_float(0x3e800001u+(uint32_t)(i%71));w[i]=(float)((int)(i%13)-6)*.125f;actual[i]=expected[i]=bits_float(0x4a55aa55); }
  state(mode);
  double sum=0;
  for(size_t i=0;i<n;++i) { volatile float square=x[i]*x[i];volatile double next=sum+(double)square;sum=next; }
  const unsigned sum_flags=flags();
  state(mode);auto c=ggml_rvv_rms_begin(true,(int64_t)n,0,1);double got=-9;
  CHECK(ggml_rvv_rms_sum_row(&c,x,n,&got)==(n!=0));
  CHECK(c.sum_fast==(n?1u:0u) && c.sum_scalar==(n?0u:1u));
  if(n) CHECK(got==sum && flags()==sum_flags);
  else CHECK(got==-9 && flags()==8);
  check_vector();
  state(mode);
  for(size_t i=0;i<n;++i) { volatile float y=x[i]*.33333334f;expected[i]=y*w[i]; }
  const unsigned output_flags=flags();
  state(mode);c=ggml_rvv_rms_begin(true,(int64_t)n,0,1);
  CHECK(ggml_rvv_rms_output_row(&c,actual,x,w,.33333334f,n)==(n!=0));
  CHECK(flags()==(n?output_flags:8u));check_vector();
  CHECK(std::memcmp(actual,expected,sizeof(actual))==0);
  CHECK(c.output_fast==(n?1u:0u) && c.output_scalar==(n?0u:1u));
  ++cases;
}

static void alias(unsigned mode,unsigned kind) {
  constexpr size_t n=257;
  for(size_t i=0;i<2060;++i) { x[i]=(float)(i%23)*.0625f;w[i]=.75f;actual[i]=expected[i]=(float)(i%37)*.03125f; }
  float *a=actual+8,*e=expected+8;
  const float *ax=x,*ex=x,*aw=w,*ew=w;
  if(kind==0) ax=a,ex=e;
  if(kind==1) aw=a,ew=e;
  if(kind==2) ax=a,ex=e,aw=a,ew=e;
  if(kind==3) ax=a-1,ex=e-1;
  if(kind==4) ax=a+1,ex=e+1;
  if(kind==5) aw=a-1,ew=e-1;
  state(mode);for(size_t i=0;i<n;++i) { volatile float y=ex[i]*.33333334f;e[i]=y*ew[i]; }
  const unsigned fc=flags();
  state(mode);auto c=ggml_rvv_rms_begin(true,n,0,1);
  const bool fast=ggml_rvv_rms_output_row(&c,a,ax,aw,.33333334f,n);
  CHECK(fast==(kind<3));
  if(!fast) {
    CHECK(flags()==8); // rejection must happen before FP work or output writes
    for(size_t i=0;i<2060;++i) CHECK(float_bits(actual[i])==float_bits((float)(i%37)*.03125f));
    for(size_t i=0;i<n;++i) { volatile float y=ax[i]*.33333334f;a[i]=y*aw[i]; }
  }
  CHECK(flags()==fc);check_vector();CHECK(std::memcmp(actual,expected,sizeof(actual))==0);
  ++aliases;
}
#endif

int main() {
  CHECK(setenv("GGML_RISCV_ORDERED_RMS_TRACE","1",1)==0);
  for(const char *flag: {"0","01","true","10",""}) {
    CHECK(setenv("GGML_RISCV_ORDERED_RMS",flag,1)==0);
#if GGML_RISCV_ORDERED_RMS_AVAILABLE
    state(0);
#endif
    auto c=ggml_rvv_rms_begin(true,257,0,1);
    double sum=-9;actual[0]=.75f;
    CHECK(!c.enabled && !ggml_rvv_rms_sum_row(&c,nullptr,257,&sum));
    CHECK(!ggml_rvv_rms_output_row(&c,actual,nullptr,nullptr,.5f,257));
    CHECK(sum==-9 && actual[0]==.75f);
#if GGML_RISCV_ORDERED_RMS_AVAILABLE
    CHECK(flags()==8);check_vector();CHECK(c.sum_scalar==1 && c.output_scalar==1);
#endif
    ++rejected;
  }
  CHECK(setenv("GGML_RISCV_ORDERED_RMS","1",1)==0);
#if GGML_RISCV_ORDERED_RMS_AVAILABLE
  for(unsigned mode=0;mode<5;++mode) CHECK(rms_runtime_gate(mode,0)==3);
  CHECK(rms_runtime_gate(0,1)==2);++rejected;
  CHECK(rms_runtime_gate(5,0)==2);++rejected;
  const size_t widths[]={0,1,31,32,33,63,64,65,127,128,129,255,256,257,511,512,513,2048};
  for(unsigned mode=0;mode<5;++mode) {
    for(size_t n:widths) valid(mode,n);
    for(unsigned kind=0;kind<6;++kind) alias(mode,kind);
  }
  CHECK(setenv("GGML_RISCV_ORDERED_RMS_TRACE","0",1)==0);state(0);
  auto c=ggml_rvv_rms_begin(true,32,0,1);double sum;
  CHECK(ggml_rvv_rms_sum_row(&c,x,32,&sum) && c.sum_fast==0 && c.sum_scalar==0);
  ggml_rvv_rms_finish(&c);
  std::printf("RMS_GGML_RUNTIME_PASS cases=%u aliases=%u rejected=%u modes=5 exact=1 flags=1\n",cases,aliases,rejected);
#else
  auto c=ggml_rvv_rms_begin(true,257,0,1);double sum=-9;
  CHECK(!c.enabled && !ggml_rvv_rms_sum_row(&c,nullptr,257,&sum));
  CHECK(!ggml_rvv_rms_output_row(&c,actual,nullptr,nullptr,.5f,257) && sum==-9);
  std::puts("RMS_GGML_RUNTIME_HOST_FALLBACK_PASS no_writes=1");
#endif
  return 0;
}
