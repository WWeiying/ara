#ifndef ARA_RESIDENT_BUFFER_POOL_H
#define ARA_RESIDENT_BUFFER_POOL_H

#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <stddef.h>
#endif

struct ara_resident_buffer {
    void *allocation, *data;
    size_t capacity;
};

/* Caller holds the accelerator lock. Failed growth preserves the old buffer. */
static inline int ara_resident_buffer_reserve(struct ara_resident_buffer *b,
        size_t bytes, size_t limit, void *(*allocate)(size_t), void (*release)(const void *))
{
    void *raw;
    if (!bytes || bytes > limit || bytes > (size_t)-1 - 63) return 0;
    if (bytes <= b->capacity) return 1;
    raw = allocate(bytes + 63);
    if (!raw) return 0;
    release(b->allocation);
    b->allocation = raw;
    b->data = (void *)(((unsigned long)raw + 63) & ~63UL);
    b->capacity = bytes;
    return 1;
}

#endif
