#include "compare.h"
#include <assert.h>
#include <stdlib.h>
int main(void) {
  const size_t n=894976;
  unsigned char *a=malloc(n),*e=malloc(n);
  assert(a && e);
  for(size_t i=0;i<n;++i) a[i]=e[i]=(unsigned char)(i*37u);
  quantkv_bytes_t r=quantkv_compare_bytes(a,e,n);
  assert(r.checked==n && r.first_fail==-1 && !r.state_errors);
  const size_t positions[]={0,12,13,1023,1024,163839,763903,n-1};
  for(unsigned i=0;i<sizeof(positions)/sizeof(positions[0]);++i) {
    const size_t at=positions[i]; a[at]^=1;
    r=quantkv_compare_bytes(a,e,n);
    assert(r.checked==n && r.first_fail==(long)at && !r.state_errors);
    a[at]^=1;
  }
  a[0]^=1; a[n-1]^=1;
  r=quantkv_compare_bytes(a,e,n); assert(r.checked==n && r.first_fail==0);
  free(a); free(e); return 0;
}
