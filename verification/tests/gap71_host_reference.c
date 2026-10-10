#include <stdio.h>
#include <string.h>
#include "../../apps/common/gap71_data.h"
int main(void) {
  if(gap71_seed_word(0)!=UINT64_C(0x719ac35e2608b4df)) return 3;
  static uint64_t p[6][512];
  for (int akv=0;akv<2;akv++) for (int fault=0;fault<2;fault++) {
    gap71_init(p,0x80040000,akv,fault);
    for (unsigned j=0;j<6;j++) for (unsigned i=0;i<512;i++)
      printf("P %d %d %u %u %016lx\n",akv,fault,j,i,(unsigned long)p[j][i]);
    if (!akv) {
      float dst[32]; qbs_ref_result_t result;
      memset(dst,0xa5,sizeof(dst));
      if (qbs_ref_execute((void*)p[3],1,8,1024,GAP71_A,&p[5][16],144,
          &p[4][16],292,dst,32,0,0,&result)!=QBS_REF_OK) return 1;
      for (unsigned i=0;i<32;i++) { uint32_t bits; memcpy(&bits,&dst[i],4);
        printf("Q %d %u %08x\n",fault,i,bits); }
      if (result.fflags || result.active_outputs!=1 || result.destination_registers!=1) return 2;
      for(unsigned i=0;i<32;i++) { uint32_t bits; memcpy(&bits,&dst[i],4);
        if(bits!=(i?0:0xc0c00000u)) return 5; }
    }
    if(akv) for(unsigned stream=0;stream<3;stream++) {
      uint16_t dst[64];
      memcpy(dst,(uint8_t*)p[stream?4:5]+(stream==2?512:128),128);
      for(unsigned i=0;i<64;i++) if(dst[i]!=(uint16_t)((stream==0?0x3000:stream==1?0xb400:0x3800)+i*(stream==0?3:stream==1?5:7))) return 4;
    }
    printf("PASSED: gap71_%s_%s checks=%u errors=0\n",akv?"akv":"qbs",fault?"fault":"read",akv?192u:36u);
  }
  return 0;
}
