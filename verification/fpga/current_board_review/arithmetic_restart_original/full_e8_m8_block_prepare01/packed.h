/* Actual output footprint is1026B; ROM block padding is never accessed here. */
static uint64_t raw_word(const uint8_t *p) {
    uint64_t value;
    __builtin_memcpy(&value,p,8);
    return value;
}
static void initialize_output(uint8_t *p) {
    const uint64_t value=UINT64_C(0x5b5b5b5b5b5b5b5b);
    for(unsigned offset=0;offset<1024;offset+=64) {
        __builtin_memcpy(p+offset,&value,8);
        __builtin_memcpy(p+offset+8,&value,8);
        __builtin_memcpy(p+offset+16,&value,8);
        __builtin_memcpy(p+offset+24,&value,8);
        __builtin_memcpy(p+offset+32,&value,8);
        __builtin_memcpy(p+offset+40,&value,8);
        __builtin_memcpy(p+offset+48,&value,8);
        __builtin_memcpy(p+offset+56,&value,8);
    }
    const uint16_t tail=0x5b5b;
    __builtin_memcpy(p+1024,&tail,2);
}
static void initialize_mask(uint8_t *p,unsigned mode) {
    for(unsigned i=0;i<16;++i)__builtin_memcpy(p+8*i,physical_masks[mode]+8*i,8);
}
static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal) {
    const uint16_t *indices=expected_indices[ordinal];
    for(unsigned block=0;block<16;++block) {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[block];
        const uint8_t *actual=p+64*block;
        if(raw_word(actual)!=expected[0])return 1;
        if(raw_word(actual+8)!=expected[1])return 1;
        if(raw_word(actual+16)!=expected[2])return 1;
        if(raw_word(actual+24)!=expected[3])return 1;
        if(raw_word(actual+32)!=expected[4])return 1;
        if(raw_word(actual+40)!=expected[5])return 1;
        if(raw_word(actual+48)!=expected[6])return 1;
        if(raw_word(actual+56)!=expected[7])return 1;
    }
    uint16_t tail;
    __builtin_memcpy(&tail,p+1024,2);
    return tail!=(uint16_t)expected_dictionary[8*(unsigned)indices[16]];
}
