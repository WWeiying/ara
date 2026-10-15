/* Exact66 bytes: uint8 output64 plus one guard at each end. */
static uint64_t raw_word(const uint8_t *p) {
    uint64_t value;
    __builtin_memcpy(&value,p,8);
    return value;
}
static void initialize_output(uint8_t *p) {
    const uint64_t value=UINT64_C(0x5b5b5b5b5b5b5b5b);
    __builtin_memcpy(p,&value,8);
    __builtin_memcpy(p+8,&value,8);
    __builtin_memcpy(p+16,&value,8);
    __builtin_memcpy(p+24,&value,8);
    __builtin_memcpy(p+32,&value,8);
    __builtin_memcpy(p+40,&value,8);
    __builtin_memcpy(p+48,&value,8);
    __builtin_memcpy(p+56,&value,8);
    const uint16_t tail=0x5b5b;
    __builtin_memcpy(p+64,&tail,2);
}
static void initialize_mask(uint8_t *p,unsigned mode) {
    for(unsigned i=0;i<16;++i)__builtin_memcpy(p+8*i,physical_masks[mode]+8*i,8);
}
static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal) {
    const uint64_t *expected=expected_words[ordinal];
    if(raw_word(p)!=expected[0])return 1;
    if(raw_word(p+8)!=expected[1])return 1;
    if(raw_word(p+16)!=expected[2])return 1;
    if(raw_word(p+24)!=expected[3])return 1;
    if(raw_word(p+32)!=expected[4])return 1;
    if(raw_word(p+40)!=expected[5])return 1;
    if(raw_word(p+48)!=expected[6])return 1;
    if(raw_word(p+56)!=expected[7])return 1;
    uint16_t tail;
    __builtin_memcpy(&tail,p+64,2);
    return tail!=(uint16_t)expected[8];
}
