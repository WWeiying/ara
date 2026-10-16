#include "eth_loader_stream.h"

#include <string.h>

#ifdef ETH_LOADER_PROFILE
#include "xparameters.h"
#include "xtmrctr_l.h"

volatile uint32_t eth_loader_crc_cycles;
volatile uint32_t eth_loader_write_cycles;
volatile uint32_t eth_loader_readback_cycles;
volatile uint32_t eth_loader_profile_blocks;
volatile uint32_t eth_loader_profile_bytes;

static uint32_t profile_cycles(void) {
    return XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1);
}
#endif

#define DDR_START UINT64_C(0x80000000)
#define DDR_END UINT64_C(0x100000000)
#define MAX_CHUNK 65536u
#define CAP_HOST 1u
#define CAP_PIPELINE 4u

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

static void acknowledge(struct eth_loader_stream *stream, uint32_t crc,
                        uint32_t status, enum eth_loader_stream_phase next) {
    store64(stream->reply, stream->address);
    store32(stream->reply + 8, crc);
    store32(stream->reply + 12, status);
    stream->after_reply = next;
    stream->phase = ETH_STREAM_REPLY;
}

int eth_loader_stream_init(struct eth_loader_stream *stream,
                           const struct eth_loader_io *memory, void *memory_context,
                           void *scratch, size_t scratch_size,
                           uint64_t ddr_start, uint64_t ddr_end) {
    if (!stream || !memory || !memory->write_ddr || !memory->readback_crc32 ||
        !scratch || !scratch_size || ddr_start < DDR_START ||
        ddr_start >= ddr_end || ddr_end > DDR_END) return -1;
    memset(stream, 0, sizeof(*stream));
    stream->memory = memory;
    stream->memory_context = memory_context;
    stream->scratch = scratch;
    stream->max_chunk = scratch_size < MAX_CHUNK ? scratch_size : MAX_CHUNK;
    stream->ddr_start = ddr_start;
    stream->ddr_end = ddr_end;
    stream->last_end = ddr_start;
    stream->phase = ETH_STREAM_HELLO;
    stream->input_needed = sizeof(magic);
    return 0;
}

int eth_loader_stream_feed(struct eth_loader_stream *stream, const void *data,
                           size_t size, size_t *consumed) {
    const uint8_t *bytes = data;
    if (!stream || !consumed || (!data && size)) return -1;
    *consumed = 0;
    if (stream->phase == ETH_STREAM_REPLY) return 1;
    if (stream->phase == ETH_STREAM_DONE || stream->phase == ETH_STREAM_FAILED)
        return -1;
    while (*consumed < size) {
        uint8_t *target = stream->phase == ETH_STREAM_PAYLOAD ?
            stream->scratch : stream->input;
        size_t available = stream->input_needed - stream->input_used;
        size_t remaining = size - *consumed;
        size_t take = available < remaining ? available : remaining;
        memcpy(target + stream->input_used, bytes + *consumed, take);
        stream->input_used += take;
        *consumed += take;
        if (stream->input_used != stream->input_needed) continue;
        stream->input_used = 0;
        if (stream->phase == ETH_STREAM_HELLO) {
            if (memcmp(stream->input, magic, sizeof(magic))) {
                stream->phase = ETH_STREAM_FAILED;
                return -1;
            }
            memcpy(stream->reply, magic, sizeof(magic));
            store32(stream->reply + 8, CAP_HOST | CAP_PIPELINE);
            store32(stream->reply + 12, (uint32_t)stream->max_chunk);
            stream->after_reply = ETH_STREAM_HEADER;
            stream->phase = ETH_STREAM_REPLY;
            return 1;
        }
        if (stream->phase == ETH_STREAM_HEADER) {
            stream->address = load64(stream->input + 4);
            stream->length = load32(stream->input + 12);
            stream->expected_crc = load32(stream->input + 16);
            if (memcmp(stream->input, "DONE", 4) == 0) {
                int valid = stream->wrote && !stream->length &&
                    !stream->expected_crc && stream->address >= stream->ddr_start &&
                    stream->address < stream->ddr_end;
                acknowledge(stream, 0, valid ? 0 : 1,
                            valid ? ETH_STREAM_DONE : ETH_STREAM_FAILED);
                return 1;
            }
            if (memcmp(stream->input, "DATA", 4) != 0 || !stream->length ||
                stream->length > stream->max_chunk ||
                stream->address < stream->ddr_start ||
                stream->address >= stream->ddr_end ||
                stream->length > stream->ddr_end - stream->address ||
                stream->address < stream->last_end) {
                acknowledge(stream, 0, 1, ETH_STREAM_FAILED);
                return 1;
            }
            stream->phase = ETH_STREAM_PAYLOAD;
            stream->input_needed = stream->length;
            continue;
        }
        if (stream->phase == ETH_STREAM_PAYLOAD) {
            uint32_t crc;
#ifdef ETH_LOADER_PROFILE
            uint32_t start = profile_cycles();
#endif
            crc = eth_loader_crc32(stream->scratch, stream->length);
#ifdef ETH_LOADER_PROFILE
            eth_loader_crc_cycles += profile_cycles() - start;
#endif
            if (crc != stream->expected_crc) {
                acknowledge(stream, 0, 2, ETH_STREAM_FAILED);
                return 1;
            }
            {
                int status;
#ifdef ETH_LOADER_PROFILE
                start = profile_cycles();
#endif
                status = stream->memory->write_ddr(stream->memory_context,
                                                   stream->address, stream->scratch,
                                                   stream->length);
#ifdef ETH_LOADER_PROFILE
                eth_loader_write_cycles += profile_cycles() - start;
#endif
                if (!status) {
#ifdef ETH_LOADER_PROFILE
                    start = profile_cycles();
#endif
                    status = stream->memory->readback_crc32(stream->memory_context,
                                                            stream->address,
                                                            stream->length, &crc);
#ifdef ETH_LOADER_PROFILE
                    eth_loader_readback_cycles += profile_cycles() - start;
#endif
                }
                if (status) {
                    acknowledge(stream, 0, 3, ETH_STREAM_FAILED);
                    return 1;
                }
            }
            acknowledge(stream, crc, crc == stream->expected_crc ? 0 : 4,
                        crc == stream->expected_crc ? ETH_STREAM_HEADER : ETH_STREAM_FAILED);
            if (crc == stream->expected_crc) {
                stream->wrote = 1;
                stream->last_end = stream->address + stream->length;
#ifdef ETH_LOADER_PROFILE
                ++eth_loader_profile_blocks;
                eth_loader_profile_bytes += stream->length;
#endif
            }
            return 1;
        }
    }
    return 0;
}

const uint8_t *eth_loader_stream_reply(const struct eth_loader_stream *stream,
                                       size_t *size) {
    if (!size) return NULL;
    *size = stream && stream->phase == ETH_STREAM_REPLY ? 16 : 0;
    return *size ? stream->reply : NULL;
}

void eth_loader_stream_advance(struct eth_loader_stream *stream) {
    if (!stream || stream->phase != ETH_STREAM_REPLY) return;
    stream->phase = stream->after_reply;
    stream->input_needed = stream->phase == ETH_STREAM_HEADER ? 20 : 0;
}
