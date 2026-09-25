#ifndef ETH_LOADER_TCP_H
#define ETH_LOADER_TCP_H

#include "eth_loader_core.h"

/* The caller owns the connected socket, scratch buffer and DDR callbacks. */
int eth_loader_tcp_serve(int socket_fd, const struct eth_loader_io *memory,
                         void *memory_context, void *scratch, size_t scratch_size);

#endif
