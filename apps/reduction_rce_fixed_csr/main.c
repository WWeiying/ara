// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

#define CHECK(CSR, MASK) do { \
  for (uint64_t value=0;value<=(MASK);value++) { \
    uint64_t old,read; \
    asm volatile("csrwi " #CSR ",0\ncsrrw %[old]," #CSR ",%[v]\ncsrr %[read]," #CSR \
      : [old] "=&r"(old),[read] "=&r"(read) : [v] "r"(value)); \
    if(old!=0 || read!=value) {printf("FAIL " #CSR " write value=%lu old=%lu read=%lu\n",value,old,read);return 1;} \
    asm volatile("csrwi " #CSR ",0\ncsrrs %[old]," #CSR ",%[v]\ncsrr %[read]," #CSR \
      : [old] "=&r"(old),[read] "=&r"(read) : [v] "r"(value)); \
    if(old!=0 || read!=value) {printf("FAIL " #CSR " set value=%lu old=%lu read=%lu\n",value,old,read);return 1;} \
    asm volatile("csrwi " #CSR "," #MASK "\ncsrrc %[old]," #CSR ",%[v]\ncsrr %[read]," #CSR \
      : [old] "=&r"(old),[read] "=&r"(read) : [v] "r"(value)); \
    if(old!=(MASK) || read!=((MASK)&~value)) {printf("FAIL " #CSR " clear value=%lu old=%lu read=%lu\n",value,old,read);return 1;} \
  } \
} while(0)

int main(void) {
  CHECK(vxrm,3); CHECK(vxsat,1); CHECK(vcsr,7);
  uint64_t old,read;
  asm volatile("csrwi vcsr,7\ncsrrwi %[old],vcsr,0\ncsrr %[read],vcsr"
    : [old] "=&r"(old),[read] "=&r"(read));
  if(old!=7 || read!=0) {printf("FAIL vcsr immediate old=%lu read=%lu\n",old,read);return 1;}
  asm volatile("csrwi vxrm,3\ncsrrci %[old],vxrm,2\ncsrr %[read],vxrm"
    : [old] "=&r"(old),[read] "=&r"(read));
  if(old!=3 || read!=1) {printf("FAIL vxrm immediate clear old=%lu read=%lu\n",old,read);return 1;}
  printf("Fixed-point CSR PASS: register write/set/clear and immediate old-value semantics\n");return 0;
}
