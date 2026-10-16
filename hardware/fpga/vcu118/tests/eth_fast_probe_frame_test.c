#include "../ethernet/firmware/eth_fast_probe_frame.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint16_t checksum(const uint8_t *bytes, size_t size) {
    uint32_t sum = 0;
    for (size_t i = 0; i < size; i += 2)
        sum += (uint16_t)((uint16_t)bytes[i] << 8 | bytes[i + 1]);
    while (sum >> 16) sum = (sum & 0xffffu) + (sum >> 16);
    return (uint16_t)~sum;
}

static void set16(uint8_t *bytes, uint16_t value) {
    bytes[0] = (uint8_t)(value >> 8);
    bytes[1] = (uint8_t)value;
}

int main(void) {
    uint8_t frame[14 + 20 + 8 + 32] = {0};
    uint8_t original[sizeof(frame)];
    uint8_t *payload = NULL;
    uint8_t *ip = frame + 14;
    uint8_t *udp = ip + 20;
    const uint8_t board_mac[6] = {2, 0, 0, 0, 1, 0x18};
    const uint8_t host_mac[6] = {2, 4, 6, 8, 10, 12};
    memcpy(frame, board_mac, 6);
    memcpy(frame + 6, host_mac, 6);
    set16(frame + 12, 0x0800);
    ip[0] = 0x45;
    set16(ip + 2, 20 + 8 + 32);
    ip[8] = 64;
    ip[9] = 17;
    const uint8_t host_ip[4] = {192, 168, 1, 11};
    const uint8_t board_ip[4] = {192, 168, 1, 10};
    memcpy(ip + 12, host_ip, 4);
    memcpy(ip + 16, board_ip, 4);
    set16(ip + 10, checksum(ip, 20));
    set16(udp, 12345);
    set16(udp + 2, 49201);
    set16(udp + 4, 8 + 32);
    for (unsigned i = 0; i < 32; ++i) udp[8 + i] = (uint8_t)(i ^ 0xa5);
    memcpy(original, frame, sizeof(frame));

    assert(eth_fast_probe_reflect(frame, sizeof(frame), 49201, &payload) == 32);
    assert(payload == udp + 8);
    assert(!memcmp(frame, host_mac, 6));
    assert(!memcmp(frame + 6, board_mac, 6));
    assert(!memcmp(ip + 12, board_ip, 4));
    assert(!memcmp(ip + 16, host_ip, 4));
    assert(udp[0] == original[14 + 20 + 2] && udp[1] == original[14 + 20 + 3]);
    assert(udp[2] == original[14 + 20] && udp[3] == original[14 + 20 + 1]);
    assert(checksum(ip, 20) == 0);
    assert(!memcmp(udp + 4, original + 14 + 20 + 4, 36));

    memcpy(frame, original, sizeof(frame));
    assert(!eth_fast_probe_reflect(frame, sizeof(frame), 49203, &payload));
    assert(!memcmp(frame, original, sizeof(frame)));
    set16(udp + 2, 49203);
    assert(eth_fast_probe_reflect(frame, sizeof(frame), 49203, &payload) == 32);
    assert(payload == udp + 8);

    memcpy(frame, original, sizeof(frame));
    ip[6] = 0x20;
    assert(!eth_fast_probe_reflect(frame, sizeof(frame), 49201, &payload));
    assert(payload == NULL);
    assert(!memcmp(frame, original, 14 + 6));
    memcpy(frame, original, sizeof(frame));
    set16(udp + 2, 49200);
    assert(!eth_fast_probe_reflect(frame, sizeof(frame), 49201, &payload));
    memcpy(frame, original, sizeof(frame));
    ip[10] ^= 1;
    assert(!eth_fast_probe_reflect(frame, sizeof(frame), 49201, &payload));
    memcpy(frame, original, sizeof(frame));
    assert(!eth_fast_probe_reflect(frame, sizeof(frame) - 1, 49201, &payload));
    puts("eth_fast_probe_frame_test PASS");
    return 0;
}
