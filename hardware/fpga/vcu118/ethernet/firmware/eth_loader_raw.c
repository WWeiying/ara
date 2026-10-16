#include "eth_loader_raw.h"

#include "lwip/pbuf.h"
#include "lwip/tcp.h"

#include <stddef.h>

#ifdef ETH_LOADER_PROFILE
#include "xparameters.h"
#include "xtmrctr_l.h"

volatile uint32_t eth_loader_rx_callback_cycles;
volatile uint32_t eth_loader_rx_callback_count;

static uint32_t profile_cycles(void) {
    return XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1);
}
#endif

struct raw_server {
    const struct eth_loader_io *memory;
    void *memory_context;
    void *scratch;
    size_t scratch_size;
    uint64_t ddr_start, ddr_end;
    struct tcp_pcb *listener, *active;
    struct eth_loader_stream stream;
    int close_pending;
    size_t reject_remaining;
};

static struct raw_server server;

static void drop_connection(struct tcp_pcb *pcb) {
    server.active = NULL;
    server.close_pending = 0;
    server.reject_remaining = 0;
    tcp_arg(pcb, NULL);
    tcp_err(pcb, NULL);
    tcp_recv(pcb, NULL);
    tcp_poll(pcb, NULL, 0);
    tcp_abort(pcb);
}

static err_t close_connection(struct tcp_pcb *pcb) {
    err_t err;
    server.close_pending = 1;
    err = tcp_close(pcb);
    if (err == ERR_OK) {
        server.active = NULL;
        server.close_pending = 0;
    }
    return err;
}

static err_t flush_reply(struct tcp_pcb *pcb) {
    const uint8_t *reply;
    size_t size;
    err_t err;
    reply = eth_loader_stream_reply(&server.stream, &size);
    if (!reply) return ERR_OK;
    if (tcp_sndbuf(pcb) < size) return ERR_MEM;
    err = tcp_write(pcb, reply, (u16_t)size, TCP_WRITE_FLAG_COPY);
    if (err != ERR_OK) return err;
    eth_loader_stream_advance(&server.stream);
    err = tcp_output(pcb);
    if (err != ERR_OK && err != ERR_MEM) return err;
    if (server.stream.phase == ETH_STREAM_DONE ||
        server.stream.phase == ETH_STREAM_FAILED) return close_connection(pcb);
    return ERR_OK;
}

static void receive_error(void *arg, err_t err) {
    (void)err;
    if (server.active == arg) {
        server.active = NULL;
        server.close_pending = 0;
        server.reject_remaining = 0;
    }
}

static err_t poll_connection(void *arg, struct tcp_pcb *pcb) {
    err_t err;
    (void)arg;
    if (server.reject_remaining) return ERR_OK;
    if (server.close_pending) err = close_connection(pcb);
    else if (server.stream.phase == ETH_STREAM_REPLY) err = flush_reply(pcb);
    else err = tcp_output(pcb);
    if (err == ERR_MEM || err == ERR_OK) return ERR_OK;
    drop_connection(pcb);
    return ERR_ABRT;
}

static err_t receive_data(void *arg, struct tcp_pcb *pcb, struct pbuf *p,
                          err_t err) {
    struct pbuf *part;
    int terminal = 0;
    int bad = 0;
#ifdef ETH_LOADER_PROFILE
    uint32_t started = profile_cycles();
#endif
    (void)arg;
    if (!p) {
        if (close_connection(pcb) != ERR_OK) drop_connection(pcb);
        return ERR_OK;
    }
    if (err != ERR_OK || server.close_pending ||
        (server.stream.phase == ETH_STREAM_REPLY && !server.reject_remaining)) {
        pbuf_free(p);
        drop_connection(pcb);
        return ERR_ABRT;
    }
    for (part = p; part && !terminal && !bad; part = part->next) {
        const uint8_t *bytes = part->payload;
        size_t offset = 0;
        while (offset < part->len && !terminal && !bad) {
            size_t consumed;
            int result;
            if (server.reject_remaining) {
                size_t available = part->len - offset;
                size_t take = available < server.reject_remaining ?
                              available : server.reject_remaining;
                offset += take;
                server.reject_remaining -= take;
                if (!server.reject_remaining) terminal = 1;
                continue;
            }
            enum eth_loader_stream_phase before = server.stream.phase;
            result = eth_loader_stream_feed(&server.stream, bytes + offset,
                                            part->len - offset, &consumed);
            offset += consumed;
            if (result < 0 || (!consumed && result == 0)) {
                bad = 1;
                break;
            }
            if (result != 1) continue;
            if (before == ETH_STREAM_HEADER &&
                server.stream.after_reply == ETH_STREAM_FAILED &&
                server.stream.reply[12] == 1 && server.stream.length &&
                server.stream.length <= server.stream.max_chunk) {
                server.reject_remaining = server.stream.length;
                continue;
            }
            if (server.stream.after_reply == ETH_STREAM_DONE ||
                server.stream.after_reply == ETH_STREAM_FAILED) {
                terminal = 1;
                break;
            }
            err = flush_reply(pcb);
            if (err == ERR_MEM && offset == part->len && !part->next) break;
            if (err != ERR_OK) bad = 1;
        }
    }
    if (bad) {
        pbuf_free(p);
        drop_connection(pcb);
        return ERR_ABRT;
    }
    tcp_recved(pcb, p->tot_len);
    pbuf_free(p);
    if (terminal) {
        err = flush_reply(pcb);
        if (err != ERR_OK && err != ERR_MEM) {
            drop_connection(pcb);
            return ERR_ABRT;
        }
    }
#ifdef ETH_LOADER_PROFILE
    eth_loader_rx_callback_cycles += profile_cycles() - started;
    ++eth_loader_rx_callback_count;
#endif
    return ERR_OK;
}

static err_t accept_connection(void *arg, struct tcp_pcb *pcb, err_t err) {
    (void)arg;
    if (!pcb) return ERR_VAL;
    if (err != ERR_OK || server.active ||
        eth_loader_stream_init(&server.stream, server.memory,
                               server.memory_context, server.scratch,
                               server.scratch_size, server.ddr_start,
                               server.ddr_end)) {
        tcp_abort(pcb);
        return ERR_ABRT;
    }
    server.active = pcb;
    server.close_pending = 0;
    server.reject_remaining = 0;
    tcp_arg(pcb, pcb);
    tcp_recv(pcb, receive_data);
    tcp_err(pcb, receive_error);
    tcp_poll(pcb, poll_connection, 2);
    return ERR_OK;
}

int eth_loader_raw_listen(uint16_t port, const struct eth_loader_io *memory,
                          void *memory_context, void *scratch, size_t scratch_size,
                          uint64_t ddr_start, uint64_t ddr_end) {
    struct tcp_pcb *listener;
    struct eth_loader_stream probe;
    if (!port || server.listener ||
        eth_loader_stream_init(&probe, memory, memory_context, scratch,
                               scratch_size, ddr_start, ddr_end)) return -1;
    listener = tcp_new_ip_type(IPADDR_TYPE_ANY);
    if (!listener) return -1;
    if (tcp_bind(listener, IP_ANY_TYPE, port) != ERR_OK) {
        tcp_close(listener);
        return -1;
    }
    server.memory = memory;
    server.memory_context = memory_context;
    server.scratch = scratch;
    server.scratch_size = scratch_size;
    server.ddr_start = ddr_start;
    server.ddr_end = ddr_end;
    server.listener = tcp_listen(listener);
    if (!server.listener) return -1;
    tcp_arg(server.listener, &server);
    tcp_accept(server.listener, accept_connection);
    return 0;
}
