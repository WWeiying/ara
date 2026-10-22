#ifndef NEGATIVE_STRIDE_CASES_H
#define NEGATIVE_STRIDE_CASES_H
struct ns_case { int unmapped,store,boundary,mode,split,gap,base,stride,mask,start,faults; };
static const struct ns_case ns_cases[] = {
  {0,0,3,2,0,1,4106,-4,36,5,1},
  {0,0,3,2,0,3,4118,-8,36,5,1},
  {0,0,3,3,0,1,4106,-4,0,8,0},
  {0,0,3,3,0,3,4118,-8,0,8,0}
};
#endif
