// SPDX-License-Identifier: SHL-0.51
#include <stdio.h>
#include "memory_emul_r2_reference.h"
int main(void) {
  unsigned vrf_bytes=0,buffer_bytes=0;
  uint64_t checksum=0;
  for(unsigned phase=0;phase<7;++phase)for(unsigned reg=0;reg<32;++reg)for(unsigned i=0;i<128;++i) {
    checksum+=r2_vrf_byte(phase,reg,i); ++vrf_bytes;
  }
  for(unsigned n=0;n<3;++n)for(unsigned w=0;w<18;++w) {
    checksum^=r2_buffer_word(n,w,0); checksum^=r2_buffer_word(n,w,1); buffer_bytes+=16;
  }
  if(R2_CHECKS!=7*32*18+3*21+3*3+3*3+3*18*2+6+1+1 || vrf_bytes!=28672 || buffer_bytes!=864)return 1;
  printf("R2_BYTE_ORACLE_PASS snapshots=7 traps=3 checks=%u vrfbytes=%u bufferbytes=%u checksum=%llu\n",
         R2_CHECKS,vrf_bytes,buffer_bytes,(unsigned long long)checksum);
  return 0;
}
