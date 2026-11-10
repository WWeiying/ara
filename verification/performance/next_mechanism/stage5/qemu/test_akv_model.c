#include "akv_model.h"
#include "akv/akv_abi.h"

#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#define MEMORY_SIZE 131072u
#define DESCRIPTOR 256u
#define QUERY 4096u
#define KEY 16384u
#define VALUE 65536u

typedef struct {
    uint8_t memory[MEMORY_SIZE], vrf[32][128];
    akv_model *model;
    uint64_t bad;
    unsigned probes, reads, writes, q_reads, fma_h_calls, fma_s_calls, rm;
    int deny_reg;
    bool poison_expected, jump;
    jmp_buf escape;
} fixture;

static fixture f;
static akv_model model, other;
static akv_model_csr csr;
static akv_model_callbacks cb;
static unsigned cases;

static void store16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
}

static uint16_t load16(const uint8_t *p)
{
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8);
}

static void store32(uint8_t *p, uint32_t v)
{
    store16(p, (uint16_t)v); store16(p + 2, (uint16_t)(v >> 16));
}

static uint32_t load32(const uint8_t *p)
{
    return (uint32_t)load16(p) | (uint32_t)load16(p + 2) << 16;
}

static void store64(uint8_t *p, uint64_t v)
{
    store32(p, (uint32_t)v); store32(p + 4, (uint32_t)(v >> 32));
}

static bool ram_probe(void *opaque, uint64_t address, size_t bytes)
{
    fixture *s = opaque;
    ++s->probes;
    if (s->poison_expected) CHECK(!s->model->valid);
    if (s->jump && address == s->bad) longjmp(s->escape, 1);
    return address < MEMORY_SIZE && bytes <= MEMORY_SIZE - address && address != s->bad;
}

static bool ram_read(void *opaque, uint64_t address, void *to, size_t bytes)
{
    fixture *s = opaque;
    CHECK(address < MEMORY_SIZE && bytes <= MEMORY_SIZE - address);
    ++s->reads;
    if (address >= QUERY && address < QUERY + 2048) ++s->q_reads;
    if (s->poison_expected) CHECK(!s->model->valid);
    memcpy(to, s->memory + address, bytes);
    return true;
}

static bool vrf_probe(void *opaque, unsigned reg, size_t offset, size_t bytes, bool write)
{
    fixture *s = opaque;
    (void)write;
    CHECK(reg < 32 && offset <= 128 && bytes <= 128 - offset);
    return (int)reg != s->deny_reg;
}

static bool vrf_read(void *opaque, unsigned reg, size_t offset, void *to, size_t bytes)
{
    fixture *s = opaque;
    CHECK(reg < 32 && offset + bytes <= 128);
    memcpy(to, s->vrf[reg] + offset, bytes);
    return true;
}

static void vrf_write(void *opaque, unsigned reg, size_t offset, const void *from, size_t bytes)
{
    fixture *s = opaque;
    CHECK(reg < 32 && offset + bytes <= 128);
    memcpy(s->vrf[reg] + offset, from, bytes);
    ++s->writes;
}

/* Deliberately non-FP primitives test operand mapping/order, not arithmetic.
 * Actual numerical/rounding/NaN acceptance belongs to the QEMU SoftFloat gate. */
static uint16_t toy_h(uint16_t a, uint16_t b, uint16_t c)
{
    return (uint16_t)(17u * c + 3u * a + 5u * b);
}

static uint32_t toy_s(uint32_t a, uint32_t b, uint32_t c)
{
    return 31u * c + a + 3u * b;
}

static uint16_t fma_h(void *opaque, uint16_t a, uint16_t b, uint16_t c,
                      unsigned rm, uint8_t *flags)
{
    fixture *s = opaque;
    CHECK(rm == s->rm && !s->writes);
    ++s->fma_h_calls; *flags |= 1;
    return toy_h(a, b, c);
}

static uint32_t fma_s(void *opaque, uint32_t a, uint32_t b, uint32_t c,
                      unsigned rm, uint8_t *flags)
{
    fixture *s = opaque;
    CHECK(rm == s->rm && !s->writes);
    ++s->fma_s_calls; *flags |= 16;
    return toy_s(a, b, c);
}

static uint32_t insn(unsigned f3, unsigned f7, unsigned rd, unsigned s1, unsigned s2)
{
    return akv_encode_r(f3, f7, rd, s1, s2);
}

static akv_model_result execute(uint32_t instruction, uint64_t s1, uint64_t s2)
{
    akv_model_csr before = csr;
    akv_model_result r = akv_model_execute(&model, instruction, s1, s2, &csr, &cb);
    CHECK(memcmp(&before, &csr, sizeof(csr)) == 0);
    return r;
}

static void setup(unsigned dim, unsigned length, unsigned rows)
{
    memset(&f, 0, sizeof(f));
    f.model = &model; f.bad = UINT64_MAX; f.deny_reg = -1; f.poison_expected = true;
    memset(f.vrf, 0xa5, sizeof(f.vrf));
    akv_model_reset(&model);
    csr = (akv_model_csr){.vl = 0, .vtype = UINT64_C(1) << 63,
                         .frm = 0, .fs_enabled = true, .vs_enabled = true};
    cb = (akv_model_callbacks){&f, ram_probe, ram_read, vrf_probe, vrf_read, vrf_write, fma_h, fma_s};
    uint8_t *d = f.memory + DESCRIPTOR;
    d[0] = 1; d[1] = 1; d[2] = (uint8_t)rows;
    store16(d + 4, (uint16_t)dim); store16(d + 6, (uint16_t)length);
    store32(d + 8, 256); store32(d + 12, 256); store32(d + 16, 256);
    store64(d + 24, QUERY); store64(d + 32, KEY); store64(d + 40, VALUE);
    for (unsigned h = 0; h < rows; ++h)
        for (unsigned x = 0; x < dim; ++x)
            store16(f.memory + QUERY + h * 256 + 2 * x, (uint16_t)(0x3000 + h * 113 + x));
    for (unsigned t = 0; t < length; ++t)
        for (unsigned x = 0; x < dim; ++x) {
            store16(f.memory + KEY + t * 256 + 2 * x, (uint16_t)(0x3400 + t * 23 + x));
            store16(f.memory + VALUE + t * 256 + 2 * x, (uint16_t)(0x3800 + t * 17 + x));
        }
}

static void full(bool v2, uint64_t tile)
{
    CHECK(execute(insn(v2 ? 6 : 2, 0, 0, 10, 11), DESCRIPTOR, tile).status == AKV_MODEL_OK);
    CHECK(model.valid && model.v2 == v2);
}

static void done(const char *name)
{
    ++cases;
    printf("AKV_MODEL_CASE %s PASS\n", name);
}

static void info_test(void)
{
    setup(64, 1, 1);
    CHECK(akv_model_info(0) == akv_capability_word(0, 1));
    CHECK(akv_model_info(1) == akv_capability_word(1, 1));
    CHECK(akv_model_info(2) == (akv_v2_capability_word(2, 1) & ~(UINT64_C(1) << 39)));
    CHECK(akv_model_info(3) == akv_v2_capability_word(3, 1));
    CHECK(!akv_model_info(4) && !akv_model_info(UINT64_MAX));
    csr.fs_enabled = csr.vs_enabled = false; csr.vstart = 7; csr.frm = 7;
    akv_model_result r = execute(insn(4, 0, 10, 11, 0), 2, 0);
    CHECK(r.status == AKV_MODEL_OK && r.writes_scalar && r.scalar == akv_model_info(2));
    CHECK(!r.writes_vrf && !r.fflags && !f.probes && !f.writes);
    CHECK(execute(insn(4, 1, 10, 11, 0), 0, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(execute(insn(4, 0, 10, 11, 1), 0, 0).status == AKV_MODEL_ILLEGAL);
    done("strict_info_scalar");
}

static void replay_test(void)
{
    setup(96, 65, 8); full(true, 0);
    csr.fs_enabled = false; csr.frm = 7;
    CHECK(execute(insn(3, 2, 8, 10, 0), akv_v2_selector(AKV_STREAM_Q, 7), 0).status == AKV_MODEL_OK);
    for (unsigned d = 0; d < 96; ++d)
        CHECK(load16(f.vrf[8 + d / 64] + 2 * (d % 64)) == model.q[7][d]);
    for (unsigned i = 64; i < 128; ++i) CHECK(f.vrf[9][i] == 0xa5);
    CHECK(execute(insn(7, 1, 12, 10, 0), 92, 0).status == AKV_MODEL_OK);
    for (unsigned c = 0; c < 4; ++c)
        for (unsigned t = 0; t < 64; ++t) CHECK(load16(f.vrf[12 + c] + 2 * t) == model.k[t][92 + c]);
    CHECK(execute(insn(7, 0, 16, 10, 0), 128 + 95, 0).status == AKV_MODEL_OK);
    for (unsigned t = 0; t < 64; ++t) CHECK(load16(f.vrf[16] + 2 * t) == model.v[t][95]);
    CHECK(!f.fma_h_calls && !f.fma_s_calls);
    done("v2_rows_panel4_v_columns_ordinary_rm");
}

static void refill_test(void)
{
    setup(128, 65, 2); full(true, 0);
    unsigned q_reads = f.q_reads; uint16_t q = model.q[0][0];
    memset(f.memory + DESCRIPTOR, 0xff, 64); memset(f.memory + QUERY, 0xff, 512);
    store16(f.memory + KEY + 64 * 256, 0x4567);
    CHECK(execute(insn(6, 1, 0, 0, 11), UINT64_MAX, 64).status == AKV_MODEL_OK);
    CHECK(model.tokens == 1 && model.tile_start == 64 && model.q[0][0] == q && f.q_reads == q_reads);
    CHECK(model.k[0][0] == 0x4567);
    CHECK(execute(insn(7, 1, 20, 10, 0), 0, 0).status == AKV_MODEL_OK);
    for (unsigned c = 0; c < 4; ++c) {
        CHECK(load16(f.vrf[20 + c]) == model.k[0][c]);
        for (unsigned i = 2; i < 128; ++i) CHECK(f.vrf[20 + c][i] == 0xa5);
    }
    done("refill_q_retention_and_column_tail");
}

static void fault_test(void)
{
    setup(64, 65, 2); full(true, 0);
    unsigned reads = f.reads;
    uint32_t instruction = insn(6, 0, 0, 10, 11);
    akv_model_result rejected = execute(instruction, DESCRIPTOR + 1, 0);
    CHECK(rejected.status == AKV_MODEL_ILLEGAL && rejected.fault_addr == instruction);
    CHECK(model.valid && f.reads == reads);
    CHECK(execute(insn(7, 1, 8, 10, 0), 63, 0).status == AKV_MODEL_ILLEGAL && model.valid);
    f.memory[DESCRIPTOR + 3] = 1;
    rejected = execute(instruction, DESCRIPTOR, 0);
    CHECK(rejected.status == AKV_MODEL_ILLEGAL && !rejected.fault_addr && !model.valid);
    CHECK(execute(insn(3, 0, 8, 10, 0), 0, 0).status == AKV_MODEL_ILLEGAL && !f.writes);
    f.memory[DESCRIPTOR + 3] = 0; full(true, 0);
    CHECK(execute(insn(6, 1, 0, 0, 11), 0, 65).status == AKV_MODEL_ILLEGAL && !model.valid);
    full(true, 0);
    CHECK(execute(insn(2, 1, 0, 0, 11), 0, 1).status == AKV_MODEL_ILLEGAL && !model.valid);
    full(true, 0); f.bad = VALUE + 256;
    akv_model_result r = execute(insn(6, 1, 0, 0, 11), 0, 1);
    CHECK(r.status == AKV_MODEL_ACCESS && r.fault_addr == f.bad && !model.valid && !f.writes);
    f.bad = UINT64_MAX; full(true, 0);
    done("frontend_preservation_backend_poison_recovery");
}

static void longjmp_test(void)
{
    setup(64, 9, 1); full(true, 0);
    f.bad = KEY; f.jump = true;
    if (!setjmp(f.escape)) {
        (void)execute(insn(6, 1, 0, 0, 11), 0, 0);
        CHECK(false);
    }
    CHECK(!model.valid && !f.writes);
    f.jump = false; f.bad = UINT64_MAX; full(true, 0);
    done("qemu_longjmp_poison_before_callback");
}

static void descriptor_test(void)
{
    static const unsigned offsets[] = {0, 1, 2, 3, 20, 48, 56};
    for (unsigned i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
        setup(64, 1, 1); full(true, 0); f.memory[DESCRIPTOR + offsets[i]] = 0xff;
        CHECK(execute(insn(6, 0, 0, 10, 11), DESCRIPTOR, 0).status == AKV_MODEL_ILLEGAL && !model.valid);
    }
    setup(64, 2, 1); store64(f.memory + DESCRIPTOR + 32, UINT64_MAX - 31);
    CHECK(execute(insn(6, 0, 0, 10, 11), DESCRIPTOR, 0).status == AKV_MODEL_ILLEGAL && !model.valid);
    setup(256, 1, 1);
    CHECK(execute(insn(6, 0, 0, 10, 11), DESCRIPTOR, 0).status == AKV_MODEL_ILLEGAL && !model.valid);
    setup(96, 1, 1);
    CHECK(execute(insn(2, 0, 0, 10, 11), DESCRIPTOR, 0).status == AKV_MODEL_ILLEGAL);
    done("descriptor_ranges_reserved_and_unsupported");
}

static void legacy_hart_test(void)
{
    setup(128, 9, 2); full(false, 0); other = model;
    CHECK(model.tokens == 8);
    CHECK(execute(insn(2, 1, 0, 0, 11), 0, 8).status == AKV_MODEL_OK && model.tokens == 1);
    CHECK(other.tokens == 8 && other.tile_start == 0);
    CHECK(execute(insn(3, 1, 8, 10, 0), akv_selector(AKV_STREAM_V, 0), 0).status == AKV_MODEL_OK);
    CHECK(load16(f.vrf[8]) == model.v[0][0]);
    CHECK(execute(insn(5, 0, 0, 0, 0), 0, 0).status == AKV_MODEL_OK && !model.valid && other.valid);
    CHECK(execute(insn(7, 0, 16, 10, 0), 0, 0).status == AKV_MODEL_ILLEGAL);
    akv_model_reset(&other); CHECK(!other.valid && !other.q[0][0]);
    done("v1_and_perhart_release_reset");
}

static void qk_test(void)
{
    setup(96, 9, 8); full(true, 0); csr.frm = f.rm = 4;
    uint64_t control = 8 | 64 | UINT64_C(2) << 7 | UINT64_C(6) << 9;
    akv_model_result r = execute(insn(7, 3, 0, 10, 0), control, 0);
    CHECK(r.status == AKV_MODEL_OK && r.fflags == 16 && r.writes_vrf && f.fma_s_calls == 2 * 9 * 96);
    for (unsigned h = 0; h < 2; ++h)
        for (unsigned t = 0; t < 9; ++t) {
            uint32_t expected = 0;
            for (unsigned d = 0; d < 96; ++d)
                expected = toy_s(akv_model_f16_to_f32(model.q[6 + h][d]),
                                 akv_model_f16_to_f32(model.k[t][d]), expected);
            CHECK(load32(f.vrf[h * 2] + t * 4) == expected);
        }
    for (unsigned h = 0; h < 2; ++h)
        for (unsigned b = 36; b < 256; ++b) CHECK(f.vrf[h * 2 + b / 128][b % 128] == 0xa5);
    done("qk_base6_h2_d96_t9_order_and_tail");
}

static void pv_test(void)
{
    setup(128, 64, 1); full(true, 0); csr.frm = f.rm = 2;
    uint16_t source[384];
    for (unsigned i = 0; i < 384; ++i) {
        source[i] = (uint16_t)(0x2000 + i * 29);
        store16(f.vrf[8 + i / 64] + (i % 64) * 2, source[i]);
    }
    uint8_t before[sizeof(f.vrf)]; memcpy(before, f.vrf, sizeof(before));
    /* PV H2 has no Q-row bound: its seeds/coefficients are architectural VRF input. */
    akv_model_result r = execute(insn(7, 2, 0, 10, 8), 63 | 64 | 128, 0);
    CHECK(r.status == AKV_MODEL_OK && r.fflags == 1 && f.fma_h_calls == 2 * 128 * 64);
    for (unsigned h = 0; h < 2; ++h)
        for (unsigned d = 0; d < 128; ++d) {
            uint16_t expected = source[h * 128 + d];
            for (unsigned t = 0; t < 64; ++t)
                expected = toy_h(source[256 + t * 2 + h], model.v[t][d], expected);
            CHECK(load16(f.vrf[2 * h + d / 64] + (d % 64) * 2) == expected);
        }
    CHECK(memcmp(&f.vrf[4], before + 4 * 128, sizeof(f.vrf) - 4 * 128) == 0);
    done("pv_sixreg_seeds_coefficients_h2_t64_rm2");
}

static void resident_errors_test(void)
{
    setup(64, 1, 2); full(true, 0);
    const uint32_t qk = insn(7, 3, 0, 10, 0), pv = insn(7, 2, 0, 10, 8);
    uint8_t before[sizeof(f.vrf)]; memcpy(before, f.vrf, sizeof(before));
    csr.fs_enabled = false; CHECK(execute(qk, 0, 0).status == AKV_MODEL_ILLEGAL);
    csr.fs_enabled = true; csr.vstart = 1; CHECK(execute(pv, 0, 0).status == AKV_MODEL_ILLEGAL);
    csr.vstart = 0; csr.frm = 5; CHECK(execute(qk, 0, 0).status == AKV_MODEL_ILLEGAL);
    csr.frm = 0;
    CHECK(execute(qk, 1, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(execute(qk, 128, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(execute(qk, UINT64_C(2) << 9, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(execute(insn(7, 3, 2, 10, 0), 0, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(execute(insn(7, 2, 8, 10, 8), 0, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(execute(insn(7, 2, 0, 10, 4), 0, 0).status == AKV_MODEL_ILLEGAL);
    f.deny_reg = 2;
    CHECK(execute(qk, 64, 0).status == AKV_MODEL_ILLEGAL);
    CHECK(model.valid && !f.fma_h_calls && !f.fma_s_calls && !f.writes && memcmp(before, f.vrf, sizeof(before)) == 0);
    f.deny_reg = -1;
    CHECK(execute(qk, 0, 0).status == AKV_MODEL_OK && model.valid);
    done("resident_reject_atomic_same_context_recovery");
}

static void widen_test(void)
{
    static const struct { uint16_t h; uint32_t s; } cases_bits[] = {
        {0, 0}, {0x8000, 0x80000000}, {1, 0x33800000}, {0x3ff, 0x387fc000},
        {0x400, 0x38800000}, {0x3c00, 0x3f800000}, {0x7bff, 0x477fe000},
        {0x7c00, 0x7f800000}, {0xfc00, 0xff800000}, {0x7c01, 0x7f802000},
        {0xfc01, 0xff802000}, {0x7e01, 0x7fc02000}, {0xfe01, 0xffc02000}
    };
    for (unsigned i = 0; i < sizeof(cases_bits) / sizeof(cases_bits[0]); ++i)
        CHECK(akv_model_f16_to_f32(cases_bits[i].h) == cases_bits[i].s);
    for (unsigned h = 0x7c01; h < 0x7e00; ++h)
        CHECK((akv_model_f16_to_f32((uint16_t)h) & 0x00400000) == 0);
    done("exact_widen_subnormal_zero_inf_signaling_nan");
}

int main(void)
{
    info_test(); replay_test(); refill_test(); fault_test(); longjmp_test();
    descriptor_test(); legacy_hart_test(); qk_test(); pv_test();
    resident_errors_test(); widen_test();
    printf("AKV_MODEL_HOST_PASS cases=%u arithmetic=callback_contract_not_softfloat\n", cases);
    return 0;
}
