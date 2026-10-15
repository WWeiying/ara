/* Independent integer-only checks; the archived fixture oracle also runs. */
static word seen_a[16], seen_b[16];
static uint8_t seen_mask[2];
extern void capture_vectors(void *, void *, void *);
static unsigned nan16(word x) { return (x & 0x7c00) == 0x7c00 && (x & 0x3ff); }
static unsigned snan16(word x) { return nan16(x) && !(x & 0x200); }
static unsigned eq16(word x, word y) {
    return !nan16(x) && !nan16(y) && (x == y || !((x | y) & 0x7fff));
}
static unsigned mapped(unsigned i) { return CONTROL == 2 && i == 15 ? 14 : i; }
static void hex(unsigned n, unsigned digits) {
    char s[9];
    for (unsigned i = 0; i < digits; ++i)
        s[i] = "0123456789abcdef"[(n >> (4 * (digits - i - 1))) & 15];
    s[digits] = 0;
    text(s);
}
static void audit_before(unsigned cap, unsigned op, unsigned vl, unsigned start) {
    text("CMP_INPUT case=" CASE_NAME " op="); num(op);
    text(" vl="); num(vl); text(" start="); num(start);
    text(" sticky=0 cap="); num(cap); text(" mask=");
    for (unsigned i = 0; i < 2; ++i) hex(mask[i], 2);
    text(" old_buffer=5b5b old_vd=");
    text(DESTINATION_KIND == 3 ? "ffff" : "5b5b"); text("\nCMP_A=");
    for (unsigned i = 0; i < cap; ++i) { hex(a[i], 4); text(" "); }
    text("\nCMP_B=");
    for (unsigned i = 0; i < cap; ++i) { hex(b[i], 4); text(" "); }
    text("\n");
}
static unsigned audit_after(unsigned cap, unsigned op, unsigned vl, unsigned start,
                            unsigned long status, unsigned fixture_errors) {
    unsigned flags = 0, data_errors = 0, setup_errors = 0, oracle_errors = 0;
    for (unsigned i = 0; i < cap; ++i) {
        word x = a[i], y = b[i];
        unsigned ai = i==15 ? 14 : mapped(lhs_index(0, i)), bi = mapped(rhs_index(0, i, op));
        struct fixture f = expected[0][ai][bi];
        unsigned eq = eq16(x, y), nv = (snan16(x) || snan16(y)) ? 16 : 0;
        oracle_errors += f.bit != eq || f.flags != nv;
        unsigned active = i >= start && i < vl && (UNMASKED_COMPARISONS || bit(mask, i));
        unsigned old = DESTINATION_KIND == 3 ? bit(mask, i) : ((0x5b >> (i % 8)) & 1);
        unsigned got = bit(output + 1, i);
        if (active) { flags |= nv; data_errors += got != eq; }
        else if (i < vl || i < start) data_errors += got != old;
        else data_errors += got != old && got != 1 && got != eq;
        setup_errors += seen_a[i] != a[i] || seen_b[i] != b[i];
        setup_errors += a[i] != inputs[ai] || b[i] != inputs[bi];
    }
    for (unsigned i = 0; i < 128; ++i) {
        unsigned wanted = CONTROL == 1 && i == 0 ? 32 : RESTART_COMPARISONS || UNMASKED_COMPARISONS ? 255 : 0;
        setup_errors += mask[i] != wanted;
    }
    for (unsigned i = 0; i < 2; ++i)
        setup_errors += seen_mask[i] != (DESTINATION_KIND == 3 ? output[i + 1] : mask[i]);
    for (unsigned i = 0; i < 130; ++i)
        if (i == 0 || i > 2) setup_errors += output[i] != 0x5b;
    text("CMP_OUTPUT case=" CASE_NAME " bytes="); hex(output[1], 2); hex(output[2], 2);
    text(" v0="); hex(seen_mask[0], 2); hex(seen_mask[1], 2);
    text(" guards="); hex(output[0], 2); hex(output[3], 2); text("\n");
    text("CMP_RESULT case=" CASE_NAME " expected_flags="); num(flags);
    text(" actual_flags="); num(status >> 32); text(" vstart="); num((uint32_t)status);
    text(" data_errors="); num(data_errors); text(" setup_errors="); num(setup_errors);
    text(" oracle_disagreements="); num(oracle_errors);
    text(" fixture_errors="); num(fixture_errors); text("\n");
    return data_errors + setup_errors + oracle_errors + ((status >> 32) != flags) + ((uint32_t)status != 0);
}
