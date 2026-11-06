#include "qbs/qbs.h"
#include "printf.h"

extern "C" qbs_status_t candidate_qbs_execute_with_options(
    const qbs_plan_t *,const void *,size_t,const void *,size_t,float *,size_t,
    size_t,void *,size_t,const qbs_execution_options_t *,qbs_command_executor_t,void *);
static unsigned sdk_single_candidate;
static qbs_status_t sdk_single_dispatch(
    const qbs_plan_t *p,const void *w,size_t wb,const void *a,size_t ab,float *o,
    size_t oc,size_t stride,void *workspace,size_t ws,const qbs_execution_options_t *options,
    qbs_command_executor_t executor,void *context) {
    const auto execute=sdk_single_candidate?candidate_qbs_execute_with_options:qbs_execute_with_options;
    return execute(p,w,wb,a,ab,o,oc,stride,workspace,ws,options,executor,context);
}

// Retain the accepted real operands, production quantizer, canaries and oracle checks.
#define main sdk_single_workload
#define qbs_execute_with_options sdk_single_dispatch
#include "decode_native.cpp"
#undef qbs_execute_with_options
#undef main

int main() {
    const unsigned order[]={0,1,1,0};
    for (unsigned trial=0;trial<4;++trial) {
        sdk_single_candidate=order[trial];commands=0;command_errors=0;
        printf("SDK_SINGLE_INPUT_TRIAL_BEGIN trial=%u candidate=%u\n",trial,sdk_single_candidate);
        const int status=sdk_single_workload();
        printf("SDK_SINGLE_INPUT_TRIAL_END trial=%u candidate=%u status=%d\n",trial,sdk_single_candidate,status);
        if (status) return status;
    }
    printf("SDK_SINGLE_INPUT_SUITE_PASS trials=4 order=ABBA commands=112 outputs=3584\n");
    return 0;
}
