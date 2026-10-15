#ifndef REDSPECIAL_PACKED_H
#define REDSPECIAL_PACKED_H
#include <stdint.h>
#ifdef HOST_CHECK
#define SD(p,o,v) host_store((p),(o),(uint64_t)(v))
#define LD(p,o,v) ((v)=host_load((p),(o)))
#else
#define SD(p,o,v) __asm__ volatile("sd %0,%c1(%2)" : : "r"((uint64_t)(v)),"i"(o),"r"(p) : "memory")
#define LD(p,o,v) __asm__ volatile("ld %0,%c1(%2)" : "=r"(v) : "i"(o),"r"(p) : "memory")
#endif
#define STORES8(p,v) do { SD(p,0,v); SD(p,8,v); SD(p,16,v); SD(p,24,v); \
    SD(p,32,v); SD(p,40,v); SD(p,48,v); SD(p,56,v); } while(0)
#define STORES16(p,v) do { STORES8(p,v); SD(p,64,v); SD(p,72,v); \
    SD(p,80,v); SD(p,88,v); SD(p,96,v); SD(p,104,v); SD(p,112,v); SD(p,120,v); } while(0)

static inline void seed_initialize(void *p,uint16_t value) {
    uint64_t repeated=(uint64_t)value*UINT64_C(0x0001000100010001);
    STORES16(p,repeated);
}
static inline void mask_initialize(void *p,unsigned mode) {
    unsigned byte=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0x55:0x24;
    uint64_t repeated=(uint64_t)byte*UINT64_C(0x0101010101010101);
    STORES8(p,repeated);
}
static inline void output_initialize(void *p) {
    const uint64_t sentinel=UINT64_C(0x5b5b5b5b5b5b5b5b);
    STORES16(p,sentinel); SD(p,128,sentinel); SD(p,136,sentinel);
}
static inline unsigned packed_mismatch(const void *p,uint64_t bits,unsigned vl) {
    const uint64_t sentinel=UINT64_C(0x5b5b5b5b5b5b5b5b);
    uint64_t first=vl ? ((sentinel & ~UINT64_C(65535))|(bits & 65535)):sentinel;
    uint64_t value, differences=0;
#define CHECK_WORD(o,w) do { LD(p,o,value); differences|=value^(w); } while(0)
    CHECK_WORD(0,sentinel); CHECK_WORD(8,first);
    CHECK_WORD(16,sentinel); CHECK_WORD(24,sentinel);
    CHECK_WORD(32,sentinel); CHECK_WORD(40,sentinel);
    CHECK_WORD(48,sentinel); CHECK_WORD(56,sentinel);
    CHECK_WORD(64,sentinel); CHECK_WORD(72,sentinel);
    CHECK_WORD(80,sentinel); CHECK_WORD(88,sentinel);
    CHECK_WORD(96,sentinel); CHECK_WORD(104,sentinel);
    CHECK_WORD(112,sentinel); CHECK_WORD(120,sentinel);
    CHECK_WORD(128,sentinel); CHECK_WORD(136,sentinel);
#undef CHECK_WORD
    return differences != 0;
}
#endif
