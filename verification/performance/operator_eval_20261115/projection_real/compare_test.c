#include "compare.h"
#include <stdio.h>
#include <stdlib.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "comparison test line %u\n", __LINE__); exit(1); } } while (0)
int main(void) {
  unsigned char golden[28032], actual[28032];
  for (unsigned i=0; i<sizeof(golden); ++i) golden[i]=(unsigned char)(i*37u);
  memcpy(actual, golden, sizeof(actual));
  format_comparison c = format_compare(actual,golden,sizeof(actual),0,0,0,0);
  CHECK(!c.mismatches && c.first==UINT32_MAX && c.actual_hash==c.expected_hash);
  for (unsigned i=0; i<sizeof(actual); ++i) {
    actual[i]^=1;
    c=format_compare(actual,golden,sizeof(actual),0,0,0,0);
    CHECK(c.count==sizeof(actual) && c.mismatches==1 && c.raw_differences==1 && c.first==i &&
          c.first_actual==actual[i] && c.first_expected==golden[i]);
    actual[i]^=1;
  }
  float g[256], a[256];
  for (unsigned i=0; i<256; ++i) a[i]=g[i]=(float)i-128.0f;
  for (unsigned i=0; i<256; ++i) {
    a[i]=g[i]+1.0f;
    c=format_compare(a,g,256,1,0,0,0);
    CHECK(c.mismatches==1 && c.first==i);
    c=format_compare(a,g,256,1,1,0.0002f,0.0002f);
    CHECK(c.mismatches==1 && c.first==i);
    a[i]=g[i];
  }
  a[0]=nextafterf(g[0], INFINITY);
  c=format_compare(a,g,256,1,1,0.0002f,0.0002f);
  CHECK(!c.mismatches && c.raw_differences==1 && c.actual_hash!=c.expected_hash);
  const float bad[]={NAN, INFINITY, -INFINITY};
  for (unsigned j=0; j<3; ++j) {
    a[0]=bad[j]; c=format_compare(a,g,256,1,1,0.0002f,0.0002f); CHECK(c.mismatches==1);
  }
  a[0]=g[0]; g[0]=NAN;
  c=format_compare(a,g,256,1,1,0.0002f,0.0002f); CHECK(c.mismatches==1);
  puts("PASS exhaustive 28032 byte mutations, 256 output mutations, tolerance and nonfinite rejection");
  return 0;
}
