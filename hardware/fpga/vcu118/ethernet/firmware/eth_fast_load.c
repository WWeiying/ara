#include "eth_fast_load.h"

static uint32_t packet_count(const struct eth_fast_load_state *state) {
    return (uint32_t)(((uint64_t)state->length + ETH_FAST_LOAD_CHUNK - 1) /
                      ETH_FAST_LOAD_CHUNK);
}

int eth_fast_load_begin(struct eth_fast_load_state *state, uint32_t session,
                        uint32_t base, uint32_t length) {
    if (!state || !length || base < ETH_FAST_LOAD_DDR_START ||
        (uint64_t)base + length > ETH_FAST_LOAD_DDR_LIMIT)
        return ETH_FAST_LOAD_RANGE;
    if (state->active && state->session == session) {
        return state->base == base && state->length == length
                   ? ETH_FAST_LOAD_OK : ETH_FAST_LOAD_SESSION;
    }
    state->session = session;
    state->base = base;
    state->length = length;
    state->next_sequence = 0;
    state->received_window = 0;
    state->active = 1;
    state->finished = 0;
    return ETH_FAST_LOAD_OK;
}

int eth_fast_load_prepare(const struct eth_fast_load_state *state,
                          uint32_t session, uint32_t sequence,
                          size_t size, uint32_t *address) {
    uint64_t offset;
    size_t expected;
    if (!state || !address || !state->active || state->session != session ||
        state->finished) return ETH_FAST_LOAD_SESSION;
    offset = (uint64_t)sequence * ETH_FAST_LOAD_CHUNK;
    if (offset >= state->length ||
        (sequence >= state->next_sequence &&
         sequence - state->next_sequence >= 64)) return ETH_FAST_LOAD_SEQUENCE;
    expected = state->length - offset;
    if (expected > ETH_FAST_LOAD_CHUNK) expected = ETH_FAST_LOAD_CHUNK;
    if (size != expected) return ETH_FAST_LOAD_SEQUENCE;
    *address = state->base + (uint32_t)offset;
    return ETH_FAST_LOAD_OK;
}

void eth_fast_load_commit(struct eth_fast_load_state *state, uint32_t sequence) {
    if (sequence < state->next_sequence) return;
    state->received_window |= UINT64_C(1) << (sequence - state->next_sequence);
    while (state->received_window & 1) {
        state->received_window >>= 1;
        ++state->next_sequence;
    }
}

int eth_fast_load_finish(struct eth_fast_load_state *state, uint32_t session,
                         uint32_t packets) {
    if (!state || !state->active || state->session != session)
        return ETH_FAST_LOAD_SESSION;
    if (packets != packet_count(state) || state->next_sequence != packets)
        return ETH_FAST_LOAD_INCOMPLETE;
    state->finished = 1;
    return ETH_FAST_LOAD_OK;
}

int eth_fast_load_dma_source_ok(uint64_t address, size_t length) {
#ifdef ETH_LOADER_ARA
    // Network pbuf storage must remain in the loader's private DDR reservation.
    return length && address >= UINT64_C(0xff000000) &&
#else
    return length && address >= ETH_FAST_LOAD_DDR_START &&
#endif
           address < UINT64_C(0x100000000) &&
           length <= UINT64_C(0x100000000) - address;
}
