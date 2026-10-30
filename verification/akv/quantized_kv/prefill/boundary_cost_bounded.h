#ifndef QUANT_PREFILL_BOUNDARY_COST_BOUNDED_H
#define QUANT_PREFILL_BOUNDARY_COST_BOUNDED_H

#include "boundary_plan.h"
#include <assert.h>

/* Internal prototype: rows<=8, visible prefixes in [1,65536]. Equal-length
 * runs only change at a row's full/partial/empty transitions. Skip intervening
 * identical tiles exactly; this is not a sampled or approximate cost. */
static inline prefill_group_cost_t prefill_group_cost_bounded(const unsigned *visible,
    unsigned first,unsigned rows,unsigned *intervals) {
  assert(visible && rows && rows<=8 && intervals);
  prefill_group_cost_t c={0};*intervals=0;
  for(unsigned r=0;r<rows;++r) {
    unsigned n=visible[first+r];assert(n && n<=65536);
    if(n>c.values)c.values=n;
  }
  c.panels=(c.values+31)/32;
  unsigned limit=c.panels*32;
  for(unsigned token=0;token<limit;) {
    unsigned next=limit,lengths[8],commands=0;
    for(unsigned r=0;r<rows;++r) {
      unsigned n=visible[first+r],full=n/32*32,empty=(n+31)/32*32;
      if(full>token && full<next)next=full;
      if(empty>token && empty<next)next=empty;
      lengths[r]=n>token?n-token:0;if(lengths[r]>32)lengths[r]=32;
    }
    for(unsigned r=0;r<rows;) {
      if(!lengths[r]){++r;continue;}
      unsigned end=r+1;
      while(end<rows && lengths[end]==lengths[r])++end;
      unsigned n=end-r;commands+=n/4+(n%4)/2+n%2;r=end;
    }
    assert(next>token && (next-token)%32==0);
    c.commands+=commands*((next-token)/32);token=next;++*intervals;
  }
  assert(*intervals<=2*rows+1);
  return c;
}
static inline prefill_group_cost_t prefill_cost_for_boundaries(const unsigned *visible,
    unsigned first,unsigned rows) {
  unsigned intervals;
  return prefill_group_cost_bounded(visible,first,rows,&intervals);
}

static inline unsigned prefill_plan_boundaries_bounded(const unsigned *visible,unsigned rows,unsigned *sizes) {
  unsigned groups=(rows+7)/8;
  for(unsigned i=0;i<groups;++i)sizes[i]=rows-i*8<8?rows-i*8:8;
  unsigned end=rows;
  for(unsigned right=groups;right>1;--right) {
    unsigned i=right-2,total=sizes[i]+sizes[i+1],first=end-total,best=sizes[i];
    prefill_group_cost_t cost=prefill_cost_add(prefill_cost_for_boundaries(visible,first,best),
                                              prefill_cost_for_boundaries(visible,first+best,total-best));
    unsigned low=total>8?total-8:1;
    for(unsigned left=low;left<total && left<=8;++left) {
      prefill_group_cost_t candidate=prefill_cost_add(prefill_cost_for_boundaries(visible,first,left),
                                 prefill_cost_for_boundaries(visible,first+left,total-left));
      if(candidate.values<=cost.values && candidate.commands<=cost.commands && candidate.panels<=cost.panels &&
          (candidate.values<cost.values || candidate.commands<cost.commands || candidate.panels<cost.panels)) {
        best=left;cost=candidate;
      }
    }
    sizes[i]=best;sizes[i+1]=total-best;end-=sizes[i+1];
  }
  return groups;
}
#endif
