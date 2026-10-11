// SPDX-License-Identifier: Apache-2.0
// No software completion barriers: CSR accesses themselves must be ordered.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t upper[4] __attribute__((aligned(128)));
static uint64_t lower[4] __attribute__((aligned(128)));
int main(void) {
  uint64_t flags, result;
  asm volatile(
    "vsetivli zero,4,e64,m1,tu,mu\n"
    "vmv.v.x v4,%[one]\nvmv.v.x v6,%[three]\n"
    "csrwi frm,3\ncsrwi fflags,0\n"
    "vfdiv.vv v8,v4,v6\ncsrwi frm,2\n"
    "vfdiv.vv v10,v4,v6\ncsrr %[f],fflags\n"
    "vse64.v v8,(%[up])\nvse64.v v10,(%[down])\n"
    : [f] "=&r"(flags)
    : [one] "r"(0x3ff0000000000000ULL),[three] "r"(0x4008000000000000ULL),
      [up] "r"(upper),[down] "r"(lower) : "memory");
  if(flags!=1) { printf("FAIL FP CSR FRM flags=%lx\n",flags);return 1; }
  for(unsigned i=0;i<4;i++) if(upper[i]!=0x3fd5555555555556ULL || lower[i]!=0x3fd5555555555555ULL) {
    printf("FAIL FP CSR FRM lane=%u upper=%lx lower=%lx\n",i,upper[i],lower[i]);return 1;
  }
  asm volatile(
    "vfdiv.vv v8,v4,v6\ncsrwi fflags,0\ncsrr %[f],fflags\n"
    "vmv.x.s %[r],v8\n"
    : [f] "=&r"(flags),[r] "=&r"(result) :: "memory");
  if(flags || result!=0x3fd5555555555555ULL) {
    printf("FAIL FP CSR clear result=%lx flags=%lx\n",result,flags);return 1;
  }
  // The RCE, not a scalar-result transfer, must deliver NV before the CSR read.
  asm volatile(
    "vmv.s.x v2,%[snan]\ncsrwi fflags,0\n"
    "vfredusum.vs v8,v4,v2\ncsrr %[f],fflags\nvmv.x.s %[r],v8\n"
    "csrwi frm,0\n"
    : [f] "=&r"(flags),[r] "=&r"(result)
    : [snan] "r"(0x7ff0000000000001ULL) : "memory");
  if(flags!=16 || result!=0x7ff8000000000000ULL) {
    printf("FAIL FP CSR RCE result=%lx flags=%lx\n",result,flags);return 1;
  }
  printf("RCE FP CSR order PASS: FRM switch, NX clear, immediate RCE NV read\n");
  return 0;
}
