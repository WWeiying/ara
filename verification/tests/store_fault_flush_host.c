#include <stdio.h>
#include "store_fault_flush_reference.h"
int main(void) {
  for (unsigned b = 0; b < 5; ++b)
    for (unsigned i = 0; i < 20; ++i)
      printf("B %u %u %016llx\n", b, i, (unsigned long long)sff_expected(b, i));
  for (unsigned i = 0; i < 8; ++i) printf("I %u %u\n", i, sff_offsets[i]);
  return 0;
}
