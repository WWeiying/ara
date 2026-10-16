#include "../ethernet/firmware/eth_loader_stream.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct memory {
    uint8_t bytes[128];
    unsigned writes;
    int corrupt;
};

static void put32(uint8_t *p, uint32_t n) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(n >> (8 * i));
}

static void put64(uint8_t *p, uint64_t n) {
    put32(p, (uint32_t)n);
    put32(p + 4, (uint32_t)(n >> 32));
}

static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int write_ddr(void *opaque, uint64_t address, const void *data, size_t n) {
    struct memory *memory = opaque;
    size_t offset = (size_t)(address - UINT64_C(0x80000000));
    assert(offset <= sizeof(memory->bytes) && n <= sizeof(memory->bytes) - offset);
    memcpy(memory->bytes + offset, data, n);
    ++memory->writes;
    return 0;
}

static int readback_crc(void *opaque, uint64_t address, size_t n, uint32_t *crc) {
    struct memory *memory = opaque;
    size_t offset = (size_t)(address - UINT64_C(0x80000000));
    *crc = eth_loader_crc32(memory->bytes + offset, n) ^ (unsigned)memory->corrupt;
    return 0;
}

static const struct eth_loader_io io = {NULL, NULL, write_ddr, readback_crc};

static void record(uint8_t *dst, const char *op, uint64_t address,
                   uint32_t length, uint32_t crc) {
    memcpy(dst, op, 4);
    put64(dst + 4, address);
    put32(dst + 12, length);
    put32(dst + 16, crc);
}

static void feed_fragmented(struct eth_loader_stream *stream, const uint8_t *data,
                            size_t length) {
    for (size_t i = 0; i < length; ++i) {
        size_t consumed = 99;
        int result = eth_loader_stream_feed(stream, data + i, 1, &consumed);
        assert(consumed == 1);
        assert(result == (i + 1 == length ? 1 : 0));
    }
}

static uint32_t reply_status(struct eth_loader_stream *stream) {
    size_t size;
    const uint8_t *reply = eth_loader_stream_reply(stream, &size);
    assert(reply && size == 16);
    return get32(reply + 12);
}

int main(void) {
    struct eth_loader_stream stream;
    struct memory memory = {{0}, 0, 0};
    uint8_t scratch[8], packet[24];
    const uint8_t payload[4] = {1, 2, 3, 4};
    uint32_t crc = eth_loader_crc32(payload, sizeof(payload));
    size_t consumed;

    assert(eth_loader_stream_init(&stream, &io, &memory, scratch, sizeof(scratch),
                                  UINT64_C(0x80000000), UINT64_C(0x80000080)) == 0);
    feed_fragmented(&stream, (const uint8_t *)"ARAETH01", 8);
    assert(memcmp(eth_loader_stream_reply(&stream, &consumed), "ARAETH01", 8) == 0);
    assert(consumed == 16 && get32(stream.reply + 12) == sizeof(scratch));
    assert(eth_loader_stream_feed(&stream, payload, sizeof(payload), &consumed) == 1);
    assert(consumed == 0);
    eth_loader_stream_advance(&stream);

    record(packet, "DATA", UINT64_C(0x80000008), 4, crc);
    memcpy(packet + 20, payload, 4);
    assert(eth_loader_stream_feed(&stream, packet, sizeof(packet), &consumed) == 1);
    assert(consumed == sizeof(packet) && memory.writes == 1);
    assert(reply_status(&stream) == 0 && get32(stream.reply + 8) == crc);
    assert(memcmp(memory.bytes + 8, payload, 4) == 0);
    eth_loader_stream_advance(&stream);
    record(packet, "DONE", UINT64_C(0x80000008), 0, 0);
    feed_fragmented(&stream, packet, 20);
    assert(reply_status(&stream) == 0);
    eth_loader_stream_advance(&stream);
    assert(stream.phase == ETH_STREAM_DONE);
    assert(eth_loader_stream_feed(&stream, packet, 20, &consumed) == -1);

    assert(eth_loader_stream_init(&stream, &io, &memory, scratch, sizeof(scratch),
                                  UINT64_C(0x80000000), UINT64_C(0x80000080)) == 0);
    feed_fragmented(&stream, (const uint8_t *)"ARAETH01", 8);
    eth_loader_stream_advance(&stream);
    record(packet, "DATA", UINT64_C(0x8000007e), 4, crc);
    assert(eth_loader_stream_feed(&stream, packet, 20, &consumed) == 1);
    assert(reply_status(&stream) == 1 && consumed == 20 && memory.writes == 1);
    eth_loader_stream_advance(&stream);
    assert(stream.phase == ETH_STREAM_FAILED);

    assert(eth_loader_stream_init(&stream, &io, &memory, scratch, sizeof(scratch),
                                  UINT64_C(0x80000000), UINT64_C(0x80000080)) == 0);
    feed_fragmented(&stream, (const uint8_t *)"ARAETH01", 8);
    eth_loader_stream_advance(&stream);
    record(packet, "DATA", UINT64_C(0x80000008), 4, crc ^ 1);
    memcpy(packet + 20, payload, 4);
    assert(eth_loader_stream_feed(&stream, packet, 24, &consumed) == 1);
    assert(reply_status(&stream) == 2 && memory.writes == 1);

    assert(eth_loader_stream_init(&stream, &io, &memory, scratch, sizeof(scratch),
                                  UINT64_C(0x80000000), UINT64_C(0x80000080)) == 0);
    feed_fragmented(&stream, (const uint8_t *)"ARAETH01", 8);
    eth_loader_stream_advance(&stream);
    record(packet, "DATA", UINT64_C(0x80000008), 4, crc);
    memcpy(packet + 20, payload, 4);
    memory.corrupt = 1;
    assert(eth_loader_stream_feed(&stream, packet, 24, &consumed) == 1);
    assert(reply_status(&stream) == 4 && memory.writes == 2);

    {
        uint8_t source[9] = {0};
        const uint8_t payload8[8] = {9, 7, 5, 3, 1, 2, 4, 6};
        uint32_t crc8 = eth_loader_crc32(payload8, sizeof(payload8));
        memcpy(source + 1, payload8, sizeof(payload8));
        memory.corrupt = 0;
        assert(eth_loader_stream_init(&stream, &io, &memory, scratch, sizeof(scratch),
                                      UINT64_C(0x80000000), UINT64_C(0x80000080)) == 0);
        feed_fragmented(&stream, (const uint8_t *)"ARAETH01", 8);
        eth_loader_stream_advance(&stream);
        record(packet, "DATA", UINT64_C(0x80000020), 8, crc8);
        assert(eth_loader_stream_feed(&stream, packet, 20, &consumed) == 0);
        assert(eth_loader_stream_feed(&stream, source + 1, 3, &consumed) == 0);
        assert(eth_loader_stream_feed(&stream, source + 4, 5, &consumed) == 1);
        assert(reply_status(&stream) == 0 && get32(stream.reply + 8) == crc8);
        assert(memory.writes == 3 &&
               memcmp(memory.bytes + 0x20, payload8, sizeof(payload8)) == 0);
    }

    assert(eth_loader_stream_init(&stream, &io, &memory, scratch, sizeof(scratch),
                                  UINT64_C(0x80000000), UINT64_C(0x80000080)) == 0);
    assert(eth_loader_stream_feed(&stream, "BADMAGIC", 8, &consumed) == -1);
    assert(stream.phase == ETH_STREAM_FAILED && memory.writes == 3);
    puts("eth_loader_stream_test PASS");
    return 0;
}
