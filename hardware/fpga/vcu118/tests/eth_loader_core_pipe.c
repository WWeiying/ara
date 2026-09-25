/* Test-only pipe adapter. No Xilinx IP or board memory is involved. */
#include "../ethernet/firmware/eth_loader_core.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define BASE UINT64_C(0x80000000)
static uint8_t ddr[65536];

static int receive(void *context, void *data, size_t n) {
    (void)context;
    return fread(data, 1, n, stdin) == n ? 0 : -1;
}

static int send_data(void *context, const void *data, size_t n) {
    (void)context;
    return fwrite(data, 1, n, stdout) == n && fflush(stdout) == 0 ? 0 : -1;
}

static int write_ddr(void *context, uint64_t address, const void *data, size_t n) {
    (void)context;
    if (address < BASE || address - BASE > sizeof(ddr) ||
        n > sizeof(ddr) - (size_t)(address - BASE)) return -1;
    memcpy(ddr + (size_t)(address - BASE), data, n);
    return 0;
}

static int readback_crc32(void *context, uint64_t address, size_t n, uint32_t *crc) {
    (void)context;
    if (address < BASE || address - BASE > sizeof(ddr) ||
        n > sizeof(ddr) - (size_t)(address - BASE)) return -1;
    *crc = eth_loader_crc32(ddr + (size_t)(address - BASE), n);
    return 0;
}

int main(void) {
    static uint8_t scratch[4096];
    const struct eth_loader_io io = {receive, send_data, write_ddr, readback_crc32};
    return eth_loader_receive(&io, NULL, scratch, sizeof(scratch)) == 0 ? 0 : 1;
}
