/* Freestanding test only. The host checker owns the independent golden. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long u64;
_Static_assert(sizeof(u64) == 8 && sizeof(u16) == 2, "RV64 layout");
extern const u16 query_data[], key_data[], value_data[], pv_source[];
extern const u8 expected_row[], expected_column[], expected_qk[], expected_pv[], expected_source[];
static const struct __attribute__((aligned(64))) {
    u8 version, format, heads, flags;
    u16 dimension, tokens;
    u32 q_stride, k_stride, v_stride, reserved0;
    const void *q, *k, *v;
    u64 reserved1, reserved2;
} descriptor = {1, 1, 2, 0, 128, 64, 256, 256, 256, 0,
                query_data, key_data, value_data, 0, 0};
_Static_assert(sizeof(descriptor) == 64, "AKV descriptor ABI");
static u8 row[384] __attribute__((aligned(64)));
static u8 column[640] __attribute__((aligned(64)));
static u8 qk[640] __attribute__((aligned(64)));
static u8 pv[640] __attribute__((aligned(64)));
static u8 source[1152] __attribute__((aligned(64)));
static u64 observation[4][3];
extern void fill_context(const void *, u64), release_context(void);
extern void row_case(u64, void *, void *), column_case(u64, void *, void *);
extern void qk_case(u64, void *, void *), pv_case(u64, void *, void *, const void *, void *);
static void put(char c) { *(volatile u8 *)0xc0000000UL = (u8)c; }
static void text(const char *s) { while (*s) put(*s++); }
static void hex(u64 x, unsigned digits) {
    const char h[] = "0123456789abcdef";
    for (int shift = (int)digits * 4 - 4; shift >= 0; shift -= 4) put(h[(x >> shift) & 15]);
}
static void initialize(u8 *p, unsigned n) { for (unsigned i = 0; i < n; i++) p[i] = 0xa5; }
void trap_report(u64 cause, u64 pc, u64 value) {
    text("DRAIN_TRAP mcause="); hex(cause, 16); text(" mepc="); hex(pc, 16);
    text(" mtval="); hex(value, 16); put('\n');
}
static unsigned compare(const char *name, const u8 *p, const u8 *gold, unsigned n, unsigned elements) {
    unsigned mismatches = 0, first = ~0u;
    for (unsigned i = 0; i < n; i++) {
        if (p[i] != gold[i]) { if (!mismatches) first = i; mismatches++; }
    }
    text("DRAIN_CHECK name="); text(name); text(" elements="); hex(elements, 8);
    text(" checked="); hex(n, 8); text(" mismatches="); hex(mismatches, 8);
    text(" first="); hex(first, 8); text(" actual="); hex(mismatches ? p[first] : 0, 2);
    text(" expected="); hex(mismatches ? gold[first] : 0, 2); put('\n');
    return mismatches;
}
int main(void) {
    u64 vlenb;
    __asm__ volatile("csrr %0, vlenb" : "=r"(vlenb));
    if (vlenb != 128) return 1;
    initialize(row, sizeof(row)); initialize(column, sizeof(column));
    initialize(qk, sizeof(qk)); initialize(pv, sizeof(pv)); initialize(source, sizeof(source));
    fill_context(&descriptor, 0);
    row_case(2 | (63 << 2), row + 64, observation[0]);
    column_case(20, column + 64, observation[1]);
    qk_case(255, qk + 64, observation[2]);
    pv_case(255, pv + 64, observation[3], pv_source, source + 64);
    release_context();
    unsigned errors = compare("row", row, expected_row, sizeof(row), 128);
    errors += compare("column", column, expected_column, sizeof(column), 256);
    errors += compare("qk", qk, expected_qk, sizeof(qk), 128);
    errors += compare("pv", pv, expected_pv, sizeof(pv), 256);
    errors += compare("source", source, expected_source, sizeof(source), 512);
    for (unsigned i = 0; i < 4; i++) {
        errors += observation[i][0] != (i == 0 || i == 2 ? 128 : 256) ||
                  observation[i][1] != 1 || observation[i][2] != 0;
        text("DRAIN_OBS index="); hex(i, 2); text(" vl="); hex(observation[i][0], 16);
        text(" fcsr="); hex(observation[i][1], 16); text(" vstart="); hex(observation[i][2], 16); put('\n');
    }
    text("DRAIN_PAYLOAD_END\n");
    return errors != 0;
}
