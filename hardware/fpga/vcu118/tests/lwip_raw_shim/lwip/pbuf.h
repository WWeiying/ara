#ifndef TEST_LWIP_PBUF_H
#define TEST_LWIP_PBUF_H

#include <stdint.h>

struct pbuf {
    struct pbuf *next;
    void *payload;
    uint16_t len, tot_len;
};

void pbuf_free(struct pbuf *p);

#endif
