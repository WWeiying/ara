#ifndef ETH_LOADER_DDR_H
#define ETH_LOADER_DDR_H

#include "eth_loader_core.h"

#include <stdint.h>

#define ETH_LOADER_DDR_START UINT64_C(0x80000000)
#define ETH_LOADER_DDR_LIMIT UINT64_C(0xff000000)

extern const struct eth_loader_io eth_loader_ddr_io;

#endif
