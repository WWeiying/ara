#include <stdint.h>
#include <stddef.h>

volatile unsigned long replay_case;
volatile unsigned long replay_trap_record[4];

void *memcpy(void *destination, const void *source, size_t count) {
    unsigned char *d = destination;
    const unsigned char *s = source;
    for (size_t i = 0; i < count; ++i) d[i] = s[i];
    return destination;
}

#ifdef SPIKE_REFERENCE
volatile uint64_t tohost __attribute__((section(".tohost"), aligned(64)));
volatile uint64_t fromhost __attribute__((section(".tohost"), aligned(64)));
/* Keep diagnostics in RAM; Spike has neither Ara's UART nor its CTRL block. */
volatile unsigned long replay_log_count;
char replay_log[8192];
static void put_byte(uint8_t byte) {
    if (replay_log_count < sizeof(replay_log) - 1)
        replay_log[replay_log_count++] = byte;
}
#else
static void put_byte(uint8_t byte) {
    *(volatile uint8_t *)0xc0000000UL = byte;
}
#endif

void replay_text(const char *text) {
    while (*text) put_byte((uint8_t)*text++);
}

long replay_write(long number, long fd, long pointer, long length) {
    const char *bytes = (const char *)pointer;
    if (number != 64 || fd != 1 || length < 0) {
        replay_text("BOARD_REPLAY_SERVICE_FAIL\n");
        extern void replay_exit(long) __attribute__((noreturn));
        replay_exit(126);
    }
    for (long i = 0; i < length; ++i) put_byte((uint8_t)bytes[i]);
    return length;
}

static void hex(unsigned long value) {
    char text[17];
    for (unsigned i = 0; i < 16; ++i)
        text[i] = "0123456789abcdef"[(value >> (60 - 4 * i)) & 15];
    text[16] = 0;
    replay_text(text);
}

void replay_trap(unsigned long cause, unsigned long pc, unsigned long value) {
    replay_trap_record[0] = replay_case;
    replay_trap_record[1] = cause;
    replay_trap_record[2] = pc;
    replay_trap_record[3] = value;
    replay_text("BOARD_REPLAY_TRAP case="); hex(replay_case);
    replay_text(" mcause="); hex(cause);
    replay_text(" mepc="); hex(pc);
    replay_text(" mtval="); hex(value);
    replay_text("\n");
}

int replay_mismatch(unsigned long trial, unsigned long index,
                    unsigned long expected, unsigned long actual) {
    replay_text("BOARD_REPLAY_MISMATCH case="); hex(replay_case);
    replay_text(" trial="); hex(trial);
    replay_text(" index="); hex(index);
    replay_text(" expected="); hex(expected);
    replay_text(" actual="); hex(actual);
    replay_text("\n");
    return 1;
}
