#include <stdint.h>
#include <sys/resource.h>

#if DATA_BITS == 16
typedef uint16_t data_type;
#elif DATA_BITS == 32
typedef uint32_t data_type;
#elif DATA_BITS == 64
typedef uint64_t data_type;
#else
#error Unsupported data width
#endif
#if INDEX_BITS == 32
typedef uint32_t index_type;
#elif INDEX_BITS == 64
typedef uint64_t index_type;
#else
#error Unsupported index width
#endif
extern long gather32(const index_type *, const void *, data_type *, long);
extern long masked_restart32(const index_type *, const void *, data_type *);
static uint32_t pages[32768] __attribute__((aligned(4096)));
static data_type output[34];
static index_type indices[32];
static struct rusage usage;
static uint64_t faults;
static data_type expected(index_type offset) {
    const unsigned char *p = (const unsigned char *)pages + offset;
    uint64_t value = 0;
    for (unsigned i = 0; i < sizeof(data_type); ++i)
        value |= (uint64_t)p[i] << (8*i);
    return (data_type)value;
}

static long call(long n, long x, long y, long z, long u, long v, long w) {
    register long a0 __asm__("a0") = x;
    register long a1 __asm__("a1") = y;
    register long a2 __asm__("a2") = z;
    register long a3 __asm__("a3") = u;
    register long a4 __asm__("a4") = v;
    register long a5 __asm__("a5") = w;
    register long a7 __asm__("a7") = n;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3),
                     "r"(a4), "r"(a5), "r"(a7) : "memory");
    return a0;
}
static void text(const char *s) {
    long n = 0;
    while (s[n]) ++n;
    call(64, 1, (long)s, n, 0, 0, 0);
}
static void number(uint64_t n) {
    char b[24];
    int i = 23;
    b[i] = 0;
    do { b[--i] = '0' + n % 10; n /= 10; } while (n);
    text(b+i);
}
static void quit(long code) {
    call(94, code, 0, 0, 0, 0, 0);
    for (;;) {}
}
static void fail(const char *s, long i, uint64_t wanted, uint64_t got) {
    text("VECTOR_FAIL "); text(s); text(" element="); number(i);
    text(" expected="); number(wanted); text(" actual="); number(got);
    text("\n"); quit(1);
}
void _start(void) {
    for (unsigned i = 0; i < 32768; ++i)
        pages[i] = (i * 7919u) ^ 0xa5a50f0fu;
    for (unsigned i = 0; i < 32; ++i)
        indices[i] = ((i * 13u + 7u) % 32u) * 4096u;
    output[0] = output[33] = 0x5b12;
#ifdef FAULT_PAGES
    long fd = call(279, (long)"vector-probe", 0, 0, 0, 0, 0);
    if (fd < 0) quit(2);
    if (call(64, fd, (long)pages, sizeof(pages), 0, 0, 0) != sizeof(pages)) quit(3);
#endif
    for (unsigned r = 0; r < 50; ++r) {
        const void *base = pages;
#ifdef FAULT_PAGES
        long mapped = call(222, 0, sizeof(pages), 1, 2, fd, 0);
        if (mapped < 0) quit(4);
        base = (void *)mapped;
#endif
#ifdef FAULT_PAGES
        if (call(165, 0, (long)&usage, 0, 0, 0, 0)) quit(8);
        long before = usage.ru_minflt;
#endif
        long vl = gather32(indices, base, output+1, OVERLAP);
#ifdef FAULT_PAGES
        if (call(165, 0, (long)&usage, 0, 0, 0, 0)) quit(8);
        if (usage.ru_minflt <= before) quit(9);
        faults += usage.ru_minflt - before;
#endif
        if (vl != 32) fail("VL", r, 32, vl);
        for (unsigned i = 0; i < 32; ++i) {
            data_type wanted = expected(indices[i]);
            if (output[i+1] != wanted) fail("gather", i, wanted, output[i+1]);
        }
        if (output[0] != 0x5b12 || output[33] != 0x5b12) quit(5);
#ifdef FAULT_PAGES
        if (call(215, (long)base, sizeof(pages), 0, 0, 0, 0)) quit(6);
#endif
    }
#ifndef FAULT_PAGES
    if (masked_restart32(indices, pages, output+1) != 32) quit(7);
    for (unsigned i = 0; i < 32; ++i) {
        data_type wanted = (i >= 7 && i < 17 && (i & 1))
            ? expected(indices[i]) : (data_type)-7;
        if (output[i+1] != wanted) fail("mask_tail_vstart", i, wanted, output[i+1]);
    }
#endif
    text("VECTOR_PASS loops=50 overlap="); number(OVERLAP);
    text(" data_bits="); number(DATA_BITS);
    text(" index_bits="); number(INDEX_BITS);
    text(" fault_pages=");
#ifdef FAULT_PAGES
    text("1 minor_faults="); number(faults); text("\n");
#else
    text("0 mask_tail_vstart=checked\n");
#endif
    quit(0);
}
