#ifndef ETH_FAST_PROBE_FRAME_H
#define ETH_FAST_PROBE_FRAME_H

#include <stddef.h>
#include <stdint.h>

// Returns the echoed UDP payload size, or zero for a non-probe/invalid frame.
size_t eth_fast_probe_reflect(uint8_t *frame, size_t frame_size,
                              uint16_t port, uint8_t **payload);

#endif
