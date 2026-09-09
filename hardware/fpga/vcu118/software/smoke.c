/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#include "qbs_abi.h"
#include "akv_abi.h"

static volatile uint8_t *const uart = (volatile uint8_t *)0x03002000u;
static void putc_uart(char c) {
    while (!(uart[5] & 0x20u)) {}
    uart[0] = (uint8_t)c;
}
static void puts_uart(const char *s) { while (*s) putc_uart(*s++); }
static void hex64(uint64_t v) {
    for (int i = 60; i >= 0; i -= 4) putc_uart("0123456789abcdef"[(v >> i) & 15u]);
}
static void value(const char *name, uint64_t v) {
    puts_uart(name); hex64(v); puts_uart("\r\n");
}
static uint64_t qbs_info(uint64_t index) {
    uint64_t result;
    __asm__ volatile(".insn r 0x5b, 1, 0, %0, %1, x0" : "=r"(result) : "r"(index) : "memory");
    return result;
}
static uint64_t akv_info(uint64_t index) {
    uint64_t result;
    __asm__ volatile(".insn r 0x5b, 4, 0, %0, %1, x0" : "=r"(result) : "r"(index) : "memory");
    return result;
}
_Static_assert(QBS_QBINFO_FUNCT3 == 1 && AKV_INFO_FUNCT3 == 4, "Update smoke encodings");

static uint32_t a[67] __attribute__((aligned(128)));
static uint32_t b[67] __attribute__((aligned(128)));
static uint32_t c[67] __attribute__((aligned(128)));
static volatile uint64_t memory_check[2048] __attribute__((aligned(128)));

void report_trap(uint64_t cause, uint64_t pc, uint64_t tval) {
    puts_uart("\r\nSMOKE TRAP\r\n");
    value("mcause=", cause); value("mepc=", pc); value("mtval=", tval);
}

int main(void) {
    /* Reinitialize 16550 UART for the fixed 50 MHz board configuration. */
    uart[1] = 0; uart[3] = 0x80; uart[0] = 27; uart[1] = 0;
    uart[3] = 3; uart[2] = 7; uart[4] = 0;
    puts_uart("\r\nAra DSA VCU118 smoke\r\n");
    for (unsigned i = 0; i < 2048; ++i) memory_check[i] = UINT64_C(0x9e3779b97f4a7c15) ^ i;
    __asm__ volatile("fence rw,rw" ::: "memory");
    for (unsigned i = 0; i < 2048; ++i) {
        if (memory_check[i] != (UINT64_C(0x9e3779b97f4a7c15) ^ i)) {
            puts_uart("SMOKE FAIL memory\r\n"); return 1;
        }
    }
    uint64_t vlenb;
    __asm__ volatile("csrr %0, vlenb" : "=r"(vlenb));
    value("vlenb=", vlenb);
    if (vlenb != 128) { puts_uart("SMOKE FAIL VLEN\r\n"); return 2; }
    for (unsigned i = 0; i < 67; ++i) { a[i] = i * 17u; b[i] = i ^ 0x1234u; }
    unsigned offset = 0;
    while (offset < 67) {
        unsigned long vl;
        __asm__ volatile(
            "vsetvli %0, %4, e32, m1, ta, ma\n"
            "vle32.v v0, (%1)\n"
            "vle32.v v1, (%2)\n"
            "vadd.vv v2, v0, v1\n"
            "vse32.v v2, (%3)\n"
            : "=&r"(vl) : "r"(a + offset), "r"(b + offset), "r"(c + offset),
              "r"((unsigned long)(67 - offset)) : "v0", "v1", "v2", "memory");
        offset += vl;
    }
    __asm__ volatile("fence rw,rw" ::: "memory");
    for (unsigned i = 0; i < 67; ++i) {
        if (c[i] != a[i] + b[i]) { value("SMOKE FAIL RVV index=", i); return 3; }
    }
    uint64_t q = qbs_info(0), k = akv_info(0), k2 = akv_info(2);
    value("QBINFO[0]=", q); value("AKVINFO[0]=", k); value("AKVINFO[2]=", k2);
    if (q != qbs_capability_word(0, 1024) || k != akv_capability_word(0, 1) ||
        k2 != akv_v2_capability_word(2, 1)) {
        puts_uart("SMOKE FAIL capabilities\r\n"); return 4;
    }
    puts_uart("SMOKE PASS: small RAM, RVV integer, QBS/AKV capabilities\r\n");
    puts_uart("QBS/AKV arithmetic and full DDR tests still required.\r\n");
    return 0;
}
