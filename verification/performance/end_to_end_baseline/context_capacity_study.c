/* Planner-only what-if study. Changed capabilities are hypothetical, never
 * sent to a device. No performance, area, execution or model-coverage claim. */
#include "qbs/qbs.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#define CHECK(x) do { if(!(x)) { fprintf(stderr,"capacity study failed: %d\n",__LINE__); exit(1); } } while(0)

int main(void) {
  const unsigned profiles[]={QBS_WEIGHT_PROFILE_Q4_K,QBS_WEIGHT_PROFILE_Q5_K,
    QBS_WEIGHT_PROFILE_Q6_K,QBS_WEIGHT_PROFILE_Q3_K,QBS_WEIGHT_PROFILE_Q2_K,
    QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,QBS_WEIGHT_PROFILE_Q4_0,
    QBS_WEIGHT_PROFILE_Q5_0,QBS_WEIGHT_PROFILE_IQ4_NL};
  /* Qwen3-1.7B projection dimensions; rows are a scheduling sweep, not captured
   * activations. Decode and Prefill input reuse have different opportunities. */
  const unsigned shapes[][2]={{2048,2048},{1024,2048},{6144,2048},{2048,6144}};
  const unsigned rows[]={1,4,8};
  puts("profile,m,n,k,capacity_bytes,max_context_blocks,commands,context_eligible,weight_bytes,direct_activation_bytes,context_activation_bytes,macs");
  for(unsigned p=0;p<9;++p)for(unsigned shape=0;shape<4;++shape)
    for(unsigned m=0;m<3;++m)for(unsigned factor=1;factor<=8;factor*=2)
      for(unsigned extended=0;extended<2;++extended) {
        qbs_device_t device; CHECK(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
        device.capabilities.activation_context_capacity_bytes*=factor;
        /* 255 requires a different capability encoding and larger block-tag
         * storage; it is not expressible by the current five-bit query field. */
        if(extended)device.capabilities.activation_context_max_k_blocks=255;
        const qbs_problem_t problem={.weight_profile=profiles[p],
          .activation_profile=qbs_default_activation_profile(profiles[p]),
          .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
          .activation_storage=m==2?QBS_ACTIVATION_STORAGE_M8_GROUPED:
                                  m==1?QBS_ACTIVATION_STORAGE_M4_GROUPED:QBS_ACTIVATION_STORAGE_ROW_MAJOR,
          .m=rows[m],.n=shapes[shape][0],.k_elements=shapes[shape][1]};
        qbs_plan_t plan; CHECK(qbs_plan_create_segmented_r4(&device,&problem,256,&plan)==QBS_STATUS_OK);
        qbs_weight_profile_info_t wi; qbs_activation_profile_info_t ai;
        CHECK(qbs_weight_profile_info(profiles[p],&wi)==QBS_STATUS_OK);
        CHECK(qbs_activation_profile_info(problem.activation_profile,&ai)==QBS_STATUS_OK);
        qbs_plan_cursor_t cursor; qbs_plan_cursor_reset(&cursor);
        uint64_t commands=0,weight=0,activation=0,macs=0;
        for(;;) {
          qbs_command_t c;int present;
          CHECK(qbs_plan_next(&plan,&cursor,&c,&present)==QBS_STATUS_OK);
          if(!present)break;
          CHECK(c.input_start+c.m<=problem.m && c.output_start+c.n<=problem.n &&
                c.k_block_start+c.k_blocks<=plan.k_blocks);
          ++commands;weight+=(uint64_t)c.n*c.k_blocks*wi.block_bytes;
          activation+=(uint64_t)(c.activation_layout==QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED?8:c.m)*c.k_blocks*ai.block_bytes;
          macs+=(uint64_t)c.m*c.n*c.k_blocks*wi.block_elements;
        }
        CHECK(macs==(uint64_t)problem.m*problem.n*problem.k_elements);
        const int eligible=qbs_plan_supports_activation_context(&plan);
        const uint64_t resident=eligible?(uint64_t)problem.m*plan.k_blocks*ai.block_bytes:activation;
        CHECK(resident<=activation);
        printf("%s,%u,%u,%u,%u,%u,%"PRIu64",%d,%"PRIu64",%"PRIu64",%"PRIu64",%"PRIu64"\n",
          qbs_weight_profile_name(profiles[p]),problem.m,problem.n,problem.k_elements,
          device.capabilities.activation_context_capacity_bytes,
          device.capabilities.activation_context_max_k_blocks,commands,eligible,
          weight,activation,resident,macs);
      }
  return 0;
}
