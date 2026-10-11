// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t a,b,c,d,e;
  asm volatile(
    "li t0,32\nvsetvli zero,t0,e32,m1,tu,mu\n"
    "vmv.v.i v2,3\nvmv.v.i v4,1\nvmv.v.i v6,5\nvmv.v.i v8,5\n"
    // The producer supplies BOTH the seed and the real source vector.
    "vredsum.vs v8,v4,v2\nvredsum.vs v10,v8,v8\nvmv.x.s %[a],v10\n"
    // A mask RAW must survive late binding of the same register as seed.
    "vmv.v.i v0,0\nvredsum.vs v0,v4,v2\n"
    "vredsum.vs v10,v4,v0,v0.t\nvmv.x.s %[b],v10\n"
    // A younger scalar result aliases the older reduction's vector source.
    "vredsum.vs v8,v4,v2\nvredsum.vs v4,v6,v8\nvmv.x.s %[c],v4\n"
    // An ordinary vector definition supersedes the cached reduction version.
    "vmv.v.i v4,1\nvredsum.vs v8,v4,v2\nvadd.vv v8,v6,v6\n"
    "vredsum.vs v10,v4,v8\nvmv.x.s %[d],v10\n"
    // Wrap the eight-bit destination epoch and reuse all instruction IDs.
    "vmv.v.i v8,3\n.rept 288\nvredsum.vs v8,v4,v8\n.endr\n"
    "vmv.x.s %[e],v8\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d),[e] "=&r"(e)
    :: "t0","memory");
  if(a!=225 || b!=38 || c!=195 || d!=42 || e!=9219) {
    printf("FAIL integer seed hazards source=%lu mask=%lu war=%lu version=%lu wrap=%lu\n",a,b,c,d,e);return 1;
  }
  printf("RCE integer seed hazards PASS: source/Mask RAW, source WAR, replaced seed, 288-step epoch wrap\n");
  return 0;
}
