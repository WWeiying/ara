/* Byte pointers keep out+1 legal and preserve the exact 514-byte footprint. */
static uint64_t raw_word(const uint8_t *p) {
    uint64_t v;
    __builtin_memcpy(&v, p, sizeof(v));
    return v;
}
static void initialize_output(uint8_t *p) {
    const uint64_t sentinel = UINT64_C(0x5b5b5b5b5b5b5b5b);
    for(unsigned i=0;i<64;i+=4){
        __builtin_memcpy(p+8*i,&sentinel,8);
        __builtin_memcpy(p+8*(i+1),&sentinel,8);
        __builtin_memcpy(p+8*(i+2),&sentinel,8);
        __builtin_memcpy(p+8*(i+3),&sentinel,8);
    }
    p[512]=91;p[513]=91;
}
static void initialize_mask(uint8_t *p,unsigned mode) {
    for(unsigned i=0;i<16;++i)__builtin_memcpy(p+8*i,physical_masks[mode]+8*i,8);
}
static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal) {
    const uint16_t *indices=expected_indices[ordinal];
    for(unsigned i=0;i<64;i+=4){
        if(raw_word(p+8*i)!=expected_dictionary[indices[i]])return 1;
        if(raw_word(p+8*(i+1))!=expected_dictionary[indices[i+1]])return 1;
        if(raw_word(p+8*(i+2))!=expected_dictionary[indices[i+2]])return 1;
        if(raw_word(p+8*(i+3))!=expected_dictionary[indices[i+3]])return 1;
    }
    uint16_t tail;
    __builtin_memcpy(&tail,p+512,2);
    return tail!=(uint16_t)expected_dictionary[indices[64]];
}
