#ifndef ARA_LLAMA_RESIDENT_DEPLOYMENT_V1_H
#define ARA_LLAMA_RESIDENT_DEPLOYMENT_V1_H

#include "entry.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    ARA_RESIDENT_IMAGE_ISA_BOUND = 1u << 0,
    ARA_RESIDENT_SAFE_USER_CSR = 1u << 1,
    ARA_RESIDENT_COMPOSED_VALIDATED = 1u << 2,
    ARA_RESIDENT_MEMORY_LEASE = 1u << 3,
    ARA_RESIDENT_EXCLUSIVE_LEASE = 1u << 4,
    ARA_RESIDENT_WORKER_BOUND = 1u << 5,
    ARA_RESIDENT_CONTEXT_PROTECTED = 1u << 6,
    ARA_RESIDENT_FAULT_LIFETIME_SAFE = 1u << 7,
    ARA_RESIDENT_REQUIRED = (1u << 8) - 1
};
enum {
    ARA_RESIDENT_KERNEL_CONTEXT = 1,
    ARA_RESIDENT_NONPREEMPTIBLE_FIRMWARE = 2
};

typedef struct {
    unsigned abi_version, struct_bytes;
    uint8_t contract_sha256[32];
    unsigned guarantees, state_protection;
    unsigned operation_mask, qk_profile, pv_profile, nr_lanes, vlen_bits;
    unsigned legacy_operations, whole_process_ram;
    uintptr_t owner;
} ara_resident_observation_v1;

typedef struct {
    unsigned abi_version, struct_bytes;
    akv_resident_platform_provider_v1 resident;
    ggml_akv_legacy_contract_v1 legacy;
    void *authority;
    /* Scalar-safe; recheck current image/OS/process/thread. A reviewed kernel
     * entry may establish CSR access safety only with proven exact preservation
     * of FCSR/VCSR/VSTART (including nonzero VSTART), private state and any lease
     * on both allow and deny. Before safety is proven, do not read/write/probe
     * user CSRs. No unaudited libc/syscall path or user FP/vector/custom work.
     * owner must distinguish fork, exec, thread replacement and policy epochs. */
    int (*observe)(void *, ara_resident_observation_v1 *);
    /* Atomically revalidate owner and ALL spans, permissions, reachability,
     * coherency and lifetime. Enforce exclusivity through SDK RELEASE, including
     * traps, signals, preemption, migration, faults and other accelerator users.
     * Failure retains no lease. Preserve FCSR/VCSR/VSTART on both outcomes. */
    uintptr_t (*acquire)(void *, uintptr_t owner, const akv_platform_request_v1 *);
    /* Validate cookie/owner and clean up reliably even after BAD_VSTART.
     * A reviewed kernel entry is permitted only with proven CSR/private-context
     * preservation and lease protection through release. Preserve the exact
     * entry FCSR/VCSR/VSTART, including nonzero VSTART; scalar restoration is
     * permitted. No user FP/vector/custom computation, invalid-state clearing,
     * or computation retry. Fail fatally if cleanup cannot be guaranteed. */
    void (*release)(void *, uintptr_t cookie);
} ara_resident_deployment_v1;

/* Trusted, immutable, explicitly linked code only. Default returns NULL.
 * No runtime registration, environment authority or application credentials. */
const ara_resident_deployment_v1 *ara_resident_deployment_current_v1(void);

akv_platform_result_t ara_resident_deployment_read_state_v1(void *, akv_platform_thread_state_v1 *);
uintptr_t ara_resident_deployment_acquire_v1(void *, const akv_platform_request_v1 *);
void ara_resident_deployment_release_v1(void *, uintptr_t);

/* The remaining binding fields and independent legacy contract are explicit.
 * HASH is a macro expanding to the 32 reviewed contract digest bytes. */
#define ARA_RESIDENT_PROVIDER_V1(BINDING, HASH) { \
    .abi_version = 1, .struct_bytes = sizeof(akv_resident_platform_provider_v1), \
    .kind = AKV_PLATFORM_EXTERNAL_DEPLOYMENT, .assurances = AKV_PLATFORM_REQUIRED_ASSURANCES, \
    .contract_sha256 = { HASH }, .operation_mask = AKV_PLATFORM_QK_PV_V1, \
    .qk_profile = 1, .pv_profile = 1, .nr_lanes = 4, .vlen_bits = 1024, \
    .context = (void *)&(BINDING), .read_state = ara_resident_deployment_read_state_v1, \
    .acquire = ara_resident_deployment_acquire_v1, .release = ara_resident_deployment_release_v1 \
}

#ifdef __cplusplus
}
#endif
#endif
