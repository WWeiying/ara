typedef uint64_t alias_u64 __attribute__((__may_alias__));

/* Scalar accesses cover bytes 0..511, then 512..513; out+1 remains unchanged. */
__attribute__((noinline)) static void full_init(void) {
    volatile alias_u64 *p = (volatile alias_u64 *)out;
    for (unsigned i = 0; i < 64; ++i) p[i] = UINT64_C(0x5b5b5b5b5b5b5b5b);
    ((volatile uint8_t *)out)[512] = 0x5b;
    ((volatile uint8_t *)out)[513] = 0x5b;
}

__attribute__((noinline)) static unsigned full_oracle(unsigned trial) {
    const uint64_t *expected = expected_blocks[expected_index[trial]];
    const volatile alias_u64 *p = (const volatile alias_u64 *)out;
    unsigned bad = 0;
    for (unsigned i = 0; i < 64; ++i) {
        uint64_t actual = p[i];
        if (actual != expected[i]) ++bad;
    }
    if (((const volatile uint8_t *)out)[512] != (expected[64] & 255)) ++bad;
    if (((const volatile uint8_t *)out)[513] != ((expected[64] >> 8) & 255)) ++bad;
    return bad;
}
