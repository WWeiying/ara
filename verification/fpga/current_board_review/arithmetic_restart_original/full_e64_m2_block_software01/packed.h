#include <stdint.h>
static uint64_t raw_word(const void *p){uint64_t v;__builtin_memcpy(&v,p,8);return v;}
static void initialize_output(void *p){const uint64_t v=UINT64_C(0x5b);
__builtin_memcpy((unsigned char *)p+0,&v,8);
__builtin_memcpy((unsigned char *)p+8,&v,8);
__builtin_memcpy((unsigned char *)p+16,&v,8);
__builtin_memcpy((unsigned char *)p+24,&v,8);
__builtin_memcpy((unsigned char *)p+32,&v,8);
__builtin_memcpy((unsigned char *)p+40,&v,8);
__builtin_memcpy((unsigned char *)p+48,&v,8);
__builtin_memcpy((unsigned char *)p+56,&v,8);
__builtin_memcpy((unsigned char *)p+64,&v,8);
__builtin_memcpy((unsigned char *)p+72,&v,8);
__builtin_memcpy((unsigned char *)p+80,&v,8);
__builtin_memcpy((unsigned char *)p+88,&v,8);
__builtin_memcpy((unsigned char *)p+96,&v,8);
__builtin_memcpy((unsigned char *)p+104,&v,8);
__builtin_memcpy((unsigned char *)p+112,&v,8);
__builtin_memcpy((unsigned char *)p+120,&v,8);
__builtin_memcpy((unsigned char *)p+128,&v,8);
__builtin_memcpy((unsigned char *)p+136,&v,8);
__builtin_memcpy((unsigned char *)p+144,&v,8);
__builtin_memcpy((unsigned char *)p+152,&v,8);
__builtin_memcpy((unsigned char *)p+160,&v,8);
__builtin_memcpy((unsigned char *)p+168,&v,8);
__builtin_memcpy((unsigned char *)p+176,&v,8);
__builtin_memcpy((unsigned char *)p+184,&v,8);
__builtin_memcpy((unsigned char *)p+192,&v,8);
__builtin_memcpy((unsigned char *)p+200,&v,8);
__builtin_memcpy((unsigned char *)p+208,&v,8);
__builtin_memcpy((unsigned char *)p+216,&v,8);
__builtin_memcpy((unsigned char *)p+224,&v,8);
__builtin_memcpy((unsigned char *)p+232,&v,8);
__builtin_memcpy((unsigned char *)p+240,&v,8);
__builtin_memcpy((unsigned char *)p+248,&v,8);
__builtin_memcpy((unsigned char *)p+256,&v,8);
__builtin_memcpy((unsigned char *)p+264,&v,8);
}
static unsigned packed_mismatch(const void *p,uint64_t ordinal){const uint16_t *ids=expected_indices[ordinal];
{const uint64_t *expected=expected_dictionary+8*(unsigned)ids[0];
if(raw_word((const unsigned char *)p+0)!=expected[0])return 1;
if(raw_word((const unsigned char *)p+8)!=expected[1])return 1;
if(raw_word((const unsigned char *)p+16)!=expected[2])return 1;
if(raw_word((const unsigned char *)p+24)!=expected[3])return 1;
if(raw_word((const unsigned char *)p+32)!=expected[4])return 1;
if(raw_word((const unsigned char *)p+40)!=expected[5])return 1;
if(raw_word((const unsigned char *)p+48)!=expected[6])return 1;
if(raw_word((const unsigned char *)p+56)!=expected[7])return 1;
}
{const uint64_t *expected=expected_dictionary+8*(unsigned)ids[1];
if(raw_word((const unsigned char *)p+64)!=expected[0])return 1;
if(raw_word((const unsigned char *)p+72)!=expected[1])return 1;
if(raw_word((const unsigned char *)p+80)!=expected[2])return 1;
if(raw_word((const unsigned char *)p+88)!=expected[3])return 1;
if(raw_word((const unsigned char *)p+96)!=expected[4])return 1;
if(raw_word((const unsigned char *)p+104)!=expected[5])return 1;
if(raw_word((const unsigned char *)p+112)!=expected[6])return 1;
if(raw_word((const unsigned char *)p+120)!=expected[7])return 1;
}
{const uint64_t *expected=expected_dictionary+8*(unsigned)ids[2];
if(raw_word((const unsigned char *)p+128)!=expected[0])return 1;
if(raw_word((const unsigned char *)p+136)!=expected[1])return 1;
if(raw_word((const unsigned char *)p+144)!=expected[2])return 1;
if(raw_word((const unsigned char *)p+152)!=expected[3])return 1;
if(raw_word((const unsigned char *)p+160)!=expected[4])return 1;
if(raw_word((const unsigned char *)p+168)!=expected[5])return 1;
if(raw_word((const unsigned char *)p+176)!=expected[6])return 1;
if(raw_word((const unsigned char *)p+184)!=expected[7])return 1;
}
{const uint64_t *expected=expected_dictionary+8*(unsigned)ids[3];
if(raw_word((const unsigned char *)p+192)!=expected[0])return 1;
if(raw_word((const unsigned char *)p+200)!=expected[1])return 1;
if(raw_word((const unsigned char *)p+208)!=expected[2])return 1;
if(raw_word((const unsigned char *)p+216)!=expected[3])return 1;
if(raw_word((const unsigned char *)p+224)!=expected[4])return 1;
if(raw_word((const unsigned char *)p+232)!=expected[5])return 1;
if(raw_word((const unsigned char *)p+240)!=expected[6])return 1;
if(raw_word((const unsigned char *)p+248)!=expected[7])return 1;
}
{const uint64_t *expected=expected_dictionary+8*(unsigned)ids[4];
if(raw_word((const unsigned char *)p+256)!=expected[0])return 1;
if(raw_word((const unsigned char *)p+264)!=expected[1])return 1;
}
return 0;}
