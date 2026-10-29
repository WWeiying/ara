#include "candidate.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int8_t input[128];
static int16_t output[4*8+16],expected[4*8+16];
int main(void) {
  uintptr_t vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  unsigned cases=0;
  for(unsigned vl=16;vl<=128 && vl<=vlenb;vl*=2)
    for(unsigned seed=0;seed<64;++seed) {
      for(unsigned i=0;i<128;++i)
        input[i]=seed==0?-128:seed==1?127:seed==2?(i%2?-128:127):(int8_t)(seed*73+i*19+i*i);
      for(unsigned row=0;row<4;++row) {
        memset(output,0x5a,sizeof(output));memcpy(expected,output,sizeof(output));
        for(unsigned group=0;group<vl/16;++group) {
          int sum=0;
          for(unsigned i=0;i<16;++i) sum+=input[group*16+i];
          expected[4+row+group*4]=(int16_t)sum;
        }
        __asm__ volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
        vint8m1_t q=__riscv_vle8_v_i8m1(input,vl);
        qbs_m4_group_sums(q,output+4+row,vl);
        uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
        assert(fc==8 && vc==5 && !memcmp(output,expected,sizeof(output)));
      }
      ++cases;
    }
  printf("GROUP_SUMS_PASS vlen=%lu cases=%u exact=1 strided=1 csr=1\n",(unsigned long)vlenb*8,cases);
  return 0;
}
