/* SPDX-License-Identifier: GPL-2.0-or-later */
/* QEMU glue only. akv_model.c owns the instruction/state/element-order contract. */
#include "qemu/osdep.h"
#include "cpu.h"
#include "internals.h"
#include "vector_internals.h"
#include "accel/tcg/cpu-ldst.h"
#include "accel/tcg/probe.h"
#include "exec/helper-proto.h"
#include "exec/target_page.h"
#include "exec/tlb-flags.h"
#include "fpu/softfloat.h"
#include "trace.h"
#include "akv_model.h"

typedef struct {
    CPURISCVState *env;
    uintptr_t retaddr;
    target_ulong pc;
    uint64_t sequence;
} AkvQemuCall;

static G_NORETURN void akv_raise_illegal(AkvQemuCall *call, uint32_t tval)
{
    call->env->bins = tval;
    riscv_raise_exception(call->env, RISCV_EXCP_ILLEGAL_INST, call->retaddr);
}

static G_NORETURN void akv_raise_access(AkvQemuCall *call, uint64_t address,
                                      size_t bytes)
{
    CPUState *cs = env_cpu(call->env);

    riscv_cpu_do_transaction_failed(cs, 0, address,
        MIN(bytes, (size_t)UINT_MAX), MMU_DATA_LOAD, cpu_mmu_index(cs, false),
        MEMTXATTRS_UNSPECIFIED, MEMTX_ERROR, call->retaddr);
    g_assert_not_reached();
}

static bool akv_ram_probe(void *opaque, uint64_t address, size_t bytes)
{
    AkvQemuCall *call = opaque;
    CPURISCVState *env = call->env;
    int mmu_index = cpu_mmu_index(env_cpu(env), false);

    if (bytes && (uint64_t)(bytes - 1) > UINT64_MAX - address) {
        akv_raise_access(call, address, bytes);
    }
    while (bytes) {
        target_ulong adjusted = adjust_addr(env, address);
        size_t chunk = MIN(bytes, (size_t)-(adjusted | TARGET_PAGE_MASK));
        void *host = NULL;
        int flags = probe_access_flags(env, adjusted, chunk, MMU_DATA_LOAD,
                                       mmu_index, false, &host, call->retaddr);
        /* Never invoke MMIO/ROM callbacks for descriptor or payload reads. */
        if ((flags & TLB_MMIO) || !host) {
            akv_raise_access(call, address, chunk);
        }
        address += chunk;
        bytes -= chunk;
    }
    return true;
}

static bool akv_ram_read(void *opaque, uint64_t address, void *destination,
                         size_t bytes)
{
    AkvQemuCall *call = opaque;
    CPURISCVState *env = call->env;
    int mmu_index = cpu_mmu_index(env_cpu(env), false);
    uint8_t *out = destination;

    /* Recheck each copy; a callback must never become an MMIO read fallback. */
    akv_ram_probe(opaque, address, bytes);
    trace_akv_arch_read(call->sequence, call->pc, address, bytes);
    while (bytes) {
        target_ulong adjusted = adjust_addr(env, address);
        size_t chunk = MIN(bytes, (size_t)-(adjusted | TARGET_PAGE_MASK));
        void *host = probe_read(env, adjusted, chunk, mmu_index, call->retaddr);
        g_assert(host != NULL);
        memcpy(out, host, chunk);
        address += chunk;
        out += chunk;
        bytes -= chunk;
    }
    return true;
}

static bool akv_vrf_probe(void *opaque, unsigned reg, size_t offset,
                          size_t bytes, bool write)
{
    AkvQemuCall *call = opaque;
    (void)write;
    return riscv_cpu_cfg(call->env)->vlenb == AKV_MODEL_VLEN_BYTES &&
           reg < 32 && offset <= AKV_MODEL_VLEN_BYTES &&
           bytes <= AKV_MODEL_VLEN_BYTES - offset;
}

static bool akv_vrf_read(void *opaque, unsigned reg, size_t offset,
                         void *destination, size_t bytes)
{
    AkvQemuCall *call = opaque;
    if (!akv_vrf_probe(opaque, reg, offset, bytes, false)) {
        return false;
    }
    memcpy(destination, (uint8_t *)call->env->vreg +
           reg * AKV_MODEL_VLEN_BYTES + offset, bytes);
    return true;
}

static void akv_vrf_write(void *opaque, unsigned reg, size_t offset,
                          const void *source, size_t bytes)
{
    AkvQemuCall *call = opaque;
    g_assert(akv_vrf_probe(opaque, reg, offset, bytes, true));
    memcpy((uint8_t *)call->env->vreg + reg * AKV_MODEL_VLEN_BYTES + offset,
           source, bytes);
}

static float_status akv_float_status(AkvQemuCall *call, unsigned rm)
{
    static const int rounding[] = {
        float_round_nearest_even, float_round_to_zero, float_round_down,
        float_round_up, float_round_ties_away,
    };
    float_status status = call->env->fp_status;
    g_assert(rm < ARRAY_SIZE(rounding));
    set_float_rounding_mode(rounding[rm], &status);
    set_float_exception_flags(0, &status);
    return status;
}

static uint8_t akv_float_flags(const float_status *status)
{
    int flags = get_float_exception_flags(status);
    return ((flags & float_flag_inexact) ? 1 : 0) |
           ((flags & float_flag_underflow) ? 2 : 0) |
           ((flags & float_flag_overflow) ? 4 : 0) |
           ((flags & float_flag_divbyzero) ? 8 : 0) |
           ((flags & float_flag_invalid) ? 16 : 0);
}

static uint16_t akv_fma_h(void *opaque, uint16_t a, uint16_t b, uint16_t c,
                          unsigned rm, uint8_t *flags)
{
    float_status status = akv_float_status(opaque, rm);
    float16 result = float16_muladd(make_float16(a), make_float16(b),
                                   make_float16(c), 0, &status);
    *flags |= akv_float_flags(&status);
    return float16_val(result);
}

static uint32_t akv_fma_s(void *opaque, uint32_t a, uint32_t b, uint32_t c,
                          unsigned rm, uint8_t *flags)
{
    float_status status = akv_float_status(opaque, rm);
    float32 result = float32_muladd(make_float32(a), make_float32(b),
                                   make_float32(c), 0, &status);
    *flags |= akv_float_flags(&status);
    return float32_val(result);
}

target_ulong helper_akv_info(CPURISCVState *env, target_ulong index)
{
    uint64_t result = 0;
#if !HOST_BIG_ENDIAN
    if (riscv_cpu_cfg(env)->vlenb == AKV_MODEL_VLEN_BYTES &&
        riscv_cpu_cfg(env)->ext_zve32f) {
        result = akv_model_info(index);
    }
#endif
    trace_akv_arch_info(index, result);
    return result;
}

void helper_akv_exec(CPURISCVState *env, target_ulong rs1, target_ulong rs2,
                     uint32_t insn, target_ulong pc)
{
    AkvQemuCall call = {
        .env = env, .retaddr = GETPC(), .pc = pc,
        .sequence = ++env->akv_sequence,
    };
    unsigned funct3 = (insn >> 12) & 7;
    unsigned funct7 = insn >> 25;
    bool resident = funct3 == 7 && (funct7 == 2 || funct7 == 3);
    akv_model_csr csr = {
        .vl = env->vl, .vtype = env->vtype, .vstart = env->vstart,
        .frm = env->frm, .fs_enabled = (env->mstatus & MSTATUS_FS) != 0,
        .vs_enabled = (env->mstatus & MSTATUS_VS) != 0,
    };
    const akv_model_callbacks callbacks = {
        .opaque = &call, .ram_probe = akv_ram_probe, .ram_read = akv_ram_read,
        .vrf_probe = akv_vrf_probe, .vrf_read = akv_vrf_read,
        .vrf_write = akv_vrf_write, .fma_h = akv_fma_h, .fma_s = akv_fma_s,
    };
    akv_model_result result;

    trace_akv_arch_begin(call.sequence, pc, insn, rs1, rs2, env->frm,
                         riscv_cpu_get_fflags(env));
    if (HOST_BIG_ENDIAN || riscv_cpu_cfg(env)->vlenb != AKV_MODEL_VLEN_BYTES ||
        !riscv_cpu_cfg(env)->ext_Xaraakv ||
        (resident && !riscv_cpu_cfg(env)->ext_XaraakvResident)) {
        akv_raise_illegal(&call, insn);
    }
    result = akv_model_execute(&env->akv_context, insn, rs1, rs2,
                               &csr, &callbacks);
    trace_akv_arch_end(call.sequence, pc, result.status, result.fflags,
                       env->akv_context.valid, env->akv_context.tile_start,
                       env->akv_context.tokens, result.fault_addr);
    if (result.status == AKV_MODEL_ILLEGAL) {
        akv_raise_illegal(&call, result.fault_addr);
    }
    if (result.status == AKV_MODEL_ACCESS) {
        akv_raise_access(&call, result.fault_addr, 1);
    }
    g_assert(result.status == AKV_MODEL_OK && !result.writes_scalar);
    /* Ordinary RVV and PV_PREP still execute in QEMU, outside this helper. */
    riscv_cpu_set_fflags(env, riscv_cpu_get_fflags(env) | result.fflags);
    env->vstart = 0;
}
