#include "../ethernet/firmware/eth_loader_core.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct mock {
    uint8_t input[256], output[256], ddr[64];
    size_t input_size, input_pos, output_size;
    unsigned writes;
    int corrupt_readback;
};

static void put32(uint8_t *bytes, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) bytes[i] = (uint8_t)(value >> (i * 8));
}

static void put64(uint8_t *bytes, uint64_t value) {
    put32(bytes, (uint32_t)value);
    put32(bytes + 4, (uint32_t)(value >> 32));
}

static uint32_t get32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
           (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static int receive(void *context, void *data, size_t n) {
    struct mock *m = context;
    if (n > m->input_size - m->input_pos) return -1;
    memcpy(data, m->input + m->input_pos, n);
    m->input_pos += n;
    return 0;
}

static int send_data(void *context, const void *data, size_t n) {
    struct mock *m = context;
    if (n > sizeof(m->output) - m->output_size) return -1;
    memcpy(m->output + m->output_size, data, n);
    m->output_size += n;
    return 0;
}

static int write_ddr(void *context, uint64_t address, const void *data, size_t n) {
    struct mock *m = context;
    size_t offset = (size_t)(address - UINT64_C(0x80000000));
    if (offset > sizeof(m->ddr) || n > sizeof(m->ddr) - offset) return -1;
    memcpy(m->ddr + offset, data, n);
    ++m->writes;
    return 0;
}

static int readback_crc32(void *context, uint64_t address, size_t n, uint32_t *crc) {
    struct mock *m = context;
    size_t offset = (size_t)(address - UINT64_C(0x80000000));
    if (offset > sizeof(m->ddr) || n > sizeof(m->ddr) - offset) return -1;
    *crc = eth_loader_crc32(m->ddr + offset, n) ^ (unsigned)m->corrupt_readback;
    return 0;
}

static const struct eth_loader_io io = {receive, send_data, write_ddr, readback_crc32};

static void append_record(struct mock *m, const char *opcode, uint64_t address,
                          const void *data, uint32_t length, uint32_t crc) {
    uint8_t *record = m->input + m->input_size;
    assert(m->input_size + 20 + length <= sizeof(m->input));
    memcpy(record, opcode, 4);
    put64(record + 4, address);
    put32(record + 12, length);
    put32(record + 16, crc);
    m->input_size += 20;
    if (length) {
        memcpy(m->input + m->input_size, data, length);
        m->input_size += length;
    }
}

static void init(struct mock *m) {
    memset(m, 0, sizeof(*m));
    memcpy(m->input, "ARAETH01", 8);
    m->input_size = 8;
}

int main(void) {
    struct mock m;
    uint8_t scratch[32];
    const uint8_t payload[] = {1, 2, 3, 4, 5, 6};
    const uint32_t crc = eth_loader_crc32(payload, sizeof(payload));

    assert(eth_loader_crc32("123456789", 9) == UINT32_C(0xcbf43926));
    init(&m);
    append_record(&m, "DATA", UINT64_C(0x80000008), payload, sizeof(payload), crc);
    append_record(&m, "DONE", UINT64_C(0x80000008), NULL, 0, 0);
    assert(eth_loader_receive(&io, &m, scratch, sizeof(scratch)) == 0);
    assert(m.writes == 1 && memcmp(m.ddr + 8, payload, sizeof(payload)) == 0);
    assert(m.output_size == 16 + 16 + 16);
    assert(memcmp(m.output, "ARAETH01", 8) == 0 && get32(m.output + 8) == 1);
    assert(get32(m.output + 12) == sizeof(scratch));
    assert(get32(m.output + 16 + 8) == crc && get32(m.output + 16 + 12) == 0);
    assert(get32(m.output + 32 + 12) == 0);

    init(&m);
    append_record(&m, "DATA", UINT64_C(0x80000008), payload, sizeof(payload), crc ^ 1);
    assert(eth_loader_receive(&io, &m, scratch, sizeof(scratch)) == -9);
    assert(m.writes == 0 && get32(m.output + 16 + 12) == 2);

    init(&m);
    append_record(&m, "DATA", UINT64_C(0x80000008), payload, sizeof(payload), crc);
    m.corrupt_readback = 1;
    assert(eth_loader_receive(&io, &m, scratch, sizeof(scratch)) == -12);
    assert(m.writes == 1 && get32(m.output + 16 + 12) == 4);

    init(&m);
    append_record(&m, "DATA", UINT64_C(0xfffffffc), payload, sizeof(payload), crc);
    assert(eth_loader_receive(&io, &m, scratch, sizeof(scratch)) == -7);
    assert(m.writes == 0 && get32(m.output + 16 + 12) == 1);

    init(&m);
    append_record(&m, "DATA", UINT64_C(0x80000008), payload, sizeof(payload), crc);
    append_record(&m, "DATA", UINT64_C(0x80000009), payload, sizeof(payload), crc);
    assert(eth_loader_receive(&io, &m, scratch, sizeof(scratch)) == -7);
    assert(m.writes == 1 && get32(m.output + 32 + 12) == 1);

    puts("eth_loader_core_test PASS");
    return 0;
}
