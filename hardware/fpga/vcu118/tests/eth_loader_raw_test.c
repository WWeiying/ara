#include "../ethernet/firmware/eth_loader_raw.h"

#include "lwip/tcp.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static struct tcp_pcb listener;
static unsigned free_count;
static uint8_t ddr[64];
static unsigned writes;

struct tcp_pcb *tcp_new_ip_type(int type) { (void)type; return &listener; }
err_t tcp_bind(struct tcp_pcb *pcb, const void *address, u16_t port) {
    (void)pcb; (void)address; return port == 49200 ? ERR_OK : ERR_ABRT;
}
struct tcp_pcb *tcp_listen(struct tcp_pcb *pcb) { return pcb; }
void tcp_accept(struct tcp_pcb *pcb, err_t (*cb)(void *, struct tcp_pcb *, err_t)) { pcb->accept = cb; }
void tcp_arg(struct tcp_pcb *pcb, void *arg) { pcb->arg = arg; }
void tcp_recv(struct tcp_pcb *pcb, err_t (*cb)(void *, struct tcp_pcb *, struct pbuf *, err_t)) { pcb->recv = cb; }
void tcp_err(struct tcp_pcb *pcb, void (*cb)(void *, err_t)) { pcb->error = cb; }
void tcp_poll(struct tcp_pcb *pcb, err_t (*cb)(void *, struct tcp_pcb *), uint8_t interval) {
    (void)interval; pcb->poll = cb;
}
u16_t tcp_sndbuf(const struct tcp_pcb *pcb) { return (u16_t)(sizeof(pcb->tx) - pcb->tx_size); }
err_t tcp_write(struct tcp_pcb *pcb, const void *data, u16_t length, uint8_t flags) {
    assert(flags == TCP_WRITE_FLAG_COPY);
    if (tcp_sndbuf(pcb) < length) return ERR_MEM;
    memcpy(pcb->tx + pcb->tx_size, data, length);
    pcb->tx_size += length;
    return ERR_OK;
}
err_t tcp_output(struct tcp_pcb *pcb) { (void)pcb; return ERR_OK; }
err_t tcp_close(struct tcp_pcb *pcb) { pcb->closed = 1; return ERR_OK; }
void tcp_abort(struct tcp_pcb *pcb) { pcb->aborted = 1; }
void tcp_recved(struct tcp_pcb *pcb, u16_t length) { pcb->recved += length; }
void pbuf_free(struct pbuf *p) { (void)p; ++free_count; }

static int write_ddr(void *unused, uint64_t address, const void *data, size_t size) {
    (void)unused;
    assert(address >= UINT64_C(0x80000000));
    assert(address - UINT64_C(0x80000000) < sizeof(ddr));
    memcpy(ddr + (size_t)(address - UINT64_C(0x80000000)), data, size);
    ++writes;
    return 0;
}

static int readback_crc(void *unused, uint64_t address, size_t size, uint32_t *crc) {
    (void)unused;
    *crc = eth_loader_crc32(ddr + (size_t)(address - UINT64_C(0x80000000)), size);
    return 0;
}

static const struct eth_loader_io io = {NULL, NULL, write_ddr, readback_crc};

static void put32(uint8_t *p, uint32_t n) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(n >> (8 * i));
}

static void put64(uint8_t *p, uint64_t n) {
    put32(p, (uint32_t)n);
    put32(p + 4, (uint32_t)(n >> 32));
}

static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static err_t deliver(struct tcp_pcb *pcb, void *data, uint16_t size) {
    struct pbuf p = {NULL, data, size, size};
    return pcb->recv(pcb->arg, pcb, &p, ERR_OK);
}

int main(void) {
    struct tcp_pcb first = {0}, second = {0}, third = {0};
    struct tcp_pcb rejected = {0}, rejected_split = {0};
    struct tcp_pcb pipelined = {0}, busy = {0};
    uint8_t scratch[8], packet[24] = {0};
    uint8_t joined[48] = {0};
    const uint8_t payload[4] = {1, 2, 3, 4};
    uint32_t crc = eth_loader_crc32(payload, sizeof(payload));

    assert(eth_loader_raw_listen(49200, &io, NULL, scratch, sizeof(scratch),
                                  UINT64_C(0x80000000), UINT64_C(0x80000040)) == 0);
    assert(listener.accept(listener.arg, &first, ERR_OK) == ERR_OK);
    assert(listener.accept(listener.arg, &busy, ERR_OK) == ERR_ABRT && busy.aborted);
    for (unsigned i = 0; i < 8; ++i)
        assert(deliver(&first, (void *)("ARAETH01" + i), 1) == ERR_OK);
    assert(first.tx_size == 16 && memcmp(first.tx, "ARAETH01", 8) == 0);
    assert(get32(first.tx + 12) == sizeof(scratch));
    memcpy(packet, "DATA", 4);
    put64(packet + 4, UINT64_C(0x80000004));
    put32(packet + 12, 4);
    put32(packet + 16, crc);
    memcpy(packet + 20, payload, 4);
    assert(deliver(&first, packet, 20) == ERR_OK);
    assert(deliver(&first, packet + 20, 4) == ERR_OK);
    assert(writes == 1 && memcmp(ddr + 4, payload, 4) == 0);
    assert(first.tx_size == 32 && get32(first.tx + 28) == 0);
    memcpy(packet, "DONE", 4);
    put64(packet + 4, UINT64_C(0x80000004));
    put32(packet + 12, 0);
    put32(packet + 16, 0);
    assert(deliver(&first, packet, 20) == ERR_OK);
    assert(first.closed && first.tx_size == 48);
    assert(first.recved == 8 + 24 + 20);

    assert(listener.accept(listener.arg, &second, ERR_OK) == ERR_OK);
    assert(deliver(&second, "ARAETH01", 8) == ERR_OK);
    memcpy(packet, "DATA", 4);
    put64(packet + 4, UINT64_C(0x80000008));
    put32(packet + 12, 4);
    put32(packet + 16, crc ^ 1);
    memcpy(packet + 20, payload, 4);
    assert(deliver(&second, packet, 24) == ERR_OK);
    assert(second.closed && get32(second.tx + 28) == 2);
    assert(listener.accept(listener.arg, &third, ERR_OK) == ERR_OK);
    third.tx_size = sizeof(third.tx);
    assert(deliver(&third, "ARAETH01", 8) == ERR_OK);
    assert(!third.closed && third.poll);
    third.tx_size = 0;
    assert(third.poll(third.arg, &third) == ERR_OK);
    assert(third.tx_size == 16 && memcmp(third.tx, "ARAETH01", 8) == 0);
    assert(writes == 1 && free_count == 14);
    memcpy(packet, "DONE", 4);
    put64(packet + 4, UINT64_C(0x80000000));
    put32(packet + 12, 0);
    put32(packet + 16, 0);
    assert(deliver(&third, packet, 20) == ERR_OK);
    assert(third.closed && get32(third.tx + 28) == 1);

    memcpy(packet, "DATA", 4);
    put64(packet + 4, UINT64_C(0x80000040));
    put32(packet + 12, 4);
    put32(packet + 16, crc);
    memcpy(packet + 20, payload, 4);
    assert(listener.accept(listener.arg, &rejected, ERR_OK) == ERR_OK);
    assert(deliver(&rejected, "ARAETH01", 8) == ERR_OK);
    assert(deliver(&rejected, packet, sizeof(packet)) == ERR_OK);
    assert(rejected.closed && !rejected.aborted && get32(rejected.tx + 28) == 1);

    assert(listener.accept(listener.arg, &rejected_split, ERR_OK) == ERR_OK);
    assert(deliver(&rejected_split, "ARAETH01", 8) == ERR_OK);
    assert(deliver(&rejected_split, packet, 20) == ERR_OK);
    assert(rejected_split.tx_size == 16 && !rejected_split.closed);
    assert(rejected_split.poll(rejected_split.arg, &rejected_split) == ERR_OK);
    assert(rejected_split.tx_size == 16);
    assert(deliver(&rejected_split, packet + 20, 4) == ERR_OK);
    assert(rejected_split.closed && !rejected_split.aborted &&
           get32(rejected_split.tx + 28) == 1);
    assert(writes == 1 && free_count == 20);

    assert(listener.accept(listener.arg, &pipelined, ERR_OK) == ERR_OK);
    assert(deliver(&pipelined, "ARAETH01", 8) == ERR_OK);
    assert(get32(pipelined.tx + 8) == 5);
    memcpy(joined, "DATA", 4);
    put64(joined + 4, UINT64_C(0x8000000c));
    put32(joined + 12, 4);
    put32(joined + 16, crc);
    memcpy(joined + 20, payload, 4);
    memcpy(joined + 24, "DATA", 4);
    put64(joined + 28, UINT64_C(0x80000010));
    put32(joined + 36, 4);
    put32(joined + 40, crc);
    memcpy(joined + 44, payload, 4);
    assert(deliver(&pipelined, joined, sizeof(joined)) == ERR_OK);
    assert(pipelined.tx_size == 48 && get32(pipelined.tx + 28) == 0 &&
           get32(pipelined.tx + 44) == 0 && writes == 3);
    memcpy(packet, "DONE", 4);
    put64(packet + 4, UINT64_C(0x8000000c));
    put32(packet + 12, 0);
    put32(packet + 16, 0);
    assert(deliver(&pipelined, packet, 20) == ERR_OK);
    assert(pipelined.closed && !pipelined.aborted && free_count == 23);
    puts("eth_loader_raw_test PASS");
    return 0;
}
