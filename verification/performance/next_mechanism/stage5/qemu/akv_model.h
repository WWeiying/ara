#ifndef STAGE5_AKV_MODEL_H
#define STAGE5_AKV_MODEL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AKV_MODEL_VLEN_BYTES 128u
#define AKV_MODEL_MAX_Q 8u
#define AKV_MODEL_MAX_D 128u
#define AKV_MODEL_MAX_T 64u

typedef enum {
    AKV_MODEL_OK = 0,
    AKV_MODEL_ILLEGAL = 1,
    AKV_MODEL_ACCESS = 2
} akv_model_status;

typedef struct {
    uint64_t vl, vtype, vstart;
    unsigned frm;
    bool fs_enabled, vs_enabled;
} akv_model_csr;

/* One instance belongs to one hart. Never share it across CPU instances. */
typedef struct {
    bool valid, v2;
    unsigned q_rows, dimension, tokens, kv_length;
    uint64_t tile_start, q_base, k_base, v_base;
    uint32_t q_stride, k_stride, v_stride;
    uint16_t q[AKV_MODEL_MAX_Q][AKV_MODEL_MAX_D];
    uint16_t k[AKV_MODEL_MAX_T][AKV_MODEL_MAX_D];
    uint16_t v[AKV_MODEL_MAX_T][AKV_MODEL_MAX_D];
} akv_model;

typedef struct {
    void *opaque;
    /* RAM-only, read-side admission; callbacks may also raise a guest trap.
     * FULL/REFILL invalidate the context BEFORE either callback is invoked. */
    bool (*ram_probe)(void *, uint64_t address, size_t bytes);
    bool (*ram_read)(void *, uint64_t address, void *destination, size_t bytes);
    /* Offsets are logical architectural bytes in one 128-byte vector register,
     * not physical Ara lane/EEW-shuffled bytes. Read/probe have no side effects.
     * write is infallible after successful probes; callbacks must not modify
     * guest CSRs. The adapter owns VS dirty marking on successful execution. */
    bool (*vrf_probe)(void *, unsigned reg, size_t offset, size_t bytes, bool write);
    bool (*vrf_read)(void *, unsigned reg, size_t offset, void *destination, size_t bytes);
    void (*vrf_write)(void *, unsigned reg, size_t offset, const void *source, size_t bytes);
    /* Ordered fused operations. OR newly raised RISC-V flags into *flags;
     * do not inherit or clear guest sticky flags. rm is resolved 0..4. */
    uint16_t (*fma_h)(void *, uint16_t a, uint16_t b, uint16_t c,
                      unsigned rm, uint8_t *flags);
    uint32_t (*fma_s)(void *, uint32_t a, uint32_t b, uint32_t c,
                      unsigned rm, uint8_t *flags);
} akv_model_callbacks;

typedef struct {
    akv_model_status status;
    /* fault_addr is architectural tval: insn for frontend ILLEGAL, zero for
     * admitted backend validation, or guest range address for ACCESS. A RAM
     * callback that raises directly owns its more precise guest fault address. */
    uint64_t scalar, fault_addr;
    uint8_t fflags;
    bool writes_scalar, writes_vrf;
} akv_model_result;

typedef struct {
    unsigned tokens, heads, dimension, query_base, vd, vs2;
    bool qk;
} akv_model_resident;

void akv_model_reset(akv_model *model);
/* Strict advertised subset: F16 v1/v2, D64/96/128, no D256; index 4 is zero. */
uint64_t akv_model_info(uint64_t index);
akv_model_result akv_model_execute(akv_model *model, uint32_t insn,
    uint64_t rs1, uint64_t rs2, const akv_model_csr *csr,
    const akv_model_callbacks *callbacks);
/* Resident validation and accessors do not change context or architectural state. */
akv_model_status akv_model_validate_resident(const akv_model *model,
    uint32_t insn, uint64_t control, const akv_model_csr *csr,
    akv_model_resident *command);
bool akv_model_q(const akv_model *, unsigned row, unsigned dimension, uint16_t *bits);
bool akv_model_k(const akv_model *, unsigned token, unsigned dimension, uint16_t *bits);
bool akv_model_v(const akv_model *, unsigned token, unsigned dimension, uint16_t *bits);
/* Exact widening, including sNaN payload/sign: no quieting or FP exceptions. */
uint32_t akv_model_f16_to_f32(uint16_t bits);

#endif
