/* Static e32/m2 candidate only: not compiled or executed.
 * Preconditions: CAP64, uint32_t inputs/output, seed0..2, mode0..2.
 * Empty compiler barriers emit no RISC-V fence or other instruction.
 */
#ifndef E32_M2_SCALAR_SETUP_H
#define E32_M2_SCALAR_SETUP_H
#include <stdint.h>

#define E32M2_BARRIER() __asm__ __volatile__("" : : : "memory")

static __attribute__((always_inline)) inline
void e32m2_seed_pattern(uint32_t q[8], const uint32_t inputs[8], unsigned seed) {
    for (unsigned k=0; k<8; ++k)
        q[k]=inputs[(seed+k)%8u];
}

/* Each macro has two separate ordered 32-bit stores. No restrict promise. */
#define E32M2_FP_PAIR(I) do { \
    {a[(I)]=q[(I)%8u];fp_store(0,(I),a[(I)]);} \
    E32M2_BARRIER(); \
    {b[(I)]=q[(3u*(I))%8u];fp_store(1,(I),b[(I)]);} \
    E32M2_BARRIER(); \
} while (0)

static __attribute__((always_inline)) inline
void e32m2_refresh_fp(uint32_t *a, uint32_t *b, const uint32_t q[8]) {
    E32M2_FP_PAIR(0u);
    E32M2_FP_PAIR(1u);
    E32M2_FP_PAIR(2u);
    E32M2_FP_PAIR(3u);
    E32M2_FP_PAIR(4u);
    E32M2_FP_PAIR(5u);
    E32M2_FP_PAIR(6u);
    E32M2_FP_PAIR(7u);
    E32M2_FP_PAIR(8u);
    E32M2_FP_PAIR(9u);
    E32M2_FP_PAIR(10u);
    E32M2_FP_PAIR(11u);
    E32M2_FP_PAIR(12u);
    E32M2_FP_PAIR(13u);
    E32M2_FP_PAIR(14u);
    E32M2_FP_PAIR(15u);
    E32M2_FP_PAIR(16u);
    E32M2_FP_PAIR(17u);
    E32M2_FP_PAIR(18u);
    E32M2_FP_PAIR(19u);
    E32M2_FP_PAIR(20u);
    E32M2_FP_PAIR(21u);
    E32M2_FP_PAIR(22u);
    E32M2_FP_PAIR(23u);
    E32M2_FP_PAIR(24u);
    E32M2_FP_PAIR(25u);
    E32M2_FP_PAIR(26u);
    E32M2_FP_PAIR(27u);
    E32M2_FP_PAIR(28u);
    E32M2_FP_PAIR(29u);
    E32M2_FP_PAIR(30u);
    E32M2_FP_PAIR(31u);
    E32M2_FP_PAIR(32u);
    E32M2_FP_PAIR(33u);
    E32M2_FP_PAIR(34u);
    E32M2_FP_PAIR(35u);
    E32M2_FP_PAIR(36u);
    E32M2_FP_PAIR(37u);
    E32M2_FP_PAIR(38u);
    E32M2_FP_PAIR(39u);
    E32M2_FP_PAIR(40u);
    E32M2_FP_PAIR(41u);
    E32M2_FP_PAIR(42u);
    E32M2_FP_PAIR(43u);
    E32M2_FP_PAIR(44u);
    E32M2_FP_PAIR(45u);
    E32M2_FP_PAIR(46u);
    E32M2_FP_PAIR(47u);
    E32M2_FP_PAIR(48u);
    E32M2_FP_PAIR(49u);
    E32M2_FP_PAIR(50u);
    E32M2_FP_PAIR(51u);
    E32M2_FP_PAIR(52u);
    E32M2_FP_PAIR(53u);
    E32M2_FP_PAIR(54u);
    E32M2_FP_PAIR(55u);
    E32M2_FP_PAIR(56u);
    E32M2_FP_PAIR(57u);
    E32M2_FP_PAIR(58u);
    E32M2_FP_PAIR(59u);
    E32M2_FP_PAIR(60u);
    E32M2_FP_PAIR(61u);
    E32M2_FP_PAIR(62u);
    E32M2_FP_PAIR(63u);
}

/* Every selected index performs its original cumulative byte update. */
#define E32M2_MASK_BIT(I) do { \
    mask[(I)/8u]=(uint8_t)(mask[(I)/8u] | (UINT32_C(1)<<((I)%8u))); mask_event(1,(I),mask); \
    E32M2_BARRIER(); \
} while (0)

static __attribute__((always_inline)) inline
void e32m2_initialize_mask(uint8_t mask[128], unsigned mode) {
    const uint64_t zero=0;
    __builtin_memcpy(mask+0,&zero,8); mask_event(0,0,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+8,&zero,8); mask_event(0,8,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+16,&zero,8); mask_event(0,16,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+24,&zero,8); mask_event(0,24,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+32,&zero,8); mask_event(0,32,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+40,&zero,8); mask_event(0,40,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+48,&zero,8); mask_event(0,48,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+56,&zero,8); mask_event(0,56,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+64,&zero,8); mask_event(0,64,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+72,&zero,8); mask_event(0,72,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+80,&zero,8); mask_event(0,80,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+88,&zero,8); mask_event(0,88,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+96,&zero,8); mask_event(0,96,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+104,&zero,8); mask_event(0,104,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+112,&zero,8); mask_event(0,112,mask);
    E32M2_BARRIER();
    __builtin_memcpy(mask+120,&zero,8); mask_event(0,120,mask);
    E32M2_BARRIER();
    if (mode==0) {
        E32M2_MASK_BIT(0u);
        E32M2_MASK_BIT(1u);
        E32M2_MASK_BIT(2u);
        E32M2_MASK_BIT(3u);
        E32M2_MASK_BIT(4u);
        E32M2_MASK_BIT(5u);
        E32M2_MASK_BIT(6u);
        E32M2_MASK_BIT(7u);
        E32M2_MASK_BIT(8u);
        E32M2_MASK_BIT(9u);
        E32M2_MASK_BIT(10u);
        E32M2_MASK_BIT(11u);
        E32M2_MASK_BIT(12u);
        E32M2_MASK_BIT(13u);
        E32M2_MASK_BIT(14u);
        E32M2_MASK_BIT(15u);
        E32M2_MASK_BIT(16u);
        E32M2_MASK_BIT(17u);
        E32M2_MASK_BIT(18u);
        E32M2_MASK_BIT(19u);
        E32M2_MASK_BIT(20u);
        E32M2_MASK_BIT(21u);
        E32M2_MASK_BIT(22u);
        E32M2_MASK_BIT(23u);
        E32M2_MASK_BIT(24u);
        E32M2_MASK_BIT(25u);
        E32M2_MASK_BIT(26u);
        E32M2_MASK_BIT(27u);
        E32M2_MASK_BIT(28u);
        E32M2_MASK_BIT(29u);
        E32M2_MASK_BIT(30u);
        E32M2_MASK_BIT(31u);
        E32M2_MASK_BIT(32u);
        E32M2_MASK_BIT(33u);
        E32M2_MASK_BIT(34u);
        E32M2_MASK_BIT(35u);
        E32M2_MASK_BIT(36u);
        E32M2_MASK_BIT(37u);
        E32M2_MASK_BIT(38u);
        E32M2_MASK_BIT(39u);
        E32M2_MASK_BIT(40u);
        E32M2_MASK_BIT(41u);
        E32M2_MASK_BIT(42u);
        E32M2_MASK_BIT(43u);
        E32M2_MASK_BIT(44u);
        E32M2_MASK_BIT(45u);
        E32M2_MASK_BIT(46u);
        E32M2_MASK_BIT(47u);
        E32M2_MASK_BIT(48u);
        E32M2_MASK_BIT(49u);
        E32M2_MASK_BIT(50u);
        E32M2_MASK_BIT(51u);
        E32M2_MASK_BIT(52u);
        E32M2_MASK_BIT(53u);
        E32M2_MASK_BIT(54u);
        E32M2_MASK_BIT(55u);
        E32M2_MASK_BIT(56u);
        E32M2_MASK_BIT(57u);
        E32M2_MASK_BIT(58u);
        E32M2_MASK_BIT(59u);
        E32M2_MASK_BIT(60u);
        E32M2_MASK_BIT(61u);
        E32M2_MASK_BIT(62u);
        if(calls!=0) E32M2_MASK_BIT(63u);
    } else if (mode==1) {
        E32M2_MASK_BIT(1u);
        E32M2_MASK_BIT(3u);
        E32M2_MASK_BIT(5u);
        E32M2_MASK_BIT(7u);
        E32M2_MASK_BIT(9u);
        E32M2_MASK_BIT(11u);
        E32M2_MASK_BIT(13u);
        E32M2_MASK_BIT(15u);
        E32M2_MASK_BIT(17u);
        E32M2_MASK_BIT(19u);
        E32M2_MASK_BIT(21u);
        E32M2_MASK_BIT(23u);
        E32M2_MASK_BIT(25u);
        E32M2_MASK_BIT(27u);
        E32M2_MASK_BIT(29u);
        E32M2_MASK_BIT(31u);
        E32M2_MASK_BIT(33u);
        E32M2_MASK_BIT(35u);
        E32M2_MASK_BIT(37u);
        E32M2_MASK_BIT(39u);
        E32M2_MASK_BIT(41u);
        E32M2_MASK_BIT(43u);
        E32M2_MASK_BIT(45u);
        E32M2_MASK_BIT(47u);
        E32M2_MASK_BIT(49u);
        E32M2_MASK_BIT(51u);
        E32M2_MASK_BIT(53u);
        E32M2_MASK_BIT(55u);
        E32M2_MASK_BIT(57u);
        E32M2_MASK_BIT(59u);
        E32M2_MASK_BIT(61u);
        if(calls!=0) E32M2_MASK_BIT(63u);
    } else if (mode==2) {
        E32M2_MASK_BIT(2u);
        E32M2_MASK_BIT(9u);
        E32M2_MASK_BIT(16u);
        E32M2_MASK_BIT(23u);
        E32M2_MASK_BIT(30u);
        E32M2_MASK_BIT(37u);
        E32M2_MASK_BIT(44u);
        E32M2_MASK_BIT(51u);
        E32M2_MASK_BIT(58u);
    }
}

#undef E32M2_MASK_BIT
#undef E32M2_FP_PAIR
#undef E32M2_BARRIER
#endif
