#include <stdint.h>

extern void run_epoch(void *);
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long, unsigned long, unsigned long, unsigned long);

static void hex(unsigned long value) {
    char text[17];
    for (unsigned i = 0; i < 16; ++i)
        text[i] = "0123456789abcdef"[(value >> (60 - 4 * i)) & 15];
    text[16] = 0;
    replay_text(text);
}

int CASE_MAIN(void) {
    struct {
        uint64_t flags;
        uint16_t first, second;
        uint32_t guard;
    } result = {0, 0, 0, 0x12345678};
    run_epoch(&result);
    replay_text("EPOCH_RESULT variant="); hex(VARIANT);
    replay_text(" flags="); hex(result.flags);
    replay_text(" first="); hex(result.first);
    replay_text(" second="); hex(result.second);
    replay_text("\n");
    int errors = 0;
    if (result.flags != 16)
        errors += replay_mismatch(VARIANT, 0, 16, result.flags);
    if (result.first != 0x7e00)
        errors += replay_mismatch(VARIANT, 1, 0x7e00, result.first);
    unsigned expected_second = VARIANT == 0 ? 0 : VARIANT == 1 ? 0x4000 : 0x3c00;
    if (result.second != expected_second)
        errors += replay_mismatch(VARIANT, 2, expected_second, result.second);
    if (result.guard != 0x12345678)
        errors += replay_mismatch(VARIANT, 3, 0x12345678, result.guard);
    if (!errors) replay_text("EPOCH_PASS\n");
    return errors != 0;
}
