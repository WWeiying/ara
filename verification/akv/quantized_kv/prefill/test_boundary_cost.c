#include "boundary_cost_bounded.h"
#include <stdio.h>

static unsigned cases,max_intervals;
static void check(unsigned *visible,unsigned first,unsigned rows) {
  unsigned intervals;
  prefill_group_cost_t a=prefill_group_cost(visible,first,rows);
  prefill_group_cost_t b=prefill_group_cost_bounded(visible,first,rows,&intervals);
  assert(a.values==b.values && a.commands==b.commands && a.panels==b.panels);
  assert(intervals<=2*rows+1);
  if(intervals>max_intervals)max_intervals=intervals;
  ++cases;
}
int main(void) {
  unsigned visible[12],seed=0x71835429;
  const unsigned edges[]={1,2,31,32,33,63,64,65,65503,65504,65505,65535,65536};
  for(unsigned n=1;n<=8;++n) {
    for(unsigned e=0;e<13;++e) {
      for(unsigned i=0;i<12;++i)visible[i]=edges[e];
      check(visible,3,n);
      for(unsigned i=0;i<12;++i)visible[i]=edges[(e+i)%13];
      check(visible,3,n);
    }
    for(unsigned trial=0;trial<256;++trial) {
      for(unsigned i=0;i<12;++i) {
        seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;visible[i]=1+(seed&65535);
      }
      check(visible,3,n);
    }
  }
  assert(cases==2256);
  printf("BOUNDED_COST_PASS cases=%u max_intervals=%u context_max=65536 exact_reference=1\n",cases,max_intervals);
  return 0;
}
