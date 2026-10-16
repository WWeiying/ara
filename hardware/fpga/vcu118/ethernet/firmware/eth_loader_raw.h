#ifndef ETH_LOADER_RAW_H
#define ETH_LOADER_RAW_H

#include "eth_loader_stream.h"

#include <stdint.h>

/* Call after lwIP and the Ethernet netif are initialized in NO_SYS mode. */
int eth_loader_raw_listen(uint16_t port, const struct eth_loader_io *memory,
                          void *memory_context, void *scratch, size_t scratch_size,
                          uint64_t ddr_start, uint64_t ddr_end);

#endif
