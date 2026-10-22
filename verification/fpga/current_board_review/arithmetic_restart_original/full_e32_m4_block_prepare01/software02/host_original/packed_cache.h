#ifndef E32M4_INTEGRATED_PACKED_CACHE_H
#define E32M4_INTEGRATED_PACKED_CACHE_H
#include <stdint.h>

extern const uint64_t e32m4_expected_blocks[2252][8];
extern const uint16_t e32m4_expected_ids[5985][9];

/* The empty volatile asm consumes every real read, including after a mismatch. */
static __attribute__((always_inline)) inline uint64_t
e32m4_actual8(const unsigned char *p)
{
    uint64_t value;
    if(running && fault==32 && p==actual_base+16)return UINT64_C(0x0000005b0000005b);
    __builtin_memcpy(&value, p, 8);
    __asm__ volatile ("" : "+r"(value) : : "memory");
    actual_event(p,value);
    return value;
}

static __attribute__((always_inline)) inline uint64_t
e32m4_gold8(const uint64_t *p)
{
    uint64_t value;
    __builtin_memcpy(&value, p, 8);
    if(running && fault==27)value^=1;
    gold_event(p,value);
    return value;
}

static __attribute__((noinline)) void e32m4_initialize_output(void *out)
{
    const uint64_t sentinel = UINT64_C(0x0000005b0000005b);
    unsigned char *const p = out;
    if(!(running && fault==35 && calls==1 && 0==8)){__builtin_memcpy(p + 0, &sentinel, 8);init_event(0,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 8==8)){__builtin_memcpy(p + 8, &sentinel, 8);init_event(8,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 16==8)){__builtin_memcpy(p + 16, &sentinel, 8);init_event(16,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 24==8)){__builtin_memcpy(p + 24, &sentinel, 8);init_event(24,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 32==8)){__builtin_memcpy(p + 32, &sentinel, 8);init_event(32,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 40==8)){__builtin_memcpy(p + 40, &sentinel, 8);init_event(40,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 48==8)){__builtin_memcpy(p + 48, &sentinel, 8);init_event(48,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 56==8)){__builtin_memcpy(p + 56, &sentinel, 8);init_event(56,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 64==8)){__builtin_memcpy(p + 64, &sentinel, 8);init_event(64,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 72==8)){__builtin_memcpy(p + 72, &sentinel, 8);init_event(72,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 80==8)){__builtin_memcpy(p + 80, &sentinel, 8);init_event(80,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 88==8)){__builtin_memcpy(p + 88, &sentinel, 8);init_event(88,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 96==8)){__builtin_memcpy(p + 96, &sentinel, 8);init_event(96,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 104==8)){__builtin_memcpy(p + 104, &sentinel, 8);init_event(104,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 112==8)){__builtin_memcpy(p + 112, &sentinel, 8);init_event(112,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 120==8)){__builtin_memcpy(p + 120, &sentinel, 8);init_event(120,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 128==8)){__builtin_memcpy(p + 128, &sentinel, 8);init_event(128,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 136==8)){__builtin_memcpy(p + 136, &sentinel, 8);init_event(136,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 144==8)){__builtin_memcpy(p + 144, &sentinel, 8);init_event(144,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 152==8)){__builtin_memcpy(p + 152, &sentinel, 8);init_event(152,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 160==8)){__builtin_memcpy(p + 160, &sentinel, 8);init_event(160,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 168==8)){__builtin_memcpy(p + 168, &sentinel, 8);init_event(168,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 176==8)){__builtin_memcpy(p + 176, &sentinel, 8);init_event(176,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 184==8)){__builtin_memcpy(p + 184, &sentinel, 8);init_event(184,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 192==8)){__builtin_memcpy(p + 192, &sentinel, 8);init_event(192,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 200==8)){__builtin_memcpy(p + 200, &sentinel, 8);init_event(200,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 208==8)){__builtin_memcpy(p + 208, &sentinel, 8);init_event(208,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 216==8)){__builtin_memcpy(p + 216, &sentinel, 8);init_event(216,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 224==8)){__builtin_memcpy(p + 224, &sentinel, 8);init_event(224,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 232==8)){__builtin_memcpy(p + 232, &sentinel, 8);init_event(232,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 240==8)){__builtin_memcpy(p + 240, &sentinel, 8);init_event(240,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 248==8)){__builtin_memcpy(p + 248, &sentinel, 8);init_event(248,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 256==8)){__builtin_memcpy(p + 256, &sentinel, 8);init_event(256,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 264==8)){__builtin_memcpy(p + 264, &sentinel, 8);init_event(264,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 272==8)){__builtin_memcpy(p + 272, &sentinel, 8);init_event(272,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 280==8)){__builtin_memcpy(p + 280, &sentinel, 8);init_event(280,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 288==8)){__builtin_memcpy(p + 288, &sentinel, 8);init_event(288,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 296==8)){__builtin_memcpy(p + 296, &sentinel, 8);init_event(296,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 304==8)){__builtin_memcpy(p + 304, &sentinel, 8);init_event(304,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 312==8)){__builtin_memcpy(p + 312, &sentinel, 8);init_event(312,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 320==8)){__builtin_memcpy(p + 320, &sentinel, 8);init_event(320,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 328==8)){__builtin_memcpy(p + 328, &sentinel, 8);init_event(328,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 336==8)){__builtin_memcpy(p + 336, &sentinel, 8);init_event(336,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 344==8)){__builtin_memcpy(p + 344, &sentinel, 8);init_event(344,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 352==8)){__builtin_memcpy(p + 352, &sentinel, 8);init_event(352,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 360==8)){__builtin_memcpy(p + 360, &sentinel, 8);init_event(360,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 368==8)){__builtin_memcpy(p + 368, &sentinel, 8);init_event(368,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 376==8)){__builtin_memcpy(p + 376, &sentinel, 8);init_event(376,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 384==8)){__builtin_memcpy(p + 384, &sentinel, 8);init_event(384,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 392==8)){__builtin_memcpy(p + 392, &sentinel, 8);init_event(392,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 400==8)){__builtin_memcpy(p + 400, &sentinel, 8);init_event(400,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 408==8)){__builtin_memcpy(p + 408, &sentinel, 8);init_event(408,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 416==8)){__builtin_memcpy(p + 416, &sentinel, 8);init_event(416,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 424==8)){__builtin_memcpy(p + 424, &sentinel, 8);init_event(424,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 432==8)){__builtin_memcpy(p + 432, &sentinel, 8);init_event(432,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 440==8)){__builtin_memcpy(p + 440, &sentinel, 8);init_event(440,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 448==8)){__builtin_memcpy(p + 448, &sentinel, 8);init_event(448,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 456==8)){__builtin_memcpy(p + 456, &sentinel, 8);init_event(456,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 464==8)){__builtin_memcpy(p + 464, &sentinel, 8);init_event(464,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 472==8)){__builtin_memcpy(p + 472, &sentinel, 8);init_event(472,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 480==8)){__builtin_memcpy(p + 480, &sentinel, 8);init_event(480,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 488==8)){__builtin_memcpy(p + 488, &sentinel, 8);init_event(488,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 496==8)){__builtin_memcpy(p + 496, &sentinel, 8);init_event(496,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 504==8)){__builtin_memcpy(p + 504, &sentinel, 8);init_event(504,p);}
    __asm__ volatile ("" ::: "memory");
    if(!(running && fault==35 && calls==1 && 512==8)){__builtin_memcpy(p + 512, &sentinel, 8);init_event(512,p);}
    __asm__ volatile ("" ::: "memory");
}

#define E32M4_CACHE_FILL(ID) do { \
    const uint64_t *const block = blocks[(ID)]; \
    c0 = e32m4_gold8(block + 0); \
    c1 = e32m4_gold8(block + 1); \
    c2 = e32m4_gold8(block + 2); \
    c3 = e32m4_gold8(block + 3); \
    c4 = e32m4_gold8(block + 4); \
    c5 = e32m4_gold8(block + 5); \
    c6 = e32m4_gold8(block + 6); \
    c7 = e32m4_gold8(block + 7); \
    tag = (ID); if(running && fault==28)tag^=1; tag_event(tag,(ID)); \
} while (0)

/* Same BEQ/LI sticky contract as the reviewed e64/m4 scalar comparator. */
#if defined(__riscv) && __riscv_xlen != 64
#error "This comparator requires RV64"
#endif

#if defined(__riscv)
#define E32M4_STICKY_UPDATE(ACTUAL_VALUE, WANTED_VALUE) do { \
    const uint64_t actual_value = (ACTUAL_VALUE); \
    const uint64_t wanted_value = (WANTED_VALUE); \
    __asm__ volatile( \
        "beq %[actual], %[wanted], 1f\n\t" \
        "li %[bad], 1\n\t" \
        "1:\n\t" \
        : [bad] "+r" (mismatch) \
        : [actual] "r" (actual_value), [wanted] "r" (wanted_value) \
        : "memory"); \
} while (0)
#else
#define E32M4_STICKY_UPDATE(ACTUAL_VALUE, WANTED_VALUE) do { \
    if ((ACTUAL_VALUE) != (WANTED_VALUE)) mismatch = 1; \
} while (0)
#endif

/* Each condition may latch failure, but none bypasses a later actual read. */
#define E32M4_COMPARE_BLOCK(OFFSET) do { \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 0), c0); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 8), c1); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 16), c2); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 24), c3); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 32), c4); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 40), c5); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 48), c6); \
    E32M4_STICKY_UPDATE(e32m4_actual8(p + (OFFSET) + 56), c7); \
} while (0)

#define E32M4_NEXT_BLOCK(INDEX) do { \
    const uint16_t id = ids[(INDEX)]; id_event((INDEX),id); \
    if ((id != tag && !(running && fault==30)) || (running && fault==31)) E32M4_CACHE_FILL(id); \
    E32M4_COMPARE_BLOCK(64 * (INDEX)); \
} while (0)

static __attribute__((noinline)) unsigned
e32m4_packed_mismatch(const void *out, const uint16_t ids[9],
                      const uint64_t blocks[2252][8])
{
    const unsigned char *const p = out;
    uint64_t c0=UINT64_C(0x5b0000005b),c1=c0,c2=c0,c3=c0,c4=c0,c5=c0,c6=c0,c7=c0;
    uint16_t tag=0;
    unsigned mismatch = 0;
    cache_begin(out,ids);
    const uint16_t first_id = ids[0]; id_event(0,first_id);

    /* Unconditional first fill invalidates any previous call's cache state. */
    if(!(running && fault==29 && calls==2)) E32M4_CACHE_FILL(first_id);
    E32M4_COMPARE_BLOCK(0);
    if(running && fault==33 && mismatch){cache_end();return mismatch;}
    E32M4_NEXT_BLOCK(1);
    E32M4_NEXT_BLOCK(2);
    E32M4_NEXT_BLOCK(3);
    E32M4_NEXT_BLOCK(4);
    E32M4_NEXT_BLOCK(5);
    E32M4_NEXT_BLOCK(6);
    E32M4_NEXT_BLOCK(7);

    const uint16_t last_id = ids[8]; id_event(8,last_id);
    const uint64_t last = e32m4_gold8(blocks[last_id]);
    E32M4_STICKY_UPDATE(e32m4_actual8(p + 512), last);
    cache_end();
    return mismatch;
}

#undef E32M4_STICKY_UPDATE
#undef E32M4_NEXT_BLOCK
#undef E32M4_COMPARE_BLOCK
#undef E32M4_CACHE_FILL
#endif

