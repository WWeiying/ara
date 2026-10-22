#ifndef NEGATIVE_STRIDE_CASES_H
#define NEGATIVE_STRIDE_CASES_H
struct ns_case { int unmapped,store,boundary,mode,split,gap,base,stride,mask,start,faults; };
static const struct ns_case ns_cases[] = {
  {0,0,5,3,0,1,4114,-4,0,8,0},
  {0,0,5,3,0,3,4134,-8,0,8,0},
  {0,1,1,2,0,1,4098,-4,36,2,1},
  {0,1,1,2,0,3,4102,-8,36,2,1}
};
#endif
