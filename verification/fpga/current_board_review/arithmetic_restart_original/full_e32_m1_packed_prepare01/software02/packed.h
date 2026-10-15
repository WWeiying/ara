/* Static draft only. Original typed uint32_t sentinel, exact136B footprint. */
#include <stdint.h>
static uint64_t raw_word32(const void *p, unsigned byte_offset) {
    uint64_t value;
    __builtin_memcpy(&value,(const unsigned char *)p+byte_offset,8);
    return value;
}
static void initialize_output(void *p) {
    const uint64_t value=UINT64_C(0x0000005b0000005b);
    __builtin_memcpy((unsigned char *)p+0,&value,8);
    __builtin_memcpy((unsigned char *)p+8,&value,8);
    __builtin_memcpy((unsigned char *)p+16,&value,8);
    __builtin_memcpy((unsigned char *)p+24,&value,8);
    __builtin_memcpy((unsigned char *)p+32,&value,8);
    __builtin_memcpy((unsigned char *)p+40,&value,8);
    __builtin_memcpy((unsigned char *)p+48,&value,8);
    __builtin_memcpy((unsigned char *)p+56,&value,8);
    __builtin_memcpy((unsigned char *)p+64,&value,8);
    __builtin_memcpy((unsigned char *)p+72,&value,8);
    __builtin_memcpy((unsigned char *)p+80,&value,8);
    __builtin_memcpy((unsigned char *)p+88,&value,8);
    __builtin_memcpy((unsigned char *)p+96,&value,8);
    __builtin_memcpy((unsigned char *)p+104,&value,8);
    __builtin_memcpy((unsigned char *)p+112,&value,8);
    __builtin_memcpy((unsigned char *)p+120,&value,8);
    __builtin_memcpy((unsigned char *)p+128,&value,8);
}
static unsigned packed_mismatch(const void *p,uint64_t ordinal) {
    const uint64_t *expected=expected_words[ordinal];
    if(raw_word32(p,0)!=expected[0])return 1;
    if(raw_word32(p,8)!=expected[1])return 1;
    if(raw_word32(p,16)!=expected[2])return 1;
    if(raw_word32(p,24)!=expected[3])return 1;
    if(raw_word32(p,32)!=expected[4])return 1;
    if(raw_word32(p,40)!=expected[5])return 1;
    if(raw_word32(p,48)!=expected[6])return 1;
    if(raw_word32(p,56)!=expected[7])return 1;
    if(raw_word32(p,64)!=expected[8])return 1;
    if(raw_word32(p,72)!=expected[9])return 1;
    if(raw_word32(p,80)!=expected[10])return 1;
    if(raw_word32(p,88)!=expected[11])return 1;
    if(raw_word32(p,96)!=expected[12])return 1;
    if(raw_word32(p,104)!=expected[13])return 1;
    if(raw_word32(p,112)!=expected[14])return 1;
    if(raw_word32(p,120)!=expected[15])return 1;
    if(raw_word32(p,128)!=expected[16])return 1;
    return 0;
}
