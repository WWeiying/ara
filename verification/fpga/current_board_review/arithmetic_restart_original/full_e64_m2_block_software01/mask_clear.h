/* Fixed128-byte scalar zeroing. Compiler fences emit no target instruction. */
#include <stdint.h>
static __attribute__((always_inline)) inline void initialize_mask_zero(void *p) {
    const uint64_t zero=0;
    __builtin_memcpy((unsigned char *)p+0,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+8,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+16,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+24,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+32,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+40,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+48,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+56,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+64,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+72,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+80,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+88,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+96,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+104,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+112,&zero,8);
    __asm__ __volatile__("" : : : "memory");
    __builtin_memcpy((unsigned char *)p+120,&zero,8);
    __asm__ __volatile__("" : : : "memory");
}
