#include <stdio.h>
#include "narrow_reject_r1_reference.h"
int main(void) {
  static const uint8_t anchors[4] = {0x35,0x42,0x4f,0x5c};
  static const uint8_t recovery[4] = {0x56,0x63,0x70,0x7d};
  for (unsigned i=0;i<4;++i)
    if (r1_seed(0,i)!=anchors[i] || (uint8_t)(r1_seed(8,i)+1)!=recovery[i]) return 1;
  uint64_t fnv=UINT64_C(14695981039346656037);
  for (unsigned r=0;r<32;++r)
    for (unsigned i=0;i<128;++i) {fnv^=r1_seed(r,i);fnv*=UINT64_C(1099511628211);}
  unsigned matrix_count=0;
#define COUNT(N,C,T,W) ++matrix_count;
  R1_MATRIX(COUNT)
#undef COUNT
  if (matrix_count!=24 || R1_CHECKS!=26*32*18+24*21+9) return 2;
  for (unsigned p=0;p<26;++p)
    for (unsigned r=0;r<32;++r)
      for (unsigned w=0;w<18;++w) {
        uint64_t wanted=UINT64_C(0xa5a5a5a5a5a5a5a5);
        if (w && w<17) {
          wanted=0;
          for (unsigned b=0;b<8;++b) {
            unsigned i=(w-1)*8+b;
            uint8_t v=(uint8_t)(r*36+i*13+(((i>>3)^r)-r)*7+0x35);
            if (p==25 && r==16 && i<4) v=recovery[i];
            wanted|=(uint64_t)v<<(8*b);
          }
        }
        if (r1_dump_word(p,r,w)!=wanted) return 3;
      }
  printf("R1_HOST_PASS cases=24 checks=15489 seed_fnv=%016lx\n",(unsigned long)fnv);
  return 0;
}
