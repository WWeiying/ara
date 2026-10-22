#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned stores[512], loads[512];
static void put(volatile unsigned long *p, unsigned i, unsigned long value) {
  assert(i<512); ++stores[i]; p[i]=value;
}
static unsigned long get(volatile unsigned long *p, unsigned i) {
  assert(i<512); ++loads[i]; return p[i];
}
#define ITLB_STORE(p, i, v) put(p, i, v)
#define ITLB_LOAD(p, i) get(p, i)
#include "../../apps/riscv-tests/isa/rv64uv/itlb_bulk_scalar.h"

int main(void) {
  _Static_assert(sizeof(unsigned long)==8, "exact64bit native words required");
  const unsigned long guard=0x5a3c719de4b208f6ul;
  volatile unsigned long page[512];
  unsigned checks=0;
  for (unsigned entry=0;entry<16;entry++) {
    unsigned long c8=(0x00150513ul<<32)|(((0x100ul+entry)<<20)|0x513ul);
    unsigned long c9=(guard&0xffffffff00000000ul)|0x73ul;
    memset(stores,0,sizeof(stores)); memset(loads,0,sizeof(loads));
    itlb_init_page(page,guard,c8,c9);
    for (unsigned word=0;word<512;word++) {
      assert(stores[word]==1);
      assert(page[word]==(word==8?c8:word==9?c9:guard));
    }
    assert(itlb_check_page(page,guard,c8,c9,&checks)==0);
    for (unsigned word=0;word<512;word++) assert(loads[word]==1);
  }
  assert(checks==8192);
  for (unsigned word=0;word<512;word++) {
    page[word]^=1ul<<(word%64); memset(loads,0,sizeof(loads));
    unsigned n=0;
    unsigned long c8=(0x00150513ul<<32)|(((0x100ul+15)<<20)|0x513ul);
    unsigned long c9=(guard&0xffffffff00000000ul)|0x73ul;
    assert(itlb_check_page(page,guard,c8,c9,&n)==1 && n==512);
    for (unsigned i=0;i<512;i++) assert(loads[i]==1);
    page[word]^=1ul<<(word%64);
  }
  for (unsigned word=0;word<512;word++) page[word]^=1;
  unsigned n=0;
  assert(itlb_check_page(page,guard,
      (0x00150513ul<<32)|(((0x100ul+15)<<20)|0x513ul),
      (guard&0xffffffff00000000ul)|0x73ul,&n)==512 && n==512);
  puts("ITLB_BULK_HOST_EXACT8192_STORE_READ_512_SINGLE_FAULTS_AND_512_MULTI_FAILS_PASS");
  return 0;
}
