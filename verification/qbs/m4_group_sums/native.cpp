#include "q8_K-m4-packed.h"
#include "quantizer_candidate.h"
#include "printf.h"
#include <cstring>

extern "C" const float sums_input[];
extern "C" const unsigned char sums_golden[];
alignas(64) static unsigned char output[7008+128];
__attribute__((noinline)) static bool baseline(const float *x,void *y) {
  return ggml_riscv_q8_K_m4_packed::quantize(x,y,1536);
}
__attribute__((noinline)) static bool candidate(const float *x,void *y) {
  return qbs_m4_parallel_sums::quantize(x,y,1536);
}
static uint64_t cycle() {
  uint64_t c;__asm__ volatile("fence rw,rw;rdcycle %0":"=r"(c)::"memory");return c;
}
int main() {
  unsigned errors=0,first_fc=0;
  printf("M4_SUMS_SCOPE rows=4 k=1536 bytes=7008 whole_prepare=1 trials=4\n");
  for(unsigned trial=0;trial<4;++trial) {
    const unsigned variant=trial==1 || trial==2;
    std::memset(output,0xa5,sizeof(output));
    __asm__ volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
    const uint64_t begin=cycle();
    const bool used=variant?candidate(sums_input,output+64):baseline(sums_input,output+64);
    const uint64_t elapsed=cycle()-begin;
    uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
    unsigned local=!used || fc>31 || !(fc&8) || vc!=5;
    if(!trial)first_fc=fc;else local+=fc!=first_fc;
    uint64_t signature=UINT64_C(14695981039346656037);
    for(unsigned i=0;i<7008;++i) {
      local+=output[64+i]!=sums_golden[i];
      signature=(signature^output[64+i])*UINT64_C(1099511628211);
    }
    for(unsigned i=0;i<64;++i)local+=output[i]!=0xa5 || output[64+7008+i]!=0xa5;
    errors+=local;
    printf("M4_SUMS_TRIAL id=%u candidate=%u cycles=%lu vector=%u fcsr=%lu vcsr=%lu errors=%u signature=%016lx\n",
           trial,variant,(unsigned long)elapsed,unsigned(used),(unsigned long)fc,
           (unsigned long)vc,local,(unsigned long)signature);
    if(local)return 1;
  }
  printf("M4_SUMS_RESULT trials=4 errors=%u\n",errors);return errors?1:0;
}
