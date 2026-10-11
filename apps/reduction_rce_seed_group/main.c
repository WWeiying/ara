// SPDX-License-Identifier: Apache-2.0
// Cross-VFU seed-group admission, with aliases that must keep real dependencies.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define CHECK_CASE(M,N,D,S,SEED,EXPECTED) do { \
  uint64_t got; \
  asm volatile("li t0," #N "\nvsetvli zero,t0,e64,m" #M ",tu,mu\n" \
    "vmv.v.i v0,1\nvmv.v.i v16,1\nvmv.v.i v24,3\nvmv.v.i v8,7\n" \
    "csrr zero,vstart\n" \
    ".rept 12\nvmul.vv v8,v16,v24\nvredsum.vs " D "," S "," SEED "\n.endr\n" \
    "vmv.x.s %[got]," D "\n" : [got] "=&r"(got) :: "t0","memory"); \
  if (got != (EXPECTED)) { \
    printf("FAIL seed group m" #M " dest=" D " source=" S " seed=" SEED " got=%lu expected=%lu\n",got,(uint64_t)(EXPECTED)); \
    return 1; \
  } \
} while (0)
int main(void) {
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0","memory");
  // Base seed can bind from the producer's captured first word.
  CHECK_CASE(2,32,"v4","v0","v8",35);
  CHECK_CASE(4,64,"v4","v0","v8",67);
  // Interior seed must not bind the base-register cache entry.
  CHECK_CASE(2,32,"v4","v0","v9",35);
  CHECK_CASE(4,64,"v4","v0","v10",67);
  // Source-vector RAW remains even when the seed RAW is eligible.
  CHECK_CASE(2,32,"v4","v8","v8",99);
  CHECK_CASE(4,64,"v4","v8","v8",195);
  // Group write versus scalar destination WAW must still wait.
  CHECK_CASE(2,32,"v8","v0","v8",35);
  CHECK_CASE(4,64,"v8","v0","v8",67);
  printf("PASS seed group: base/interior seed, source RAW, destination WAW; LMUL2/4\n");
  return 0;
}
