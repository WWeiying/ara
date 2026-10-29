#include "q8_K-m4-packed.h"
#include "quantizer_candidate.h"
#include <cstdio>
#include <cstring>
#include <cassert>
#include <initializer_list>

alignas(64) static float input[4*6144],saved[4*6144],capture[15*1536];
alignas(64) static block_q8_Kx4 expected[26],actual[26];
static unsigned cases,real_cases,vector_cases;
static void one(int k,bool real) {
  std::memcpy(saved,input,4*k*sizeof(float));
  for(unsigned sticky: {0u,8u,31u}) {
    std::memset(expected,0xa5,sizeof(expected));std::memcpy(actual,expected,sizeof(actual));
    __asm__ volatile("fscsr %0;csrwi vcsr,5"::"r"((uintptr_t)sticky):"memory");
    const bool old=ggml_riscv_q8_K_m4_packed::quantize(input,expected+1,k);
    uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
    __asm__ volatile("fscsr %0;csrwi vcsr,5"::"r"((uintptr_t)sticky):"memory");
    const bool candidate=qbs_m4_parallel_sums::quantize(input,actual+1,k);
    uintptr_t nc,nv;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(nc),"=r"(nv)::"memory");
    assert(old==candidate && fc==nc && vc==nv && nv==5);
    assert(!std::memcmp(expected,actual,sizeof(expected)));
    std::memset(actual,0xa5,sizeof(actual));
    __asm__ volatile("fscsr %0;csrwi vcsr,5"::"r"((uintptr_t)sticky):"memory");
    const bool integrated=ggml_riscv_q8_K_m4_packed::quantize<true>(input,actual+1,k);
    __asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(nc),"=r"(nv)::"memory");
    assert(old==integrated && fc==nc && vc==nv && nv==5);
    assert(!std::memcmp(expected,actual,sizeof(expected)));
    assert(!std::memcmp(input,saved,4*k*sizeof(float)));
    ++cases;real_cases+=real;vector_cases+=candidate;
  }
}
int main(void) {
  FILE *f=std::fopen("/activation.bin","rb");assert(f);
  assert(std::fread(capture,1,sizeof(capture),f)==sizeof(capture));
  assert(std::fgetc(f)==EOF);std::fclose(f);
  for(unsigned group=0;group<3;++group) {
    std::memcpy(input,capture+group*4*1536,4*1536*sizeof(float));one(1536,true);
  }
  for(int k: {256,512,1536,6144}) for(unsigned pattern=0;pattern<4;++pattern) {
    for(int i=0;i<4*k;++i)
      input[i]=pattern==0?0.0f:pattern==1?(i%2?-1.0f:1.0f):
          pattern==2?(float)((i*17)%255-127)*0.125f:(float)((i*31)%1023-511)*0.03125f;
    one(k,false);
  }
  assert(cases==57 && real_cases==9 && vector_cases>0);
  std::printf("M4_SUMS_QUANTIZER_PASS cases=%u real=%u exact=1 flags=1 guards=1\n",cases,real_cases);
  return 0;
}
