// SPDX-License-Identifier: Apache-2.0
// Exercise epoch zero: an omitted source tag must not alias a wrapped epoch.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t result;
  asm volatile("li t0, 32\n vsetvli zero, t0, e32, m1, tu, mu\n"
               "vmv.v.i v1, 1\n vmv.v.i v3, 0\n" ::: "t0", "memory");
  for (unsigned i=0; i<255; ++i)
    asm volatile("vmv.v.i v2, 0" ::: "memory");
  asm volatile("csrr zero, vstart\n"
               "vredsum.vs v2, v1, v3\n csrr zero, vstart\n"
               "vmv.v.i v2, 7\n"
               "vredsum.vs v4, v1, v2\n vmv.x.s %[result], v4\n"
               : [result] "=&r"(result) :: "memory");
  int fail=result!=39;
  printf("epoch zero audit: got=%lu expected=39 %s\n",result,fail?"FAIL":"PASS");
  return fail;
}
