#include "eth_loader_core.h"

#include <string.h>

#define DDR_START UINT64_C(0x80000000)
#define DDR_END UINT64_C(0x100000000)
#define MAX_CHUNK 65536u

static const uint8_t magic[8] = {'A', 'R', 'A', 'E', 'T', 'H', '0', '1'};

static uint32_t load32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
           (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static uint64_t load64(const uint8_t *bytes) {
    return (uint64_t)load32(bytes) | (uint64_t)load32(bytes + 4) << 32;
}

static void store32(uint8_t *bytes, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) bytes[i] = (uint8_t)(value >> (8 * i));
}

static void store64(uint8_t *bytes, uint64_t value) {
    store32(bytes, (uint32_t)value);
    store32(bytes + 4, (uint32_t)(value >> 32));
}

uint32_t eth_loader_crc32(const void *data, size_t n) {
    const uint8_t *bytes = data;
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < n; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ ((crc & 1) ? UINT32_C(0xedb88320) : 0);
        }
    }
    return ~crc;
}

static int acknowledge(const struct eth_loader_io *io, void *context,
                       uint64_t address, uint32_t crc, uint32_t status) {
    uint8_t packet[16];
    store64(packet, address);
    store32(packet + 8, crc);
    store32(packet + 12, status);
    return io->send(context, packet, sizeof(packet));
}

int eth_loader_receive(const struct eth_loader_io *io, void *context,
                       void *scratch, size_t scratch_size) {
    uint8_t packet[20];
    uint64_t last_end = DDR_START;
    size_t max_chunk = scratch_size < MAX_CHUNK ? scratch_size : MAX_CHUNK;
    int wrote = 0;
    if (!io || !io->receive || !io->send || !io->write_ddr ||
        !io->readback_crc32 || !scratch || max_chunk == 0) return -1;
    if (io->receive(context, packet, sizeof(magic)) ||
        memcmp(packet, magic, sizeof(magic))) return -2;
    memcpy(packet, magic, sizeof(magic));
    store32(packet + 8, 1);  /* CAP_HOST; DDR2 intentionally absent. */
    store32(packet + 12, (uint32_t)max_chunk);
    if (io->send(context, packet, 16)) return -3;

    for (;;) {
        uint64_t address;
        uint32_t length, expected_crc, actual_crc;
        if (io->receive(context, packet, sizeof(packet))) return -4;
        address = load64(packet + 4);
        length = load32(packet + 12);
        expected_crc = load32(packet + 16);
        if (memcmp(packet, "DONE", 4) == 0) {
            if (!wrote || length != 0 || expected_crc != 0 ||
                address < DDR_START || address >= DDR_END) {
                acknowledge(io, context, address, 0, 1);
                return -5;
            }
            return acknowledge(io, context, address, 0, 0) ? -6 : 0;
        }
        if (memcmp(packet, "DATA", 4) != 0 || length == 0 ||
            length > max_chunk || address < DDR_START || address >= DDR_END ||
            length > DDR_END - address || address < last_end) {
            acknowledge(io, context, address, 0, 1);
            return -7;
        }
        if (io->receive(context, scratch, length)) return -8;
        if (eth_loader_crc32(scratch, length) != expected_crc) {
            acknowledge(io, context, address, 0, 2);
            return -9;
        }
        if (io->write_ddr(context, address, scratch, length) ||
            io->readback_crc32(context, address, length, &actual_crc)) {
            acknowledge(io, context, address, 0, 3);
            return -10;
        }
        if (acknowledge(io, context, address, actual_crc,
                        actual_crc == expected_crc ? 0 : 4)) return -11;
        if (actual_crc != expected_crc) return -12;
        last_end = address + length;
        wrote = 1;
    }
}
