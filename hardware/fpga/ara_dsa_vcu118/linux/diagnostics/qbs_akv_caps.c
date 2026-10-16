#include <stdint.h>

static void emit(const char *p, long n) {
    register long a0 asm("a0") = 1;
    register const char *a1 asm("a1") = p;
    register long a2 asm("a2") = n;
    register long a7 asm("a7") = 64;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
}

void _start(void) {
    const char hex[] = "0123456789abcdef";
    asm volatile("vsetivli zero, 1, e32, m1, ta, ma");
    for (unsigned mechanism = 0; mechanism < 2; ++mechanism) {
        for (unsigned index = 0; index < 4; ++index) {
            register uintptr_t a0 asm("a0") = index;
            if (mechanism) asm volatile(".word 0x0005455b" : "+r"(a0) : : "memory");
            else asm volatile(".word 0x0005155b" : "+r"(a0) : : "memory");
            uintptr_t value = a0;
            char line[] = "QBS0=0000000000000000\n";
            if (mechanism) { line[0] = 'A'; line[1] = 'K'; line[2] = 'V'; }
            line[3] += index;
            for (unsigned j = 0; j < 16; ++j) line[5+j] = hex[(value >> (60-4*j)) & 15];
            emit(line, sizeof(line)-1);
        }
    }
    emit("HALF_BEGIN\n", 11);
    asm volatile("li t0, 0x3c00\nfmv.h.x ft0, t0\nfadd.h ft0, ft0, ft0\n"
                 "vsetivli zero, 1, e16, m1, ta, ma\nvfmv.v.f v8, ft0\nvfadd.vv v8, v8, v8"
                 : : : "t0", "ft0", "v8", "memory");
    emit("HALF_OK\n", 8);
    register long a0 asm("a0") = 0;
    register long a7 asm("a7") = 93;
    asm volatile("ecall" : : "r"(a0), "r"(a7) : "memory");
    __builtin_unreachable();
}
