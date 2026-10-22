#include <stdint.h>
#include "context.inc"

#define READ(c, x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c, x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
#define VA UINT64_C(0x40000000)
#ifndef FAULT_ELEMENT
#define FAULT_ELEMENT 0
#endif
#define FAULT_PAGE ((FAULT_ELEMENT * 13u + 7u) % 32u)
extern long gather32(const uint64_t *, const void *, uint32_t *, long);
extern void io_handler(void), io_enter_s(uint64_t, uint64_t);
extern void replay_text(const char *);

/* Loaded by the ELF preloader, not a long scalar BSS clearing loop. */
uint32_t pages[32768] __attribute__((aligned(4096))) = {1};
uint64_t indices[32] __attribute__((aligned(128)));
uint32_t output[34] __attribute__((aligned(128)));
volatile uint64_t pt[3][512] __attribute__((aligned(4096)));
volatile uint64_t records[4][7], faults, errors, done, target_pc;
volatile uint64_t first_expected, first_actual;
unsigned char context_data[4096] __attribute__((aligned(128)));
struct vstate context_state;

static void hex(uint64_t value) {
    char text[17];
    for (unsigned i = 0; i < 16; ++i)
        text[i] = "0123456789abcdef"[(value >> (60 - i * 4)) & 15];
    text[16] = 0;
    replay_text(text);
}
static void field(const char *name, uint64_t value) {
    replay_text(name); hex(value);
}
static void check(uint64_t actual, uint64_t expected) {
    if (actual != expected) {
        if (!errors) { first_expected = expected; first_actual = actual; }
        ++errors;
    }
}
static uint64_t leaf(unsigned p) {
    return (((uint64_t)pages + p * 4096) >> 12 << 10) | 0xc3;
}

/* Scalar-only in CONTEXT=0: no reload of indices or vector CSR reconstruction. */
int io_trap(uint64_t *x) {
    uint64_t cause, pc, tval, vs, vl, vt, vc, fc;
    READ(mcause, cause); READ(mepc, pc); READ(mtval, tval);
    READ(vstart, vs); READ(vl, vl); READ(vtype, vt);
    READ(vcsr, vc); READ(fcsr, fc);
    if (cause == 9 && x[17] == 94) {
        done = 1;
        check(x[10], 0);
        return 1;
    }
    unsigned n = faults++;
    replay_text("SYSTEM_FAULT");
    field(" n=", n); field(" cause=", cause); field(" pc=", pc);
    field(" tval=", tval); field(" vstart=", vs);
    field(" vl=", vl); field(" vtype=", vt); replay_text("\n");
    if (n < 4) {
        uint64_t values[7] = {cause, pc, tval, vs, vl, vt, vc};
        for (unsigned j = 0; j < 7; ++j) records[n][j] = values[j];
    }
    check(cause, 13); check(n, 0); check(vs, FAULT_ELEMENT); check(vl, 32);
    check(vt, 16); check(vc, 5); check(fc, 117);
    check(tval, VA + FAULT_PAGE * 4096u);
    const volatile unsigned char *bytes = (const volatile unsigned char *)pc;
    uint32_t word = 0;
    for (unsigned j = 0; j < 4; ++j) word |= (uint32_t)bytes[j] << (8 * j);
    check(word, OVERLAP ? 0x0625f107 : 0x0625f407);
    if (errors || !FAULT) return 1;
    target_pc = pc;
#if CONTEXT
    linux_save(&context_state, context_data);
#if CONTEXT_DIAG
    asm volatile("fence rw,rw" : : : "memory");
    for (unsigned i = 0; i < 32; ++i) {
        uint64_t saved = ((volatile uint64_t *)context_data)[32 + i];
        if (saved != indices[i] || i < 4) {
            replay_text("CONTEXT_SAVED_INDEX");
            field(" i=", i); field(" actual=", saved);
            field(" expected=", indices[i]); replay_text("\n");
        }
    }
#endif
    linux_restore(&context_state, context_data);
    asm volatile("li t0,0x600\ncsrs sstatus,t0" : : : "t0", "memory");
    check(context_state.vstart, FAULT_ELEMENT); check(context_state.vl, 32);
    check(context_state.vtype, 16); check(context_state.vcsr, 5);
    check(context_state.vlenb, 128);
#endif
    pt[2][FAULT_PAGE] = leaf(FAULT_PAGE);
    asm volatile("fence rw,rw\n.global system_repair_sfence\n"
                 "system_repair_sfence:\nsfence.vma %0,zero"
                 : : "r"(tval) : "memory");
    return 0;
}

void original_start(void) {
    long vl = gather32(indices, (const void *)VA, output + 1, OVERLAP);
    check(vl, 32);
    for (unsigned i = 0; i < 32; ++i) {
        uint32_t expected = ((uint32_t)(indices[i] / 4) * 7919u) ^ 0xa5a50f0fu;
        check(output[i + 1], expected);
    }
    check(output[0], 0x7ac95b12); check(output[33], 0x7ac95b12);
    uint64_t vs; READ(vstart, vs); check(vs, 0);
    asm volatile("li a7,94\nli a0,0\necall" : : : "a0", "a7", "memory");
    for (;;) {}
}

int main(void) {
    uint64_t status; READ(mstatus, status);
    WRITE(mie, 0); WRITE(medeleg, 0); WRITE(mideleg, 0);
    WRITE(fcsr, 117); WRITE(vcsr, 5); WRITE(vstart, 0);
    WRITE(mtvec, io_handler);
    for (unsigned i = 0; i < 32; ++i) {
        indices[i] = ((i * 13u + 7u) % 32u) * 4096u;
        pages[i * 1024] = (i * 1024u * 7919u) ^ 0xa5a50f0fu;
        pt[2][i] = FAULT && i == FAULT_PAGE ? 0 : leaf(i);
    }
    output[0] = output[33] = 0x7ac95b12;
    pt[0][1] = ((uint64_t)pt[1] >> 12 << 10) | 1;
    pt[0][2] = 0x200000cf;
    pt[1][0] = ((uint64_t)pt[2] >> 12 << 10) | 1;
    uint64_t satp = (UINT64_C(8) << 60) | ((uint64_t)pt[0] >> 12);
    replay_text("SYSTEM_BEGIN\n");
    io_enter_s((status & ~UINT64_C(0x8000031888)) | 0x2a00, satp);
    WRITE(satp, 0); asm volatile("sfence.vma zero,zero" : : : "memory");
    check(done, 1); check(faults, FAULT);
    replay_text(errors ? "SYSTEM_FAIL" : "SYSTEM_PASS");
    field(" faults=", faults); field(" errors=", errors);
    field(" overlap=", OVERLAP); field(" context=", CONTEXT); replay_text("\n");
    if (errors) {
        replay_text("SYSTEM_FIRST_MISMATCH");
        field(" expected=", first_expected); field(" actual=", first_actual);
        replay_text("\n");
    }
    return errors != 0;
}
