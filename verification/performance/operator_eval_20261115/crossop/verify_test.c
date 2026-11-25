#include <stdio.h>
#include <string.h>
#include "verify.h"
#define NEED(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d\n",__LINE__); return 1; } } while (0)
int main(void) {
  unsigned char a[256],b[256];
  for (unsigned i=0;i<256;++i) a[i]=b[i]=(unsigned char)(37*i);
  reuse_check_t r=reuse_check_bytes(a,b,256);
  NEED(r.checked==256 && !r.errors && r.first_bad==~0u);
  for (unsigned i=0;i<256;++i) {
    a[i]^=1; r=reuse_check_bytes(a,b,256);
    NEED(r.checked==256 && r.errors==1 && r.first_bad==i); a[i]^=1;
  }
  memset(a,0xa5,256);
  NEED(!reuse_check_guard(a,256).errors);
  for (unsigned i=0;i<256;++i) {
    a[i]^=1; r=reuse_check_guard(a,256);
    NEED(r.checked==256 && r.errors==1 && r.first_bad==i); a[i]^=1;
  }
  float expected[512],row[512],group[512];
  for (unsigned i=0;i<512;++i) expected[i]=row[i]=(float)i/4;
  for (unsigned rr=0;rr<8;++rr) for (unsigned c=0;c<64;++c)
    group[(c/32*8+rr)*32+c%32]=expected[rr*64+c];
  NEED(!reuse_check_output(row,expected,8,64,0,1).errors);
  NEED(!reuse_check_output(group,expected,8,64,1,0).errors);
  for (unsigned i=0;i<512;++i) {
    row[i]+=1; r=reuse_check_output(row,expected,8,64,0,1);
    NEED(r.checked==512 && r.errors==1 && r.first_bad==i); row[i]-=1;
    unsigned j=(i%64/32*8+i/64)*32+i%32;
    group[j]+=1; r=reuse_check_output(group,expected,8,64,1,0);
    NEED(r.checked==512 && r.errors==1 && r.first_bad==i); group[j]-=1;
  }
  uint32_t nan=0x7fc00000u; memcpy(row,&nan,4);
  NEED(reuse_check_output(row,expected,8,64,0,0).errors==1);
  row[0]=-0.0f;
  NEED(reuse_check_output(row,expected,8,64,0,1).errors==1);
  NEED(!reuse_check_output(row,expected,8,64,0,0).errors);
  puts("FULL_COMPARE_HOST_PASS byte_mutations=256 guard_mutations=256 exact_outputs=512 tolerant_group_outputs=512 nan_and_signed_zero=checked");
  return 0;
}
