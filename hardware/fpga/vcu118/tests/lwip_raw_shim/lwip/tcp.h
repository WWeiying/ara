#ifndef TEST_LWIP_TCP_H
#define TEST_LWIP_TCP_H

#include "pbuf.h"

#include <stddef.h>
#include <stdint.h>

typedef int err_t;
typedef uint16_t u16_t;

#define ERR_OK 0
#define ERR_MEM -1
#define ERR_ABRT -2
#define ERR_VAL -3
#define TCP_WRITE_FLAG_COPY 1
#define IPADDR_TYPE_ANY 0
#define IP_ANY_TYPE NULL

struct tcp_pcb {
    void *arg;
    err_t (*accept)(void *, struct tcp_pcb *, err_t);
    err_t (*recv)(void *, struct tcp_pcb *, struct pbuf *, err_t);
    err_t (*poll)(void *, struct tcp_pcb *);
    void (*error)(void *, err_t);
    uint8_t tx[256];
    size_t tx_size;
    unsigned recved;
    int closed, aborted;
};

struct tcp_pcb *tcp_new_ip_type(int type);
err_t tcp_bind(struct tcp_pcb *pcb, const void *address, u16_t port);
struct tcp_pcb *tcp_listen(struct tcp_pcb *pcb);
void tcp_accept(struct tcp_pcb *pcb, err_t (*callback)(void *, struct tcp_pcb *, err_t));
void tcp_arg(struct tcp_pcb *pcb, void *arg);
void tcp_recv(struct tcp_pcb *pcb, err_t (*callback)(void *, struct tcp_pcb *, struct pbuf *, err_t));
void tcp_err(struct tcp_pcb *pcb, void (*callback)(void *, err_t));
void tcp_poll(struct tcp_pcb *pcb, err_t (*callback)(void *, struct tcp_pcb *), uint8_t interval);
u16_t tcp_sndbuf(const struct tcp_pcb *pcb);
err_t tcp_write(struct tcp_pcb *pcb, const void *data, u16_t length, uint8_t flags);
err_t tcp_output(struct tcp_pcb *pcb);
err_t tcp_close(struct tcp_pcb *pcb);
void tcp_abort(struct tcp_pcb *pcb);
void tcp_recved(struct tcp_pcb *pcb, u16_t length);

#endif
