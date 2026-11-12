/* Synthetic authority only. This file must never authorize a deployed image. */
#include "resident_deployment.h"
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#define HASH_BYTES 0x71,0x39,0x82,0x15,0x21,0x47,0x63,0x89,0x55,0x66,0x77,0x88,0x91,0x23,0x45,0x67,0x12,0x34,0x56,0x78,0x9a,0xbc,0xde,0xf0,0x13,0x57,0x24,0x68,0xab,0xcd,0xef,0x01
#define CHECK(x) do { assert(x); ++checks; } while (0)
static unsigned checks;
static _Alignas(64) uint16_t query[8][256], key[137][256], value[137][256], mask[137];
static _Alignas(64) float output[8][256];
static _Alignas(64) unsigned char scratch[8192];
static akv_platform_span_v1 spans[] = {
    {query,sizeof(query),0}, {key,sizeof(key),0}, {value,sizeof(value),0},
    {mask,sizeof(mask),0}, {output,sizeof(output),1}, {scratch,sizeof(scratch),1}
};
static struct {
    ara_resident_observation_v1 observation;
    akv_platform_thread_state_v1 csr;
    unsigned allowed, observe_ok, csr_reads, acquires, releases, owned;
    unsigned mutate_csr, deny_after_mutation, rotate_owner, poison_observation;
    uintptr_t lease_owner, sequence, cookie, hole;
} ctx;
static ara_resident_deployment_v1 binding;
static const ara_resident_deployment_v1 *selected = &binding;

static int observe(void *authority, ara_resident_observation_v1 *out) {
    assert(authority == &ctx);
    if (!ctx.observe_ok) return 0;
    if (ctx.poison_observation) return 1;
    *out = ctx.observation;
    if (ctx.owned && ctx.lease_owner != out->owner) out->guarantees = 0;
    return 1;
}

akv_platform_result_t akv_resident_platform_read_state_v1(void *unused, akv_platform_thread_state_v1 *out) {
    (void)unused;
    ++ctx.csr_reads;
    if (ctx.csr.vstart) return AKV_PLATFORM_BAD_VSTART;
    *out = ctx.csr;
    return AKV_PLATFORM_READY;
}

static uintptr_t acquire(void *authority, uintptr_t owner, const akv_platform_request_v1 *r) {
    assert(authority == &ctx);
    ++ctx.acquires;
    if (ctx.rotate_owner) { ++ctx.observation.owner; return 0; }
    if (!ctx.allowed || ctx.owned || owner != ctx.observation.owner || r->span_count != 6) return 0;
    for (size_t i = 0; i < r->span_count; ++i) {
        const akv_platform_span_v1 *s = r->spans + i;
        const uintptr_t start = (uintptr_t)s->base;
        if (s->base != spans[i].base || s->bytes != spans[i].bytes || s->writable != spans[i].writable ||
            (ctx.hole >= start && ctx.hole - start < s->bytes)) return 0;
    }
    if (ctx.mutate_csr == 1) ctx.csr.fcsr ^= 1;
    if (ctx.mutate_csr == 2) ctx.csr.vstart = 1;
    if (ctx.deny_after_mutation) return 0;
    ctx.owned = 1;
    ctx.lease_owner = owner;
    return ctx.cookie = ++ctx.sequence;
}

static void release(void *authority, uintptr_t cookie) {
    if (authority != &ctx || !ctx.owned || cookie != ctx.cookie || ctx.lease_owner != ctx.observation.owner)
        __builtin_trap();
    ctx.owned = 0;
    ctx.cookie = 0;
    ++ctx.releases;
}

const ara_resident_deployment_v1 *ara_resident_deployment_current_v1(void) { return selected; }

static void reset(void) {
    memset(&ctx, 0, sizeof(ctx));
    ctx.observation = (ara_resident_observation_v1){
        .abi_version=1, .struct_bytes=sizeof(ctx.observation), .contract_sha256={HASH_BYTES},
        .guarantees=ARA_RESIDENT_REQUIRED, .state_protection=ARA_RESIDENT_KERNEL_CONTEXT,
        .operation_mask=3, .qk_profile=1, .pv_profile=1, .nr_lanes=4, .vlen_bits=1024,
        .owner=37, .legacy_operations=7, .whole_process_ram=1
    };
    ctx.csr = (akv_platform_thread_state_v1){128,0,17,5};
    ctx.allowed = ctx.observe_ok = 1;
    binding = (ara_resident_deployment_v1){
        .abi_version=1, .struct_bytes=sizeof(binding),
        .resident=ARA_RESIDENT_PROVIDER_V1(binding, HASH_BYTES),
        .legacy={.abi_version=1, .struct_bytes=sizeof(binding.legacy), .provider=&binding.resident,
                 .contract_sha256={HASH_BYTES}, .operation_mask=7, .whole_process_ram=1},
        .authority=&ctx, .observe=observe, .acquire=acquire, .release=release
    };
    selected = &binding;
    memset(mask, 0, sizeof(mask));
    memset(output, 0xa5, sizeof(output));
    memset(scratch, 0x5a, sizeof(scratch));
}

static akv_platform_request_v1 request(void) {
    return (akv_platform_request_v1){1,sizeof(akv_platform_request_v1),1,1,1,1,2,0,spans,6};
}

static void no_provider(void) {
    CHECK(akv_resident_platform_current_v1() == NULL);
    CHECK(ggml_akv_legacy_current_v1() == NULL);
    CHECK(ggml_akv_platform_entry_v1(&binding.resident) == AKV_PLATFORM_KEEP_NATIVE);
    CHECK(akv_resident_platform_admit_v1(&binding.resident,(void *)1,(void *)1) == AKV_PLATFORM_KEEP_NATIVE);
    CHECK(!ctx.csr_reads && !ctx.acquires && !ctx.releases);
}

static void binding_rejections(void) {
    reset(); selected = NULL;
    CHECK(!akv_resident_platform_current_v1() && !ggml_akv_legacy_current_v1() && !ctx.csr_reads);
#define BAD(field, x) do { reset(); binding.field=(x); no_provider(); } while (0)
    BAD(abi_version,0); BAD(struct_bytes,0); BAD(observe,NULL); BAD(acquire,NULL); BAD(release,NULL);
    BAD(resident.abi_version,0); BAD(resident.struct_bytes,0); BAD(resident.kind,AKV_PLATFORM_VALIDATED_TEST_MODEL);
    BAD(resident.assurances,0); BAD(resident.operation_mask,1); BAD(resident.qk_profile,0);
    BAD(resident.pv_profile,0); BAD(resident.nr_lanes,8); BAD(resident.vlen_bits,2048);
    BAD(resident.context,NULL); BAD(resident.read_state,NULL); BAD(resident.acquire,NULL); BAD(resident.release,NULL);
#undef BAD
    reset(); memset(binding.resident.contract_sha256,0,32); no_provider();
}

static void observation_rejections(void) {
    for (unsigned bit=0; bit<8; ++bit) {
        reset(); ctx.observation.guarantees ^= 1u << bit; no_provider();
    }
#define BAD(field, x) do { reset(); ctx.observation.field=(x); no_provider(); } while (0)
    BAD(abi_version,0); BAD(struct_bytes,0); BAD(guarantees,ARA_RESIDENT_REQUIRED|256);
    BAD(state_protection,0); BAD(state_protection,3); BAD(owner,0); BAD(operation_mask,1);
    BAD(qk_profile,0); BAD(pv_profile,0); BAD(nr_lanes,2); BAD(vlen_bits,512);
    BAD(legacy_operations,8); BAD(whole_process_ram,2);
#undef BAD
    for (unsigned i=0; i<32; ++i) { reset(); ctx.observation.contract_sha256[i]^=1; no_provider(); }
    reset(); ctx.observe_ok=0; no_provider();
    reset(); ctx.poison_observation=1; no_provider();
    reset(); ctx.observation.state_protection=ARA_RESIDENT_NONPREEMPTIBLE_FIRMWARE;
    CHECK(akv_resident_platform_current_v1() == &binding.resident && !ctx.csr_reads);
}

static void csr_guards(void) {
    reset(); const akv_resident_platform_provider_v1 *p=akv_resident_platform_current_v1();
    CHECK(p == &binding.resident && !ctx.csr_reads);
    ctx.observe_ok=0;
    CHECK(ggml_akv_platform_entry_v1(p) == AKV_PLATFORM_KEEP_NATIVE && !ctx.csr_reads);
    ctx.observe_ok=1; ctx.csr.vstart=1;
    CHECK(ggml_akv_platform_entry_v1(p) == AKV_PLATFORM_BAD_VSTART);
    CHECK(akv_resident_platform_admit_v1(p,(void *)1,(void *)1) == AKV_PLATFORM_BAD_VSTART);
    CHECK(!ctx.acquires);
    for (unsigned i=0; i<3; ++i) {
        reset(); if (i==0) ctx.csr.vlenb=64;
        if (i==1) ctx.csr.fcsr=32;
        if (i==2) ctx.csr.vcsr=8;
        CHECK(akv_resident_platform_admit_v1(p,(void *)1,(void *)1) == AKV_PLATFORM_KEEP_NATIVE);
        CHECK(!ctx.acquires);
    }
}

static void lease_rejections(void) {
    akv_platform_session_v1 s={0};
#define BAD(field, x) do { reset(); akv_platform_request_v1 r=request(); r.field=(x); \
    CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_KEEP_NATIVE); \
    CHECK(!s.cookie && !ctx.acquires); } while (0)
    BAD(requested,0); BAD(workers,2); BAD(query_tokens,2); BAD(groups,0);
    BAD(decode_head_rows,0); BAD(refill_overlap,1); BAD(spans,NULL); BAD(span_count,0); BAD(span_count,33);
#undef BAD
    reset(); akv_platform_request_v1 r=request(); ctx.allowed=0;
    CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_KEEP_NATIVE);
    CHECK(!s.cookie && !ctx.owned && ctx.acquires==1 && !ctx.releases);
    reset(); ctx.hole=(uintptr_t)key+4096;
    CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_KEEP_NATIVE);
    CHECK(!s.cookie && !ctx.owned && !ctx.releases);
    reset(); ctx.rotate_owner=1;
    CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_KEEP_NATIVE && !s.cookie);
    for (unsigned i=0; i<4; ++i) {
        reset(); akv_platform_span_v1 changed[6]; memcpy(changed,spans,sizeof(changed)); r=request(); r.spans=changed;
        if (i==0) changed[0].base=NULL;
        if (i==1) changed[0].bytes=0;
        if (i==2) { changed[0].base=(void *)(UINTPTR_MAX-1); changed[0].bytes=4; }
        if (i==3) changed[0].writable=2;
        CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_KEEP_NATIVE);
        CHECK(!ctx.acquires && !s.cookie);
    }
    for (unsigned mutation=1; mutation<=2; ++mutation) {
        reset(); r=request(); ctx.mutate_csr=mutation;
        CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==
              (mutation==1 ? AKV_PLATFORM_INVALID : AKV_PLATFORM_BAD_VSTART));
        CHECK(ctx.releases==1 && !ctx.owned && !s.cookie);
    }
}

static void legacy_independence(void) {
    reset(); CHECK(ggml_akv_legacy_permitted_v1(&binding.resident,7));
#define BAD(field, x) do { reset(); binding.legacy.field=(x); \
    CHECK(akv_resident_platform_current_v1()==&binding.resident); \
    CHECK(!ggml_akv_legacy_current_v1() && !ggml_akv_legacy_permitted_v1(&binding.resident,1)); } while (0)
    BAD(abi_version,0); BAD(struct_bytes,0); BAD(provider,NULL); BAD(operation_mask,0);
    BAD(operation_mask,8); BAD(whole_process_ram,0);
#undef BAD
    reset(); binding.legacy.contract_sha256[31]^=1;
    CHECK(!ggml_akv_legacy_current_v1());
    reset(); ctx.observation.whole_process_ram=0;
    CHECK(akv_resident_platform_current_v1()==&binding.resident && !ggml_akv_legacy_current_v1());
    reset(); ctx.observation.legacy_operations=0; CHECK(!ggml_akv_legacy_current_v1());
    reset(); binding.legacy.operation_mask=ctx.observation.legacy_operations=1;
    CHECK(ggml_akv_legacy_permitted_v1(&binding.resident,1));
    CHECK(!ggml_akv_legacy_permitted_v1(&binding.resident,2));
    CHECK(!ggml_akv_legacy_permitted_v1(&binding.resident,4));
    reset(); akv_platform_request_v1 r=request(); r.decode_head_rows=0; r.query_tokens=4;
    akv_platform_session_v1 s={0};
    CHECK(ggml_akv_legacy_admit_v1(&binding.resident,&r,&s,7)==AKV_PLATFORM_READY);
    CHECK(s.started==1 && s.cookie && ctx.owned);
    akv_resident_platform_finish_v1(&s);
    CHECK(!s.cookie && !ctx.owned && ctx.releases==1);
}

static void routes_and_cleanup(void) {
    const unsigned dimensions[]={64,96,128}, heads[]={1,2,8}, tokens[]={1,65,137};
    for (unsigned di=0; di<3; ++di) for (unsigned hi=0; hi<3; ++hi) for (unsigned ti=0; ti<3; ++ti) {
        reset(); akv_device_t device; akv_attention_plan_t plan;
        CHECK(akv_device_init_reference(&device)==AKV_STATUS_OK);
        const akv_attention_problem_t problem={&query[0][0],&key[0][0],&value[0][0],mask,&output[0][0],
            512,512,512,1024,heads[hi],dimensions[di],tokens[ti],0.125f};
        CHECK(akv_attention_plan_create_v2(&device,&problem,&plan)==AKV_STATUS_OK);
        akv_platform_request_v1 r=request(); akv_platform_session_v1 s={0}, nested={0};
        CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_READY);
        CHECK(akv_resident_platform_admit_v1(&binding.resident,&r,&nested)==AKV_PLATFORM_KEEP_NATIVE);
        CHECK(!nested.cookie && ctx.owned && !ctx.releases);
        CHECK(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_INVALID);
        akv_resident_attention_options_t options={0};
        const akv_attention_features_t features={.sinks_enabled=1};
        CHECK(akv_resident_platform_group_v1(&s,0,&device,&plan,&features,&options)==AKV_PLATFORM_KEEP_NATIVE);
        CHECK(!s.prepared && !options.validated_available);
        for (unsigned group=0; group<2; ++group) {
            CHECK(akv_resident_platform_group_v1(&s,group,&device,&plan,NULL,&options)==AKV_PLATFORM_READY);
            CHECK(akv_resident_attention_select(&device,&plan,&options,0)==AKV_RESIDENT_USE_SHARED);
        }
        CHECK(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_READY);
        CHECK(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_NO_RETRY);
        CHECK(akv_resident_platform_group_v1(&s,2,(void *)1,(void *)1,(void *)1,(void *)1)==AKV_PLATFORM_NO_RETRY);
        ctx.observe_ok=0; ctx.csr.vstart=1;
        unsigned reads=ctx.csr_reads;
        akv_resident_platform_finish_v1(&s); akv_resident_platform_finish_v1(&s);
        CHECK(ctx.csr_reads==reads && !s.cookie && !ctx.owned && ctx.releases==1);
        CHECK(ctx.csr.vstart==1 && ctx.csr.fcsr==17 && ctx.csr.vcsr==5);
        const unsigned char *p=(const unsigned char *)output;
        for (size_t i=0; i<sizeof(output); ++i) assert(p[i]==0xa5);
        for (size_t i=0; i<sizeof(scratch); ++i) assert(scratch[i]==0x5a);
    }
    CHECK(akv_resident_qk_capability_word(4,1)==0 && akv_resident_pv_capability_word(4,1)==0);
}

static void fatal_case(unsigned which) {
    reset(); akv_platform_request_v1 r=request(); akv_platform_session_v1 s={0};
    if (which==0) { ctx.csr.vstart=1; binding.resident.acquire(binding.resident.context,(void *)1); }
    if (which==1 || which==2) {
        ctx.mutate_csr=which; ctx.deny_after_mutation=1;
        akv_resident_platform_admit_v1(&binding.resident,&r,&s);
    }
    if (which>=3) {
        assert(akv_resident_platform_admit_v1(&binding.resident,&r,&s)==AKV_PLATFORM_READY);
        if (which==3) binding.resident.release(binding.resident.context,s.cookie+1);
        if (which==4) { ++ctx.observation.owner; akv_resident_platform_finish_v1(&s); }
        if (which==5) binding.resident.release(binding.resident.context,0);
    }
    _exit(99);
}

static void fatal_not_fallback(void) {
    for (unsigned i=0; i<6; ++i) {
        const pid_t child=fork(); CHECK(child>=0);
        if (!child) fatal_case(i);
        int status; CHECK(waitpid(child,&status,0)==child);
        CHECK(WIFSIGNALED(status) && (WTERMSIG(status)==SIGILL || WTERMSIG(status)==SIGTRAP));
    }
}

int main(void) {
    binding_rejections(); observation_rejections(); csr_guards(); lease_rejections();
    legacy_independence(); routes_and_cleanup(); fatal_not_fallback();
    printf("RESIDENT_DEPLOYMENT_HOST_PASS checks=%u native_execution=0 board_acceptance=0\n",checks);
    return 0;
}
