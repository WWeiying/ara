#include "akv_model.h"

#include <limits.h>
#include <string.h>

typedef struct {
    unsigned reg;
    size_t bytes;
    const uint8_t *data;
} write_piece;

static akv_model_result result(akv_model_status status)
{
    akv_model_result r = {0};
    r.status = status;
    return r;
}

static uint16_t le16(const uint8_t *p)
{
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8);
}

static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)le16(p) | (uint32_t)le16(p + 2) << 16;
}

static uint64_t le64(const uint8_t *p)
{
    return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32;
}

static void put16(uint8_t *p, uint16_t n)
{
    p[0] = (uint8_t)n;
    p[1] = (uint8_t)(n >> 8);
}

static void put32(uint8_t *p, uint32_t n)
{
    put16(p, (uint16_t)n);
    put16(p + 2, (uint16_t)(n >> 16));
}

void akv_model_reset(akv_model *m)
{
    memset(m, 0, sizeof(*m));
}

uint64_t akv_model_info(uint64_t index)
{
    switch (index) {
    case 0:
        return UINT64_C(1) | UINT64_C(1) << 8 | UINT64_C(64) << 16 |
            UINT64_C(8) << 24 | UINT64_C(8) << 32 | UINT64_C(1) << 40 |
            UINT64_C(15) << 48;
    case 1:
        return UINT64_C(0x5b) | UINT64_C(2) << 8 | UINT64_C(3) << 11 |
            UINT64_C(4) << 14 | UINT64_C(5) << 17 | UINT64_C(6) << 20;
    case 2:
        /* Bit 39 (D256 segmented) is intentionally not advertised. */
        return UINT64_C(2) | UINT64_C(64) << 8 | UINT64_C(8) << 16 |
            UINT64_C(6) << 24 | UINT64_C(0x7f) << 32 | UINT64_C(1) << 40;
    case 3:
        return UINT64_C(0x5b) | UINT64_C(6) << 8 | UINT64_C(7) << 11 |
            UINT64_C(128) << 16 | UINT64_C(1) << 24;
    default:
        return 0;
    }
}

uint32_t akv_model_f16_to_f32(uint16_t bits)
{
    uint32_t sign = (uint32_t)(bits & 0x8000u) << 16;
    uint32_t exponent = (bits >> 10) & 31u, fraction = bits & 1023u;
    if (exponent == 31)
        return sign | UINT32_C(0x7f800000) | fraction << 13;
    if (exponent)
        return sign | (exponent + 112) << 23 | fraction << 13;
    if (!fraction)
        return sign;
    exponent = 113;
    while (!(fraction & 1024)) {
        fraction <<= 1;
        --exponent;
    }
    return sign | exponent << 23 | (fraction & 1023u) << 13;
}

static bool range_fits(uint64_t base, uint32_t stride, unsigned count, unsigned bytes)
{
    uint64_t last = (uint64_t)(count - 1) * stride;
    return count && bytes && last <= UINT64_MAX - base &&
        bytes - 1 <= UINT64_MAX - (base + last);
}

static bool descriptor(akv_model *m, const uint8_t d[64], bool v2, uint64_t tile)
{
    unsigned rows = d[2], dim = le16(d + 4), length = le16(d + 6);
    unsigned bytes = 2 * dim, alignment = v2 ? 31 : 1;
    uint32_t qs = le32(d + 8), ks = le32(d + 12), vs = le32(d + 16);
    uint64_t qb = le64(d + 24), kb = le64(d + 32), vb = le64(d + 40);
    if (d[0] != 1 || d[1] != 1 || !rows || rows > 8 || !length ||
        !(dim == 64 || dim == 128 || (v2 && dim == 96)) || d[3] ||
        le32(d + 20) || le64(d + 48) || le64(d + 56) ||
        qs < bytes || ks < bytes || vs < bytes ||
        ((qb | kb | vb | qs | ks | vs) & alignment) ||
        !range_fits(qb, qs, rows, bytes) ||
        !range_fits(kb, ks, length, bytes) ||
        !range_fits(vb, vs, length, bytes) || tile >= length)
        return false;
    m->v2 = v2;
    m->q_rows = rows;
    m->dimension = dim;
    m->kv_length = length;
    m->q_stride = qs;
    m->k_stride = ks;
    m->v_stride = vs;
    m->q_base = qb;
    m->k_base = kb;
    m->v_base = vb;
    return true;
}

static bool ram_read(const akv_model_callbacks *cb, uint64_t address,
                     void *data, size_t bytes, akv_model_result *r)
{
    if (!cb->ram_probe(cb->opaque, address, bytes) ||
        !cb->ram_read(cb->opaque, address, data, bytes)) {
        r->status = AKV_MODEL_ACCESS;
        r->fault_addr = address;
        return false;
    }
    return true;
}

static akv_model_result fill(akv_model *m, bool v2, bool refill,
                            uint64_t address, uint64_t tile,
                            const akv_model_callbacks *cb)
{
    akv_model_result r = result(AKV_MODEL_ILLEGAL);
    bool old_valid = m->valid;
    uint8_t bytes[256];
    /* A QEMU memory callback can longjmp: old state must already be unusable. */
    m->valid = false;
    if (!cb || !cb->ram_probe || !cb->ram_read)
        return r;
    if (refill) {
        if (!old_valid || v2 != m->v2 || tile >= m->kv_length)
            return r;
    } else {
        if (!ram_read(cb, address, bytes, 64, &r) ||
            !descriptor(m, bytes, v2, tile))
            return r;
    }
    m->tile_start = tile;
    m->tokens = m->kv_length - (unsigned)tile;
    if (m->tokens > (v2 ? 64u : 8u))
        m->tokens = v2 ? 64 : 8;
    /* Snapshot all resident bytes. REFILL neither reads the descriptor nor Q. */
    for (unsigned stream = refill ? 1 : 0; stream < 3; ++stream) {
        unsigned count = stream ? m->tokens : m->q_rows;
        uint64_t base = stream == 0 ? m->q_base : stream == 1 ? m->k_base : m->v_base;
        uint32_t stride = stream == 0 ? m->q_stride : stream == 1 ? m->k_stride : m->v_stride;
        if (stream)
            base += tile * stride;
        for (unsigned row = 0; row < count; ++row) {
            if (!ram_read(cb, base + (uint64_t)row * stride, bytes, 2 * m->dimension, &r))
                return r;
            uint16_t *to = stream == 0 ? m->q[row] : stream == 1 ? m->k[row] : m->v[row];
            for (unsigned dim = 0; dim < m->dimension; ++dim)
                to[dim] = le16(bytes + 2 * dim);
        }
    }
    m->valid = true;
    return result(AKV_MODEL_OK);
}

static bool probe_vrf(const akv_model_callbacks *cb, unsigned reg, size_t n, bool write)
{
    return reg < 32 && n <= 128 &&
        (!cb->vrf_probe || cb->vrf_probe(cb->opaque, reg, 0, n, write));
}

static akv_model_result commit(const akv_model_callbacks *cb,
                              const write_piece *pieces, unsigned count, uint8_t flags)
{
    akv_model_result r = result(AKV_MODEL_ILLEGAL);
    if (!cb || !cb->vrf_write)
        return r;
    for (unsigned i = 0; i < count; ++i)
        if (!probe_vrf(cb, pieces[i].reg, pieces[i].bytes, true))
            return r;
    for (unsigned i = 0; i < count; ++i)
        cb->vrf_write(cb->opaque, pieces[i].reg, 0, pieces[i].data, pieces[i].bytes);
    r.status = AKV_MODEL_OK;
    r.writes_vrf = true;
    r.fflags = flags & 31;
    return r;
}

static unsigned split(write_piece pieces[4], unsigned index, unsigned reg,
                      const uint8_t *data, size_t bytes)
{
    while (bytes) {
        size_t n = bytes > 128 ? 128 : bytes;
        pieces[index++] = (write_piece){reg++, n, data};
        data += n;
        bytes -= n;
    }
    return index;
}

static akv_model_result replay(const akv_model *m, unsigned vd,
                              unsigned funct3, unsigned funct7, uint64_t selector,
                              const akv_model_callbacks *cb)
{
    akv_model_result bad = result(AKV_MODEL_ILLEGAL);
    write_piece pieces[4];
    uint8_t data[512];
    unsigned n = 0;
    if (!m->valid || !cb)
        return bad;
    if (funct3 == 3) {
        unsigned dimension = funct7 == 0 ? 64 : funct7 == 1 ? 128 : 96;
        unsigned stream = selector & 3, row = (unsigned)(selector >> 2);
        if (dimension != m->dimension || selector >= (m->v2 ? 256u : 32u) ||
            stream == 3 || row >= (stream ? m->tokens : m->q_rows) ||
            (dimension > 64 && ((vd & 1) || vd > 30)))
            return bad;
        const uint16_t *src = stream == 0 ? m->q[row] : stream == 1 ? m->k[row] : m->v[row];
        for (unsigned d = 0; d < dimension; ++d)
            put16(data + 2 * d, src[d]);
        n = split(pieces, 0, vd, data, 2 * dimension);
    } else {
        unsigned dim = selector & 127, columns = funct7 ? 4 : 1;
        if (!m->v2 || selector > 255 || dim + columns > m->dimension ||
            (columns == 4 && ((vd & 3) || vd > 28 || (dim & 3))))
            return bad;
        for (unsigned column = 0; column < columns; ++column) {
            for (unsigned t = 0; t < m->tokens; ++t)
                put16(data + column * 128 + 2 * t,
                      (selector & 128) ? m->v[t][dim + column] : m->k[t][dim + column]);
            pieces[n++] = (write_piece){vd + column, 2 * m->tokens, data + column * 128};
        }
    }
    return commit(cb, pieces, n, 0);
}

static akv_model_status resident_fields(uint32_t insn, uint64_t control,
    const akv_model_csr *csr, akv_model_resident *command)
{
    unsigned f7 = insn >> 25, vd = (insn >> 7) & 31, vs2 = (insn >> 20) & 31;
    unsigned code = (unsigned)(control >> 7) & 3;
    unsigned dim = code == 0 ? 64 : code == 1 ? 128 : code == 2 ? 96 : 0;
    unsigned tokens = (control & 63) + 1, heads = ((control >> 6) & 1) + 1;
    unsigned base = (unsigned)(control >> 9) & 7;
    bool qk = f7 == 3;
    if (!csr || !command || (insn & 0x707f) != 0x705b ||
        !(f7 == 2 || f7 == 3) || !csr->fs_enabled || !csr->vs_enabled ||
        csr->frm > 4 || csr->vstart || !dim || (control >> (qk ? 12 : 9)) ||
        (vd & 3) || vd > 28 ||
        (qk ? vs2 != 0 || base + heads > 8 :
         (vs2 & 7) || vs2 > 24 || (vd < vs2 + 8 && vs2 < vd + 4)))
        return AKV_MODEL_ILLEGAL;
    *command = (akv_model_resident){tokens, heads, dim, qk ? base : 0, vd, vs2, qk};
    return AKV_MODEL_OK;
}

akv_model_status akv_model_validate_resident(const akv_model *m, uint32_t insn,
    uint64_t control, const akv_model_csr *csr, akv_model_resident *command)
{
    if (resident_fields(insn, control, csr, command) != AKV_MODEL_OK || !m ||
        !m->valid || !m->v2 || m->dimension != command->dimension ||
        command->tokens > m->tokens ||
        (command->qk && command->query_base + command->heads > m->q_rows))
        return AKV_MODEL_ILLEGAL;
    return AKV_MODEL_OK;
}

static akv_model_result resident(const akv_model *m, uint32_t insn, uint64_t control,
                               const akv_model_csr *csr, const akv_model_callbacks *cb)
{
    akv_model_resident cmd;
    uint8_t data[512] = {0}, source[768];
    uint8_t flags = 0;
    write_piece pieces[4];
    unsigned n = 0;
    if (resident_fields(insn, control, csr, &cmd) != AKV_MODEL_OK) {
        akv_model_result r = result(AKV_MODEL_ILLEGAL);
        r.fault_addr = insn;
        return r;
    }
    if (akv_model_validate_resident(m, insn, control, csr, &cmd) != AKV_MODEL_OK ||
        !cb || !cb->vrf_write || (cmd.qk ? !cb->fma_s : !cb->fma_h || !cb->vrf_read))
        return result(AKV_MODEL_ILLEGAL);
    for (unsigned h = 0; h < cmd.heads; ++h)
        n = split(pieces, n, cmd.vd + h * 2, data + h * 256,
                  cmd.qk ? cmd.tokens * 4 : cmd.dimension * 2);
    /* No arithmetic or output writes before every destination/source is admitted. */
    for (unsigned i = 0; i < n; ++i)
        if (!probe_vrf(cb, pieces[i].reg, pieces[i].bytes, true))
            return result(AKV_MODEL_ILLEGAL);
    if (!cmd.qk) {
        for (unsigned i = 0; i < 6; ++i)
            if (!probe_vrf(cb, cmd.vs2 + i, 128, false))
                return result(AKV_MODEL_ILLEGAL);
        for (unsigned i = 0; i < 6; ++i)
            if (!cb->vrf_read(cb->opaque, cmd.vs2 + i, 0, source + 128 * i, 128))
                return result(AKV_MODEL_ILLEGAL);
    }
    for (unsigned h = 0; h < cmd.heads; ++h) {
        if (cmd.qk) {
            for (unsigned t = 0; t < cmd.tokens; ++t) {
                uint32_t acc = 0;
                for (unsigned d = 0; d < cmd.dimension; ++d)
                    acc = cb->fma_s(cb->opaque,
                        akv_model_f16_to_f32(m->q[cmd.query_base + h][d]),
                        akv_model_f16_to_f32(m->k[t][d]), acc, csr->frm, &flags);
                put32(data + h * 256 + t * 4, acc);
            }
        } else {
            for (unsigned d = 0; d < cmd.dimension; ++d) {
                uint16_t acc = le16(source + h * 256 + d * 2);
                for (unsigned t = 0; t < cmd.tokens; ++t)
                    acc = cb->fma_h(cb->opaque, le16(source + 512 + t * 4 + h * 2),
                                    m->v[t][d], acc, csr->frm, &flags);
                put16(data + h * 256 + d * 2, acc);
            }
        }
    }
    return commit(cb, pieces, n, flags);
}

bool akv_model_q(const akv_model *m, unsigned row, unsigned d, uint16_t *bits)
{
    if (!m || !m->valid || row >= m->q_rows || d >= m->dimension || !bits)
        return false;
    *bits = m->q[row][d];
    return true;
}

bool akv_model_k(const akv_model *m, unsigned token, unsigned d, uint16_t *bits)
{
    if (!m || !m->valid || token >= m->tokens || d >= m->dimension || !bits)
        return false;
    *bits = m->k[token][d];
    return true;
}

bool akv_model_v(const akv_model *m, unsigned token, unsigned d, uint16_t *bits)
{
    if (!m || !m->valid || token >= m->tokens || d >= m->dimension || !bits)
        return false;
    *bits = m->v[token][d];
    return true;
}

akv_model_result akv_model_execute(akv_model *m, uint32_t insn,
    uint64_t rs1, uint64_t rs2, const akv_model_csr *csr,
    const akv_model_callbacks *cb)
{
    unsigned f3 = (insn >> 12) & 7, f7 = insn >> 25;
    unsigned rd = (insn >> 7) & 31, s1 = (insn >> 15) & 31, s2 = (insn >> 20) & 31;
    akv_model_result r = result(AKV_MODEL_ILLEGAL);
    r.fault_addr = insn;
    if (!m || (insn & 127) != 0x5b)
        return r;
    if (f3 == 4) {
        if (f7 || s2)
            return r;
        r.status = AKV_MODEL_OK;
        r.fault_addr = 0;
        r.scalar = akv_model_info(rs1);
        r.writes_scalar = rd != 0;
        return r;
    }
    if (!csr || !csr->vs_enabled || csr->vstart)
        return r;
    if (f3 == 7 && (f7 == 2 || f7 == 3))
        return resident(m, insn, rs1, csr, cb);
    if (f3 == 2 || f3 == 6) {
        if (f7 > 1 || rd || (f7 == 1 && s1) || (f7 == 0 && (rs1 & 63)))
            return r;
        return fill(m, f3 == 6, f7 == 1, rs1, rs2, cb);
    }
    if (f3 == 5) {
        if (f7 || rd || s1 || s2)
            return r;
        m->valid = false;
        m->v2 = false;
        return result(AKV_MODEL_OK);
    }
    if (f3 == 3) {
        if (f7 > 2 || s2 || (f7 && ((rd & 1) || rd > 30)))
            return r;
        return replay(m, rd, f3, f7, rs1, cb);
    }
    if (f3 == 7 && f7 <= 1) {
        if (s2 || (f7 && ((rd & 3) || rd > 28 || (rs1 & 3))))
            return r;
        return replay(m, rd, f3, f7, rs1, cb);
    }
    return r;
}
