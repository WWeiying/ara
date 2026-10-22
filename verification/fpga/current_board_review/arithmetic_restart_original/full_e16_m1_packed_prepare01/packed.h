/* Exact132B typed uint16 output64 and005b guards; raw byte memcpy only. */
static uint64_t raw_word(const uint8_t *p) {uint64_t v;__builtin_memcpy(&v,p,8);return v;}
static void initialize_output(uint8_t *p) {
    const uint64_t v=UINT64_C(0x005b005b005b005b);
    __builtin_memcpy(p+0,&v,8);
    __builtin_memcpy(p+8,&v,8);
    __builtin_memcpy(p+16,&v,8);
    __builtin_memcpy(p+24,&v,8);
    __builtin_memcpy(p+32,&v,8);
    __builtin_memcpy(p+40,&v,8);
    __builtin_memcpy(p+48,&v,8);
    __builtin_memcpy(p+56,&v,8);
    __builtin_memcpy(p+64,&v,8);
    __builtin_memcpy(p+72,&v,8);
    __builtin_memcpy(p+80,&v,8);
    __builtin_memcpy(p+88,&v,8);
    __builtin_memcpy(p+96,&v,8);
    __builtin_memcpy(p+104,&v,8);
    __builtin_memcpy(p+112,&v,8);
    __builtin_memcpy(p+120,&v,8);
    const uint32_t tail=UINT32_C(0x005b005b);__builtin_memcpy(p+128,&tail,4);
}
static void initialize_mask(uint8_t *p,unsigned mode) {
    for(unsigned i=0;i<16;++i)__builtin_memcpy(p+8*i,physical_masks[mode]+8*i,8);
}
static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal) {
    const uint64_t *expected=expected_words[ordinal];
    if(raw_word(p+0)!=expected[0])return 1;
    if(raw_word(p+8)!=expected[1])return 1;
    if(raw_word(p+16)!=expected[2])return 1;
    if(raw_word(p+24)!=expected[3])return 1;
    if(raw_word(p+32)!=expected[4])return 1;
    if(raw_word(p+40)!=expected[5])return 1;
    if(raw_word(p+48)!=expected[6])return 1;
    if(raw_word(p+56)!=expected[7])return 1;
    if(raw_word(p+64)!=expected[8])return 1;
    if(raw_word(p+72)!=expected[9])return 1;
    if(raw_word(p+80)!=expected[10])return 1;
    if(raw_word(p+88)!=expected[11])return 1;
    if(raw_word(p+96)!=expected[12])return 1;
    if(raw_word(p+104)!=expected[13])return 1;
    if(raw_word(p+112)!=expected[14])return 1;
    if(raw_word(p+120)!=expected[15])return 1;
    uint32_t tail;__builtin_memcpy(&tail,p+128,4);return tail!=(uint32_t)expected[16];
}
