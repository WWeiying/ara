#include "qbs/qbs.h"
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line=%d\n",__LINE__); return 1; } } while (0)

int main(void) {
    qbs_device_t device;
    CHECK(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
    CHECK(device.capabilities.activation_context_capacity_bytes==4672);
    const unsigned profiles[]={QBS_WEIGHT_PROFILE_Q4_K,QBS_WEIGHT_PROFILE_Q6_K};
    const unsigned ns[]={256,1536,8960};
    const unsigned ks[]={1536,8960};
    unsigned checks=0;
    for (unsigned p=0;p<2;++p) for (unsigned ni=0;ni<3;++ni)
    for (unsigned ki=0;ki<2;++ki) for (unsigned mi=0;mi<2;++mi)
    for (unsigned segmented=0;segmented<2;++segmented) {
        const unsigned m=mi?4:1,k=ks[ki],n=ns[ni];
        qbs_problem_t problem={
            .weight_profile=profiles[p],.activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
            .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
            .activation_storage=mi?QBS_ACTIVATION_STORAGE_M4_GROUPED:QBS_ACTIVATION_STORAGE_ROW_MAJOR,
            .m=m,.n=n,.k_elements=k};
        qbs_plan_t plan;
        qbs_status_t status=segmented?qbs_plan_create_segmented_r4(&device,&problem,256,&plan):qbs_plan_create(&device,&problem,&plan);
        CHECK(status==QBS_STATUS_OK);
        const unsigned payload=m*(k/256)*292;
        CHECK(qbs_plan_supports_activation_context(&plan)==(payload<=4672));
        CHECK(!plan.split_k && !plan.needs_activation_gather);
        printf("CONTEXT profile=%u m=%u n=%u k=%u segment=%u bytes=%u eligible=%d\n",
               profiles[p],m,n,k,segmented?256:0,payload,qbs_plan_supports_activation_context(&plan));
        ++checks;
    }
    printf("CONTEXT_PROBE_PASS checks=%u\n",checks);
    return checks==48?0:1;
}
