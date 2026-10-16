#ifndef ETH_LOADER_STREAM_H
#define ETH_LOADER_STREAM_H

#include "eth_loader_core.h"

#include <stddef.h>
#include <stdint.h>

enum eth_loader_stream_phase {
    ETH_STREAM_HELLO,
    ETH_STREAM_HEADER,
    ETH_STREAM_PAYLOAD,
    ETH_STREAM_REPLY,
    ETH_STREAM_DONE,
    ETH_STREAM_FAILED
};

/* A stop-and-wait protocol receiver. Input pauses while a reply is pending. */
struct eth_loader_stream {
    const struct eth_loader_io *memory;
    void *memory_context;
    uint8_t *scratch;
    size_t max_chunk;
    uint64_t ddr_start, ddr_end, last_end, address;
    uint8_t input[20], reply[16];
    size_t input_used, input_needed;
    uint32_t length, expected_crc;
    enum eth_loader_stream_phase phase, after_reply;
    int wrote;
};

int eth_loader_stream_init(struct eth_loader_stream *stream,
                           const struct eth_loader_io *memory, void *memory_context,
                           void *scratch, size_t scratch_size,
                           uint64_t ddr_start, uint64_t ddr_end);

/* Returns 0 for more input, 1 for a reply, -1 for a fatal protocol error. */
int eth_loader_stream_feed(struct eth_loader_stream *stream, const void *data,
                           size_t size, size_t *consumed);

/* Reply remains valid until advance; the caller must queue/copy all bytes. */
const uint8_t *eth_loader_stream_reply(const struct eth_loader_stream *stream,
                                       size_t *size);
void eth_loader_stream_advance(struct eth_loader_stream *stream);

#endif
