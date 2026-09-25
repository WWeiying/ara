#ifndef ETH_LOADER_CORE_H
#define ETH_LOADER_CORE_H

#include <stddef.h>
#include <stdint.h>

/* All transport callbacks return zero on success and must transfer exactly n bytes. */
struct eth_loader_io {
    int (*receive)(void *context, void *data, size_t n);
    int (*send)(void *context, const void *data, size_t n);
    int (*write_ddr)(void *context, uint64_t address, const void *data, size_t n);
    int (*readback_crc32)(void *context, uint64_t address, size_t n, uint32_t *crc);
};

uint32_t eth_loader_crc32(const void *data, size_t n);

/* Only DDR1 is supported. A successful DONE does not execute the image. */
int eth_loader_receive(const struct eth_loader_io *io, void *context,
                       void *scratch, size_t scratch_size);

#endif
