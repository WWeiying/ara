/* Test-only BSD shims for checking the lwIP adapter compile path. */
#ifndef ETH_LOADER_TEST_LWIP_SOCKETS_H
#define ETH_LOADER_TEST_LWIP_SOCKETS_H

#include <sys/socket.h>

static inline ssize_t lwip_recv(int fd, void *data, size_t size, int flags) {
    return recv(fd, data, size < 5 ? size : 5, flags);
}

static inline ssize_t lwip_send(int fd, const void *data, size_t size, int flags) {
    return send(fd, data, size < 3 ? size : 3, flags);
}

#endif
