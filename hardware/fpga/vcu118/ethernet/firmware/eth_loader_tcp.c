#include "eth_loader_tcp.h"

#include <errno.h>
#include <limits.h>

#ifdef ETH_LOADER_LWIP
#include "lwip/sockets.h"
#define socket_receive lwip_recv
#define socket_send lwip_send
#define SEND_FLAGS 0
#else
#include <sys/socket.h>
#define socket_receive recv
#define socket_send send
#ifdef MSG_NOSIGNAL
#define SEND_FLAGS MSG_NOSIGNAL
#else
#define SEND_FLAGS 0
#endif
#endif

struct connection {
    int fd;
    const struct eth_loader_io *memory;
    void *memory_context;
};

static int receive_exact(void *opaque, void *data, size_t size) {
    struct connection *connection = opaque;
    unsigned char *cursor = data;
    while (size) {
        size_t requested = size > INT_MAX ? INT_MAX : size;
        int count = socket_receive(connection->fd, cursor, requested, 0);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return -1;
        cursor += count;
        size -= (size_t)count;
    }
    return 0;
}

static int send_exact(void *opaque, const void *data, size_t size) {
    struct connection *connection = opaque;
    const unsigned char *cursor = data;
    while (size) {
        size_t requested = size > INT_MAX ? INT_MAX : size;
        int count = socket_send(connection->fd, cursor, requested, SEND_FLAGS);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return -1;
        cursor += count;
        size -= (size_t)count;
    }
    return 0;
}

static int write_ddr(void *opaque, uint64_t address, const void *data, size_t size) {
    struct connection *connection = opaque;
    return connection->memory->write_ddr(connection->memory_context, address, data, size);
}

static int readback_crc32(void *opaque, uint64_t address, size_t size, uint32_t *crc) {
    struct connection *connection = opaque;
    return connection->memory->readback_crc32(connection->memory_context, address, size, crc);
}

int eth_loader_tcp_serve(int socket_fd, const struct eth_loader_io *memory,
                         void *memory_context, void *scratch, size_t scratch_size) {
    struct connection connection = {socket_fd, memory, memory_context};
    const struct eth_loader_io io = {
        receive_exact, send_exact, write_ddr, readback_crc32
    };
    if (socket_fd < 0 || !memory || !memory->write_ddr || !memory->readback_crc32)
        return -1;
    return eth_loader_receive(&io, &connection, scratch, scratch_size);
}
