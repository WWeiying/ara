#include "../ethernet/firmware/eth_fast_load.h"

#include <assert.h>
#include <stdio.h>

int main(void) {
    struct eth_fast_load_state state = {0};
    uint32_t address = 0;
    const uint32_t base = 0x81000ff8u;
    assert(eth_fast_load_begin(&state, 88, (uint32_t)ETH_FAST_LOAD_DDR_LIMIT - 1, 1) == 0);
    assert(eth_fast_load_begin(&state, 89, (uint32_t)ETH_FAST_LOAD_DDR_LIMIT - 1, 2) == ETH_FAST_LOAD_RANGE);
#ifdef ETH_LOADER_ARA
    assert(eth_fast_load_begin(&state, 90, 0xfeff0000u, 1) == ETH_FAST_LOAD_RANGE);
    assert(!eth_fast_load_dma_source_ok(UINT64_C(0x80000000), 64));
#else
    assert(eth_fast_load_begin(&state, 90, 0xfeff0000u, 1) == 0);
#endif
    assert(eth_fast_load_begin(&state, 1, 0x7fffffffu, 4) == ETH_FAST_LOAD_RANGE);
    assert(eth_fast_load_begin(&state, 1, 0xfefffffeu, 3) == ETH_FAST_LOAD_RANGE);
    assert(eth_fast_load_begin(&state, 1, base, 2 * ETH_FAST_LOAD_CHUNK + 7) == 0);
    assert(eth_fast_load_begin(&state, 1, base, 2 * ETH_FAST_LOAD_CHUNK + 7) == 0);
    assert(eth_fast_load_begin(&state, 1, base + 8, 1) == ETH_FAST_LOAD_SESSION);
    assert(eth_fast_load_prepare(&state, 2, 0, ETH_FAST_LOAD_CHUNK, &address) ==
           ETH_FAST_LOAD_SESSION);
    assert(eth_fast_load_prepare(&state, 1, 2, 7, &address) == 0);
    assert(address == base + 2 * ETH_FAST_LOAD_CHUNK);
    eth_fast_load_commit(&state, 2);
    assert(eth_fast_load_finish(&state, 1, 3) == ETH_FAST_LOAD_INCOMPLETE);
    assert(eth_fast_load_prepare(&state, 1, 0, ETH_FAST_LOAD_CHUNK, &address) == 0);
    eth_fast_load_commit(&state, 0);
    assert(state.next_sequence == 1);
    eth_fast_load_commit(&state, 0);
    assert(state.next_sequence == 1);
    assert(eth_fast_load_prepare(&state, 1, 1, ETH_FAST_LOAD_CHUNK, &address) == 0);
    eth_fast_load_commit(&state, 1);
    assert(state.next_sequence == 3);
    assert(eth_fast_load_finish(&state, 1, 3) == 0);
    assert(eth_fast_load_finish(&state, 1, 3) == 0);
    assert(eth_fast_load_prepare(&state, 1, 1, ETH_FAST_LOAD_CHUNK, &address) ==
           ETH_FAST_LOAD_SESSION);
    assert(eth_fast_load_begin(&state, 2, 0x80000000u, 1) == 0);
    assert(eth_fast_load_prepare(&state, 2, 0, 0, &address) == ETH_FAST_LOAD_SEQUENCE);
    assert(eth_fast_load_prepare(&state, 2, 0, 1, &address) == 0);
    eth_fast_load_commit(&state, 0);
    assert(eth_fast_load_finish(&state, 2, 1) == 0);
    assert(eth_fast_load_dma_source_ok(UINT64_C(0xff000100), 1380));
    assert(eth_fast_load_dma_source_ok(UINT64_C(0xfffffffe), 2));
    assert(!eth_fast_load_dma_source_ok(UINT64_C(0xfffffffe), 3));
    assert(!eth_fast_load_dma_source_ok(UINT64_C(0x100000000), 1));
    assert(!eth_fast_load_dma_source_ok(UINT64_C(0x7fffffff), 1));
    assert(eth_fast_load_begin(&state, 3, base, 66 * ETH_FAST_LOAD_CHUNK) == 0);
    assert(eth_fast_load_prepare(&state, 3, 64, ETH_FAST_LOAD_CHUNK, &address) ==
           ETH_FAST_LOAD_SEQUENCE);
    assert(eth_fast_load_begin(&state, 4, base, 1) == 0);
    assert(eth_fast_load_prepare(&state, 3, 0, ETH_FAST_LOAD_CHUNK, &address) ==
           ETH_FAST_LOAD_SESSION);
    puts("eth_fast_load_test PASS");
    return 0;
}
