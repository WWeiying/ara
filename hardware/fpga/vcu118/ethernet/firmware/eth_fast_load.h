#ifndef ETH_FAST_LOAD_H
#define ETH_FAST_LOAD_H

#include <stddef.h>
#include <stdint.h>

#define ETH_FAST_LOAD_CHUNK 1380u
#define ETH_FAST_LOAD_DDR_START UINT64_C(0x80000000)
#ifdef ETH_LOADER_ARA
#define ETH_FAST_LOAD_DDR_LIMIT UINT64_C(0xfeff0000)
#else
#define ETH_FAST_LOAD_DDR_LIMIT UINT64_C(0xff000000)
#endif

enum eth_fast_load_status {
    ETH_FAST_LOAD_OK = 0,
    ETH_FAST_LOAD_RANGE = 1,
    ETH_FAST_LOAD_SESSION = 2,
    ETH_FAST_LOAD_SEQUENCE = 3,
    ETH_FAST_LOAD_INCOMPLETE = 4,
    ETH_FAST_LOAD_COPY = 5
};

struct eth_fast_load_state {
    uint32_t session;
    uint32_t base;
    uint32_t length;
    uint32_t next_sequence;
    uint64_t received_window;
    uint8_t active;
    uint8_t finished;
};

int eth_fast_load_begin(struct eth_fast_load_state *state, uint32_t session,
                        uint32_t base, uint32_t length);
int eth_fast_load_prepare(const struct eth_fast_load_state *state,
                          uint32_t session, uint32_t sequence,
                          size_t size, uint32_t *address);
void eth_fast_load_commit(struct eth_fast_load_state *state, uint32_t sequence);
int eth_fast_load_finish(struct eth_fast_load_state *state, uint32_t session,
                         uint32_t packets);
int eth_fast_load_dma_source_ok(uint64_t address, size_t length);

#endif
