#ifndef FIXED_HOST_API_H
#define FIXED_HOST_API_H
#include <stddef.h>
#include <stdint.h>
typedef struct {
    uint8_t *a, *b, *out, *mask;
    uint64_t checks, elements, errors;
} State;
int original_main(void);
int packed_main(void);
void original_reset(void);
void packed_reset(void);
State original_state(void);
State packed_state(void);
uint8_t original_value(unsigned, uint8_t, uint8_t, unsigned, unsigned *);
unsigned original_selected(unsigned, unsigned);
void original_seed(unsigned);
void original_mask(unsigned);
void source_note(char, unsigned, unsigned);
void *host_copy(void *, const void *, size_t);
unsigned packed_gold_byte(unsigned, unsigned);
unsigned packed_gold_sat(unsigned);
void packed_probe_init(uint8_t *);
unsigned packed_probe_check(unsigned, const uint8_t *);
#endif
