// Actual overlaid akv.cpp + real archived plan/features/admission. Native entries
// below are counting stubs ONLY: this executable proves control, not arithmetic.
#include "akv.cpp"
#include <cassert>
#include <cstdarg>
#include <stdexcept>

static bool granted=false,deny_lease=false;
static unsigned reads=0,acquires=0,releases=0,info=0,conversions=0,native=0,shared=0,features_native=0;
static uintptr_t test_frm=0,test_vstart=0;
static bool all_preflight_before_convert=false;
static unsigned expected_groups=2;
static unsigned reads_at_acquire=0;
static bool owned=false;
static bool legacy_granted=true;
static unsigned quantized=0;

static akv_platform_result_t read_state(void *,akv_platform_thread_state_v1 *s) {
    ++reads;
    if (test_vstart) return AKV_PLATFORM_BAD_VSTART;
    *s={128,0,test_frm<<5|8,5}; return AKV_PLATFORM_READY;
}
static uintptr_t acquire(void *,const akv_platform_request_v1 *r) {
    ++acquires;assert(r->groups==expected_groups && conversions==0);
    reads_at_acquire=reads;
    if (!deny_lease) { assert(!owned);owned=true; }
    return deny_lease?0:17;
}
static void release(void *,uintptr_t cookie) { assert(cookie==17 && owned);owned=false;++releases; }
static akv_resident_platform_provider_v1 provider={1,sizeof(provider),AKV_PLATFORM_VALIDATED_TEST_MODEL,
    AKV_PLATFORM_REQUIRED_ASSURANCES,{1},3,1,1,4,1024,nullptr,read_state,acquire,release};
static ggml_akv_legacy_contract_v1 legacy={1,sizeof(legacy),&provider,{1},7,1};
extern "C" const ggml_akv_legacy_contract_v1 *ggml_akv_legacy_current_v1() {
    return legacy_granted?&legacy:nullptr;
}
ggml_riscv_quant_kv_status ggml_riscv_quant_kv_flash_attn(const ggml_compute_params *,ggml_tensor *dst) {
    assert(owned && dst->src[1]->type==GGML_TYPE_Q4_0);++quantized;
    return ggml_riscv_quant_kv_status::complete;
}

extern "C" const akv_resident_platform_provider_v1 *akv_resident_platform_current_v1() {
    return granted?&provider:nullptr;
}
extern "C" uint64_t akv_native_info(void *,unsigned i) {
    ++info;assert(granted && !test_vstart && !test_frm);
    return i<2?akv_capability_word(i,1):akv_v2_capability_word(i,1);
}
extern "C" void ggml_abort(const char *,int,const char *,...) { throw std::runtime_error("terminal"); }
extern "C" size_t ggml_nbytes(const ggml_tensor *t) {
    return (t->ne[3]-1)*t->nb[3]+(t->ne[2]-1)*t->nb[2]+(t->ne[1]-1)*t->nb[1]+t->ne[0]*t->nb[0];
}
extern "C" bool ggml_is_contiguous(const ggml_tensor *) { return true; }
float ggml_table_f32_f16[1<<16]; // emulation is never entered in this control-only test
extern "C" void ggml_vec_dot_f16(int,float *,size_t,ggml_fp16_t *,size_t,ggml_fp16_t *,size_t,int) {
    assert(false);
}
extern "C" akv_status_t akv_attention_execute_v2_prefill_reference(const akv_device_t *,
    const akv_attention_v2_prefill_problem_t *,akv_attention_v2_prefill_workspace_t *) {
    assert(false);return AKV_STATUS_BAD_ARGUMENT;
}
static void convert_stub(const float *,void *out,int64_t n) {
    assert(granted && owned && !deny_lease);
    all_preflight_before_convert=reads-reads_at_acquire>=expected_groups+3;
    ++conversions; std::memset(out,0,n*2);
}
extern "C" const ggml_type_traits_cpu *ggml_get_type_traits_cpu(ggml_type) {
    static ggml_type_traits_cpu t=[] { ggml_type_traits_cpu x{};x.from_float=convert_stub;return x;}();
    return &t;
}
extern "C" akv_status_t akv_experimental_attention_execute_v2_native(const akv_device_t *,
    const akv_attention_plan_t *p,akv_attention_v2_workspace_t *,const akv_attention_features_t *,
    const akv_resident_attention_options_t *o,unsigned automatic) {
    assert(o->requested && o->platform_admitted && o->whole_call_owned && automatic==1);
    assert(p->descriptor.q_rows==2 && p->descriptor.head_dim==128);
    ++shared;return AKV_STATUS_OK;
}
extern "C" akv_status_t akv_attention_execute_v2_native(const akv_attention_plan_t *,akv_attention_v2_workspace_t *) {
    ++native;return AKV_STATUS_OK;
}
extern "C" akv_status_t akv_attention_execute_v2_native_auto(const akv_device_t *,const akv_attention_plan_t *,akv_attention_v2_workspace_t *) {
    ++native;return AKV_STATUS_OK;
}
extern "C" akv_status_t akv_attention_execute_v2_with_features_native(const akv_attention_plan_t *,akv_attention_v2_workspace_t *,const akv_attention_features_t *) {
    ++features_native;return AKV_STATUS_OK;
}
extern "C" akv_status_t akv_attention_execute_v2_with_features_native_auto(const akv_device_t *,const akv_attention_plan_t *,akv_attention_v2_workspace_t *,const akv_attention_features_t *) {
    ++features_native;return AKV_STATUS_OK;
}
extern "C" akv_status_t akv_attention_execute_native(const akv_attention_plan_t *) { assert(false);return AKV_STATUS_BAD_ARGUMENT; }
extern "C" akv_status_t akv_attention_execute_v2_prefill_native(const akv_device_t *,const akv_attention_v2_prefill_problem_t *,akv_attention_v2_prefill_workspace_t *) {
    assert(false);return AKV_STATUS_BAD_ARGUMENT;
}

int main() {
    setenv("GGML_RISCV_AKV","1",1);setenv("GGML_RISCV_AKV_EMULATE","0",1);
    setenv("GGML_RISCV_AKV_RESIDENT","1",1);unsetenv("AKV_PAIR_HEADS");
    setenv("GGML_RISCV_AKV_QUANT_KV","1",1); // exact common switch in frozen models04
    auto *poison=reinterpret_cast<ggml_tensor *>(uintptr_t(1));
    assert(!ggml_riscv_akv_flash_attn(nullptr,poison) && info==0 && reads==0);
    granted=true;test_frm=1;
    assert(!ggml_riscv_akv_flash_attn(nullptr,poison) && info==0);
    test_frm=0;test_vstart=1;
    try { ggml_riscv_akv_flash_attn(nullptr,poison);assert(false); } catch (const std::runtime_error &) {}
    assert(info==0 && acquires==0);test_vstart=0;
    alignas(64) float qdata[4*128]={},output[4*128]={};
    alignas(64) uint16_t kdata[2*9*128]={},vdata[2*9*128]={},maskdata[9]={};
    auto tensor=[](void *data,ggml_type type,int64_t d,int64_t n,int64_t h,size_t b) {
        ggml_tensor t{};t.data=data;t.type=type;t.ne[0]=d;t.ne[1]=n;t.ne[2]=h;t.ne[3]=1;
        t.nb[0]=b;t.nb[1]=d*b;t.nb[2]=n*t.nb[1];t.nb[3]=h*t.nb[2];return t;
    };
    auto q=tensor(qdata,GGML_TYPE_F32,128,1,4,4);
    auto k=tensor(kdata,GGML_TYPE_F16,128,9,2,2),v=tensor(vdata,GGML_TYPE_F16,128,9,2,2);
    auto mask=tensor(maskdata,GGML_TYPE_F16,9,1,1,2),dst=tensor(output,GGML_TYPE_F32,128,4,1,4);
    dst.src[0]=&q;dst.src[1]=&k;dst.src[2]=&v;dst.src[3]=&mask;
    const float scale=1;std::memcpy(dst.op_params,&scale,4);
    ggml_compute_params params{};params.nth=1;
    legacy_granted=false;
    assert(!ggml_riscv_akv_flash_attn(&params,&dst) && info==0 && acquires==0);
    legacy_granted=true;
    deny_lease=true;
    assert(!ggml_riscv_akv_flash_attn(&params,&dst) && info==4 && conversions==0 && releases==0);
    deny_lease=false;
    assert(ggml_riscv_akv_flash_attn(&params,&dst));
    assert(shared==2 && native==0 && releases==1 && conversions==4 && all_preflight_before_convert);
    conversions=0;setenv("GGML_RISCV_AKV_RESIDENT","0",1);
    assert(ggml_riscv_akv_flash_attn(&params,&dst) && native==2 && shared==2 && releases==2);
    conversions=0;setenv("GGML_RISCV_AKV_RESIDENT","1",1);
    setenv("GGML_RISCV_AKV_PORTABLE","1",1);maskdata[3]=0x3c00; // plain gate rejects, real features path retained
    assert(ggml_riscv_akv_flash_attn(&params,&dst) && features_native==2 && shared==2 && releases==3);
    conversions=0;dst.data=qdata; // alias: no mutation, no acquire, no fallback retry
    const auto old=acquires;
    assert(!ggml_riscv_akv_flash_attn(&params,&dst) && acquires==old && conversions==0);
    ggml_akv_resident_counters_v1 c{};ggml_akv_resident_snapshot_v1(&c);
    assert(c.denied==2 && c.lease_denied==1 && c.resident_calls==1 && c.native_calls==2);
    assert(c.resident_groups==2 && c.native_groups==4 && c.completed==3 && c.failed==0);
    dst.data=output;k.type=GGML_TYPE_Q4_0;
    assert(ggml_riscv_akv_flash_attn(&params,&dst) && quantized==1 && releases==4 && conversions==0);
    ggml_akv_resident_snapshot_v1(&c);
    assert(c.legacy_calls==1 && c.legacy_completed==1 && c.legacy_fallback==0 && c.resident_groups==2);
    legacy.whole_process_ram=0;
    assert(!ggml_riscv_akv_flash_attn(&params,&dst) && quantized==1 && releases==4);
    legacy.whole_process_ram=1;legacy.operation_mask=GGML_AKV_LEGACY_BASE;
    assert(!ggml_riscv_akv_flash_attn(&params,&dst) && quantized==1 && releases==4);
    granted=false;setenv("GGML_RISCV_AKV_EMULATE","1",1);
    assert(!ggml_riscv_akv_flash_attn(&params,&dst) && quantized==1 && info==4 && releases==4);
    std::puts("GGML_CONTROL_PASS resident_groups=2 native_groups=4 actual_numeric=0 native_execution=0");
}
