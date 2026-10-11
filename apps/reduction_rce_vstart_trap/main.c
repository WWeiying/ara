// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

static volatile uint64_t traps, cause;

__attribute__((interrupt("machine"), aligned(4)))
static void probe_trap(void) {
  uint64_t pc;
  asm volatile("csrr %0,mcause\ncsrr %1,mepc" : "=r"(cause), "=r"(pc));
  traps++;
  pc += 4; // All deliberately trapping instructions below are 32 bits.
  asm volatile("csrw mepc,%0" :: "r"(pc));
}

// crt0 calls this hook in machine mode before entering main in user mode.
void rvtest_init(void) {
  asm volatile("csrw mtvec,%0" :: "r"(probe_trap) : "memory");
}

#define PROBE(OP) do { \
  uint64_t before = traps, start, result; \
  asm volatile("vsetivli zero,4,e32,m1,tu,mu\n" \
               "vmv.v.i v4,1\nvmv.v.i v2,1\nvmv.v.i v8,13\n" \
               "csrwi vstart,4\ncsrr %[start],vstart\n" \
               OP " v8,v4,v2\ncsrwi vstart,0\nvmv.x.s %[result],v8\n" \
               : [start] "=&r"(start), [result] "=&r"(result) :: "memory"); \
  if(start != 4 || traps != before+1 || cause != 2 || result != 13) { \
    printf("FAIL vstart " OP " start=%lu traps=%lu cause=%lu result=%lu\n", \
           start,traps-before,cause,result); failures++; \
  } \
} while(0)

int main(void) {
  unsigned failures=0;
  asm volatile(".word 0xffffffff" ::: "memory");
  if(traps != 1 || cause != 2) {
    printf("FAIL illegal-instruction handler control\n");
    return 1;
  }
  PROBE("vredsum.vs");
  PROBE("vfredmin.vs");
  PROBE("vfredusum.vs");
  PROBE("vfredosum.vs");
  printf("vstart trap check: failures=%u cases=4 handler_control=PASS\n",failures);
  return failures != 0;
}
