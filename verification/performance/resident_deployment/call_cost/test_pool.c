#include "buffer_pool.h"
#include "sdk/finite_f16.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned allocations, frees;
static int fail;
static void *allocate(size_t n) { ++allocations; return fail ? NULL : malloc(n); }
static void release(const void *p) { if (p) ++frees; free((void *)p); }

int main(void) {
    struct ara_resident_buffer b = {0};
    assert(!ara_resident_buffer_reserve(&b, 0, 65536, allocate, release));
    assert(!ara_resident_buffer_reserve(&b, 65537, 65536, allocate, release));
    assert(!allocations);
    for (size_t n = 1; n <= 65536; n *= 2) {
        assert(ara_resident_buffer_reserve(&b, n, 65536, allocate, release));
        assert(!((uintptr_t)b.data & 63) && b.capacity == n);
        unsigned before = allocations;
        for (size_t i = 0; i < n; ++i) ((unsigned char *)b.data)[i] = (unsigned char)i;
        assert(ara_resident_buffer_reserve(&b, n / 2 + 1, 65536, allocate, release));
        assert(allocations == before);
        for (size_t i = 0; i < n; ++i) assert(((unsigned char *)b.data)[i] == (unsigned char)i);
    }
    void *old = b.data;
    fail = 1;
    assert(!ara_resident_buffer_reserve(&b, 65537, 131072, allocate, release));
    assert(b.data == old && b.capacity == 65536);
    assert(!ara_resident_buffer_reserve(&b, SIZE_MAX, SIZE_MAX, allocate, release));
    release(b.allocation);
    assert(allocations == frees + 1); // Includes the injected allocation failure.
    for (unsigned bits = 0; bits < 65536; ++bits) {
        uint16_t v = bits;
        assert(ara_resident_finite_f16(&v, 1) == ((bits & 0x7c00) != 0x7c00));
    }
    puts("PASS pool: aligned growth/reuse, failed growth preserves data, bounds/overflow; 65536 F16 encodings");
    return 0;
}
