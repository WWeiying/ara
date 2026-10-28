#define main fixed_scan_main
#include "workload_scan.c"
#undef main
#include "boundary_plan.h"

int main(void) {
  unsigned cases=0,improved=0;
  puts("queries,gqa,past,fixed_commands,planned_commands,fixed_v,planned_v,fixed_panels,planned_panels");
  const unsigned queries[]={2,4,8,16,40},past[]={0,16,31,64};
  for(unsigned qi=0;qi<5;++qi) for(unsigned g=1;g<=8;++g) for(unsigned pi=0;pi<4;++pi) {
    unsigned rows=queries[qi]*g,visible[320],sizes[40];
    for(unsigned i=0;i<rows;++i)visible[i]=past[pi]+i/g+1;
    unsigned groups=prefill_plan_boundaries(visible,rows,sizes),first=0;
    counts_t fixed=execute(queries[qi],g,past[pi],1),planned={0};
    assert(groups==(rows+7)/8);
    for(unsigned i=0;i<groups;++i) {
      assert(sizes[i]>0 && sizes[i]<=8);
      unsigned maximum=0;
      for(unsigned r=0;r<sizes[i];++r) if(visible[first+r]>maximum)maximum=visible[first+r];
      counts_t c={.last=UINT_MAX,.maximum=maximum};
      akv_quant_online_workspace_t w;float output[8][32];
      akv_quant_online_plan_t p={sizes[i],32,maximum,1,&c,qk,value,scale,mad};
      assert(quant_prefill_prefix_schedule(&p,visible+first,output[0],32,&w)==AKV_QUANT_OK);
      prefill_group_cost_t predicted=prefill_group_cost(visible,first,sizes[i]);
      assert(c.commands==predicted.commands && c.values==predicted.values && c.panels==predicted.panels);
      for(unsigned r=0;r<sizes[i];++r) for(unsigned d=0;d<32;++d) assert(fabsf(output[r][d]-1)<1e-5f);
      planned.commands+=c.commands;planned.values+=c.values;planned.panels+=c.panels;
      planned.dot_rows+=c.dot_rows;first+=sizes[i];
    }
    assert(first==rows && planned.dot_rows==fixed.dot_rows);
    assert(planned.commands<=fixed.commands && planned.values<=fixed.values && planned.panels<=fixed.panels);
    if(planned.commands<fixed.commands || planned.values<fixed.values || planned.panels<fixed.panels)++improved;
    printf("%u,%u,%u,%u,%u,%u,%u,%u,%u\n",queries[qi],g,past[pi],fixed.commands,planned.commands,
      fixed.values,planned.values,fixed.panels,planned.panels);++cases;
  }
  assert(cases==160 && improved>0);
  fprintf(stderr,"BOUNDARY_PLAN_PASS cases=%u improved=%u runtime_installed=0\n",cases,improved);
  return 0;
}
