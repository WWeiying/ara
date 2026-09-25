/* Native socket fixture; DDR is an array, not an FPGA memory controller. */
#define _POSIX_C_SOURCE 200809L
#include "../ethernet/firmware/eth_loader_tcp.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#define BASE UINT64_C(0x80000000)
static uint8_t ddr[65536];

static int write_ddr(void *context, uint64_t address, const void *data, size_t size) {
    (void)context;
    if (address < BASE || address - BASE > sizeof(ddr) ||
        size > sizeof(ddr) - (size_t)(address - BASE)) return -1;
    memcpy(ddr + (size_t)(address - BASE), data, size);
    return 0;
}

static int readback_crc32(void *context, uint64_t address, size_t size, uint32_t *crc) {
    (void)context;
    if (address < BASE || address - BASE > sizeof(ddr) ||
        size > sizeof(ddr) - (size_t)(address - BASE)) return -1;
    *crc = eth_loader_crc32(ddr + (size_t)(address - BASE), size);
    return 0;
}

int main(void) {
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in address = {0};
    socklen_t address_size = sizeof(address);
    static uint8_t scratch[4096];
    struct timeval timeout = {5, 0};
    const struct eth_loader_io memory = {NULL, NULL, write_ddr, readback_crc32};
    int peer, result;
    if (listener < 0) return 1;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(listener, (const struct sockaddr *)&address, sizeof(address)) ||
        listen(listener, 1) ||
        getsockname(listener, (struct sockaddr *)&address, &address_size)) return 1;
    printf("PORT %u\n", (unsigned)ntohs(address.sin_port));
    fflush(stdout);
    peer = accept(listener, NULL, NULL);
    close(listener);
    if (peer < 0) return 1;
    setsockopt(peer, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(peer, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    result = eth_loader_tcp_serve(peer, &memory, NULL, scratch, sizeof(scratch));
    close(peer);
    printf("RESULT %d\n", result);
    fflush(stdout);
    return result == 0 ? 0 : 2;
}
