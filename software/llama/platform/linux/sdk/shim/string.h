#ifndef ARA_KERNEL_STRING_H
#define ARA_KERNEL_STRING_H
#include <stddef.h>
void *memcpy(void *restrict dest, const void *restrict src, size_t bytes);
void *memset(void *dest, int value, size_t bytes);
int memcmp(const void *left, const void *right, size_t bytes);
#endif
