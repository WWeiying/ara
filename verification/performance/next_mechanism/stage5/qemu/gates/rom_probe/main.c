#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint64_t armed, epc, cause, tval, count, got_epc, got_cause, got_tval, status, fatal;
} trap_state;
volatile trap_state gate_traps;
_Static_assert(sizeof(trap_state) == 80 && offsetof(trap_state, got_epc) == 40,
               "Sealed trap-handler offsets");
extern void rom_full(uint64_t, uint64_t);
extern const unsigned char rom_full_pc[];

static void byte(char c) { *(volatile unsigned char *)(uintptr_t)0xc0000000 = (unsigned char)c; }
static void text(const char *s) { while (*s) byte(*s++); }
static void field(const char *name, uint64_t value, unsigned base)
{
    char digits[24]; unsigned n = 0;
    byte(' '); text(name); byte('=');
    do { digits[n++] = "0123456789abcdef"[value % base]; value /= base; } while (value);
    while (n) byte(digits[--n]);
}
static void csrs(uint64_t values[5])
{
    __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart\ncsrr %3,vl\ncsrr %4,vtype"
        : "=r"(values[0]), "=r"(values[1]), "=r"(values[2]), "=r"(values[3]), "=r"(values[4]) :: "memory");
}

int main(void)
{
    uint64_t before[5], after[5], status;
    __asm__ volatile("vsetivli zero,0,e16,m1,ta,ma\ncsrwi fcsr,8\ncsrwi vcsr,5\ncsrwi vstart,0\ncsrr %0,mstatus"
                     : "=r"(status) :: "memory");
    csrs(before);
    gate_traps.epc = (uintptr_t)rom_full_pc;
    gate_traps.cause = 5;
    gate_traps.tval = 0x1000;
    gate_traps.armed = 1;
    text("ROM_BEGIN"); field("pc", (uintptr_t)rom_full_pc, 16);
    field("address", 0x1000, 16); field("insn", 0x00b5605b, 16); field("mstatus", status, 16); byte('\n');
    rom_full(0x1000, 0);
    csrs(after);
    uint64_t errors = gate_traps.count != 1 || gate_traps.armed || gate_traps.fatal ||
        gate_traps.got_epc != (uintptr_t)rom_full_pc || gate_traps.got_cause != 5 || gate_traps.got_tval != 0x1000;
    errors += !(status & 0x6000) || !(status & 0x600);
    const uint64_t expected[5] = {8, 5, 0, 0, 0xc8};
    for (unsigned i = 0; i < 5; ++i) errors += before[i] != expected[i] || after[i] != expected[i];
    text("ROM_TRAP"); field("pc", gate_traps.got_epc, 16); field("cause", gate_traps.got_cause, 10);
    field("tval", gate_traps.got_tval, 16); field("count", gate_traps.count, 10); field("fatal", gate_traps.fatal, 10); byte('\n');
    text("ROM_CSR");
    const char *const names[10] = {"before_fcsr", "after_fcsr", "before_vcsr", "after_vcsr", "before_vstart",
        "after_vstart", "before_vl", "after_vl", "before_vtype", "after_vtype"};
    for (unsigned i = 0; i < 5; ++i) { field(names[i * 2], before[i], 10); field(names[i * 2 + 1], after[i], 10); }
    byte('\n');
    text("ROM_DONE"); field("traps", gate_traps.count, 10); field("errors", errors, 10); byte('\n');
    return errors != 0;
}
