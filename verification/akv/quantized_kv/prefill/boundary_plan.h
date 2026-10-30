#ifndef QUANT_PREFILL_BOUNDARY_PLAN_H
#define QUANT_PREFILL_BOUNDARY_PLAN_H

/* Experimental planner, not installed in the runtime. Cost construction walks
 * tiles and is not yet approved for large-context execution overhead. */
typedef struct { unsigned values,commands,panels; } prefill_group_cost_t;

static inline prefill_group_cost_t prefill_group_cost(const unsigned *visible,
    unsigned first,unsigned rows) {
  prefill_group_cost_t c={0};
  for(unsigned r=0;r<rows;++r) if(visible[first+r]>c.values)c.values=visible[first+r];
  c.panels=(c.values+31)/32;
  for(unsigned token=0;token<c.values;token+=32)
    for(unsigned r=0;r<rows;) {
      unsigned n=visible[first+r]>token?visible[first+r]-token:0;if(n>32)n=32;
      if(!n){++r;continue;}
      unsigned end=r+1;
      while(end<rows) {
        unsigned other=visible[first+end]>token?visible[first+end]-token:0;
        if(other>32)other=32;
        if(other!=n)break;
        ++end;
      }
      unsigned length=end-r;c.commands+=length/4+(length%4)/2+length%2;r=end;
    }
  return c;
}

static inline prefill_group_cost_t prefill_cost_add(prefill_group_cost_t a,prefill_group_cost_t b) {
  return (prefill_group_cost_t){a.values+b.values,a.commands+b.commands,a.panels+b.panels};
}

/* Caller supplies positive visible prefixes and ceil(rows/8) writable slots.
 * A backward pass redistributes tail slack without reordering any row. */
static inline unsigned prefill_plan_boundaries(const unsigned *visible,unsigned rows,unsigned *sizes) {
  unsigned groups=(rows+7)/8;
  for(unsigned i=0;i<groups;++i)sizes[i]=rows-i*8<8?rows-i*8:8;
  unsigned end=rows;
  for(unsigned right=groups;right>1;--right) {
    unsigned i=right-2,total=sizes[i]+sizes[i+1],first=end-total,best=sizes[i];
    prefill_group_cost_t cost=prefill_cost_add(prefill_group_cost(visible,first,best),
                                              prefill_group_cost(visible,first+best,total-best));
    unsigned low=total>8?total-8:1;
    for(unsigned left=low;left<total && left<=8;++left) {
      prefill_group_cost_t candidate=prefill_cost_add(prefill_group_cost(visible,first,left),
                                 prefill_group_cost(visible,first+left,total-left));
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
