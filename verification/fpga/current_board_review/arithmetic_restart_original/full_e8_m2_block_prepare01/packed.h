/* Exact258 bytes: 32 scalar words plus one halfword; never round up. */
static uint64_t raw_word(const uint8_t *p) {
    uint64_t value;
    __builtin_memcpy(&value,p,8);
    return value;
}
static void initialize_output(uint8_t *p) {
    const uint64_t value=UINT64_C(0x5b5b5b5b5b5b5b5b);
    __builtin_memcpy(p+0,&value,8);
    __builtin_memcpy(p+8,&value,8);
    __builtin_memcpy(p+16,&value,8);
    __builtin_memcpy(p+24,&value,8);
    __builtin_memcpy(p+32,&value,8);
    __builtin_memcpy(p+40,&value,8);
    __builtin_memcpy(p+48,&value,8);
    __builtin_memcpy(p+56,&value,8);
    __builtin_memcpy(p+64,&value,8);
    __builtin_memcpy(p+72,&value,8);
    __builtin_memcpy(p+80,&value,8);
    __builtin_memcpy(p+88,&value,8);
    __builtin_memcpy(p+96,&value,8);
    __builtin_memcpy(p+104,&value,8);
    __builtin_memcpy(p+112,&value,8);
    __builtin_memcpy(p+120,&value,8);
    __builtin_memcpy(p+128,&value,8);
    __builtin_memcpy(p+136,&value,8);
    __builtin_memcpy(p+144,&value,8);
    __builtin_memcpy(p+152,&value,8);
    __builtin_memcpy(p+160,&value,8);
    __builtin_memcpy(p+168,&value,8);
    __builtin_memcpy(p+176,&value,8);
    __builtin_memcpy(p+184,&value,8);
    __builtin_memcpy(p+192,&value,8);
    __builtin_memcpy(p+200,&value,8);
    __builtin_memcpy(p+208,&value,8);
    __builtin_memcpy(p+216,&value,8);
    __builtin_memcpy(p+224,&value,8);
    __builtin_memcpy(p+232,&value,8);
    __builtin_memcpy(p+240,&value,8);
    __builtin_memcpy(p+248,&value,8);
    const uint16_t tail=0x5b5b;
    __builtin_memcpy(p+256,&tail,2);
}
static void initialize_mask(uint8_t *p,unsigned mode) {
    for(unsigned i=0;i<16;++i)__builtin_memcpy(p+8*i,physical_masks[mode]+8*i,8);
}
static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal) {
    const uint16_t *indices=expected_indices[ordinal];
    {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[0];
        if(raw_word(p+0)!=expected[0])return 1;
        if(raw_word(p+8)!=expected[1])return 1;
        if(raw_word(p+16)!=expected[2])return 1;
        if(raw_word(p+24)!=expected[3])return 1;
        if(raw_word(p+32)!=expected[4])return 1;
        if(raw_word(p+40)!=expected[5])return 1;
        if(raw_word(p+48)!=expected[6])return 1;
        if(raw_word(p+56)!=expected[7])return 1;
    }
    {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[1];
        if(raw_word(p+64)!=expected[0])return 1;
        if(raw_word(p+72)!=expected[1])return 1;
        if(raw_word(p+80)!=expected[2])return 1;
        if(raw_word(p+88)!=expected[3])return 1;
        if(raw_word(p+96)!=expected[4])return 1;
        if(raw_word(p+104)!=expected[5])return 1;
        if(raw_word(p+112)!=expected[6])return 1;
        if(raw_word(p+120)!=expected[7])return 1;
    }
    {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[2];
        if(raw_word(p+128)!=expected[0])return 1;
        if(raw_word(p+136)!=expected[1])return 1;
        if(raw_word(p+144)!=expected[2])return 1;
        if(raw_word(p+152)!=expected[3])return 1;
        if(raw_word(p+160)!=expected[4])return 1;
        if(raw_word(p+168)!=expected[5])return 1;
        if(raw_word(p+176)!=expected[6])return 1;
        if(raw_word(p+184)!=expected[7])return 1;
    }
    {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[3];
        if(raw_word(p+192)!=expected[0])return 1;
        if(raw_word(p+200)!=expected[1])return 1;
        if(raw_word(p+208)!=expected[2])return 1;
        if(raw_word(p+216)!=expected[3])return 1;
        if(raw_word(p+224)!=expected[4])return 1;
        if(raw_word(p+232)!=expected[5])return 1;
        if(raw_word(p+240)!=expected[6])return 1;
        if(raw_word(p+248)!=expected[7])return 1;
    }
    uint16_t tail;
    __builtin_memcpy(&tail,p+256,2);
    return tail!=(uint16_t)expected_dictionary[8*(unsigned)indices[4]];
}
