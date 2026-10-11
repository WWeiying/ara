// SPDX-License-Identifier: Apache-2.0
// Alternate seed values across producer ID reuse and queued exact consumers.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t first[128] __attribute__((aligned(128)));
static uint32_t second[128] __attribute__((aligned(128)));
static int probe(unsigned n, unsigned group) {
 uint64_t a,b;
 // Two group sizes exercise scalar-seed versus whole-vector producer metadata.
 if(group==4) asm volatile("vsetvli t0,%0,e32,m4,tu,mu" :: "r"(n):"t0","memory");
 else asm volatile("vsetvli t0,%0,e32,m1,tu,mu" :: "r"(n):"t0","memory");
 asm volatile("li t0,0x3f800000\nvmv.v.x v4,t0\ncsrr zero,vstart\n"
 ".rept 32\n"
 "vle32.v v8,(%[p])\nvfredusum.vs v24,v4,v8\n"
 "vle32.v v8,(%[q])\nvfredusum.vs v25,v4,v8\n"
 ".endr\ncsrr zero,vstart\nvmv.x.s %[a],v24\nvmv.x.s %[b],v25\n"
 : [a] "=&r"(a),[b] "=&r"(b) : [p] "r"(first),[q] "r"(second):"t0","memory");
 union {float f;uint32_t u;} x={.f=(float)(n+3)},y={.f=(float)(n+5)};
 if((uint32_t)a!=x.u || (uint32_t)b!=y.u) {
  printf("FAIL exact seed versions vl=%u m%u a=%lx b=%lx\n",n,group,a,b);return 1;
 }
 return 0;
}
int main(void) {
 for(unsigned i=0;i<128;i++){first[i]=0x40400000;second[i]=0x40a00000;}
 asm volatile("fence rw,rw\nvsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" :::"t0","memory");
 if(probe(1,1)||probe(16,1)||probe(32,1)||probe(64,4)||probe(128,4))return 1;
 printf("PASS exact seed versions: five shapes, 320 alternating producer/consumer pairs\n");return 0;
}
