#include "resident_deployment.h"

#ifndef ARA_RESIDENT_LINKED_BINDING
__attribute__((weak))
const ara_resident_deployment_v1 *ara_resident_deployment_current_v1(void) {
    return NULL;
}
#endif

static int digest_equal(const uint8_t *a, const uint8_t *b) {
    unsigned different = 0, nonzero = 0;
    const volatile uint8_t *left = a, *right = b;
    for (size_t i = 0; i < 32; ++i) {
        different |= left[i] ^ right[i];
        nonzero |= left[i];
    }
    return !different && nonzero;
}

static int binding_valid(const ara_resident_deployment_v1 *d) {
    if (!d || d->abi_version != 1 || d->struct_bytes != sizeof(*d) ||
        !d->observe || !d->acquire || !d->release) return 0;
    const akv_resident_platform_provider_v1 *p = &d->resident;
    return p->abi_version == 1 && p->struct_bytes == sizeof(*p) &&
        p->kind == AKV_PLATFORM_EXTERNAL_DEPLOYMENT &&
        p->assurances == AKV_PLATFORM_REQUIRED_ASSURANCES &&
        p->operation_mask == AKV_PLATFORM_QK_PV_V1 && p->qk_profile == 1 &&
        p->pv_profile == 1 && p->nr_lanes == 4 && p->vlen_bits == 1024 &&
        p->context == d && p->read_state == ara_resident_deployment_read_state_v1 &&
        p->acquire == ara_resident_deployment_acquire_v1 &&
        p->release == ara_resident_deployment_release_v1 &&
        digest_equal(p->contract_sha256, p->contract_sha256);
}

static int observation(const ara_resident_deployment_v1 *d, ara_resident_observation_v1 *o) {
    if (!binding_valid(d)) return 0;
    /* Zero output prevents an incomplete callback from authorizing stale data. */
    volatile unsigned char *bytes = (volatile unsigned char *)o;
    for (size_t i = 0; i < sizeof(*o); ++i) bytes[i] = 0;
    return d->observe(d->authority, o) == 1 && o->abi_version == 1 &&
        o->struct_bytes == sizeof(*o) && o->owner && o->guarantees == ARA_RESIDENT_REQUIRED &&
        (o->state_protection == ARA_RESIDENT_KERNEL_CONTEXT ||
         o->state_protection == ARA_RESIDENT_NONPREEMPTIBLE_FIRMWARE) &&
        digest_equal(d->resident.contract_sha256, o->contract_sha256) &&
        o->operation_mask == AKV_PLATFORM_QK_PV_V1 && o->qk_profile == 1 &&
        o->pv_profile == 1 && o->nr_lanes == 4 && o->vlen_bits == 1024 &&
        !(o->legacy_operations & ~7u) && o->whole_process_ram <= 1;
}

akv_platform_result_t ara_resident_deployment_read_state_v1(
    void *context, akv_platform_thread_state_v1 *out) {
    const ara_resident_deployment_v1 *d = context;
    ara_resident_observation_v1 o;
    if (!observation(d, &o)) return AKV_PLATFORM_KEEP_NATIVE;
    if (!out) return AKV_PLATFORM_INVALID;
    return akv_resident_platform_read_state_v1(NULL, out);
}

static int request_valid(const akv_platform_request_v1 *r) {
    if (!r || r->abi_version != 1 || r->struct_bytes != sizeof(*r) ||
        r->requested != 1 || r->workers != 1 || !r->query_tokens || !r->groups ||
        r->decode_head_rows > 1 || r->refill_overlap || !r->spans ||
        !r->span_count || r->span_count > 32) return 0;
    for (size_t i = 0; i < r->span_count; ++i) {
        const akv_platform_span_v1 *s = r->spans + i;
        const uintptr_t base = (uintptr_t)s->base;
        if (!base || !s->bytes || s->bytes > UINTPTR_MAX - base || s->writable > 1) return 0;
    }
    return 1;
}

uintptr_t ara_resident_deployment_acquire_v1(void *context, const akv_platform_request_v1 *r) {
    const ara_resident_deployment_v1 *d = context;
    ara_resident_observation_v1 o;
    if (!observation(d, &o)) return 0;
    akv_platform_thread_state_v1 state;
    const akv_platform_result_t result = akv_resident_platform_read_state_v1(NULL, &state);
    /* The cookie-only ABI cannot return BAD_VSTART. Never turn it into fallback. */
    if (result == AKV_PLATFORM_BAD_VSTART || (result == AKV_PLATFORM_READY && state.vstart)) __builtin_trap();
    if (result != AKV_PLATFORM_READY || state.vlenb != 128 || state.fcsr >> 5 || state.vcsr > 7 ||
        !request_valid(r)) return 0;
    const uintptr_t cookie = d->acquire(d->authority, o.owner, r);
    if (!cookie) {
        akv_platform_thread_state_v1 after;
        if (ara_resident_deployment_read_state_v1(context, &after) != AKV_PLATFORM_READY ||
            after.vlenb != state.vlenb || after.vstart != state.vstart ||
            after.fcsr != state.fcsr || after.vcsr != state.vcsr) __builtin_trap();
    }
    return cookie;
}

void ara_resident_deployment_release_v1(void *context, uintptr_t cookie) {
    const ara_resident_deployment_v1 *d = context;
    if (!binding_valid(d) || !cookie) __builtin_trap();
    /* Revocation or bad VSTART must not bypass cleanup or enter the OS. */
    d->release(d->authority, cookie);
}

const akv_resident_platform_provider_v1 *akv_resident_platform_current_v1(void) {
    const ara_resident_deployment_v1 *d = ara_resident_deployment_current_v1();
    ara_resident_observation_v1 o;
    return observation(d, &o) ? &d->resident : NULL;
}

const ggml_akv_legacy_contract_v1 *ggml_akv_legacy_current_v1(void) {
    const ara_resident_deployment_v1 *d = ara_resident_deployment_current_v1();
    ara_resident_observation_v1 o;
    if (!observation(d, &o)) return NULL;
    const ggml_akv_legacy_contract_v1 *c = &d->legacy;
    if (c->abi_version != 1 || c->struct_bytes != sizeof(*c) || c->provider != &d->resident ||
        !c->operation_mask || c->operation_mask & ~7u || c->whole_process_ram != 1 ||
        (o.legacy_operations & c->operation_mask) != c->operation_mask || o.whole_process_ram != 1 ||
        !digest_equal(d->resident.contract_sha256, c->contract_sha256)) return NULL;
    return c;
}
