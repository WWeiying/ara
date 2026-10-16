#include "eth_fast_probe_frame.h"

#include <string.h>

#define ETH_HEADER 14u
#define IPV4_MIN_HEADER 20u
#define UDP_HEADER 8u

static const uint8_t board_mac[6] = {0x02, 0x00, 0x00, 0x00, 0x01, 0x18};
static const uint8_t board_ip[4] = {192, 168, 1, 10};

static uint16_t be16(const uint8_t *data) {
    return (uint16_t)((uint16_t)data[0] << 8 | data[1]);
}

static int valid_ipv4_checksum(const uint8_t *header, size_t size) {
    uint32_t sum = 0;
    for (size_t i = 0; i < size; i += 2) sum += be16(header + i);
    while (sum >> 16) sum = (sum & 0xffffu) + (sum >> 16);
    return sum == 0xffffu;
}

size_t eth_fast_probe_reflect(uint8_t *frame, size_t frame_size,
                              uint16_t port, uint8_t **payload) {
    uint8_t swap[6];
    uint8_t *ip;
    uint8_t *udp;
    size_t ip_header, ip_size, udp_size;
    if (payload) *payload = NULL;
    if (!frame || !payload || frame_size < ETH_HEADER + IPV4_MIN_HEADER + UDP_HEADER ||
        memcmp(frame, board_mac, sizeof(board_mac)) != 0 ||
        be16(frame + 12) != 0x0800u) return 0;
    ip = frame + ETH_HEADER;
    ip_header = (size_t)(ip[0] & 0x0fu) * 4u;
    if ((ip[0] >> 4) != 4 || ip_header < IPV4_MIN_HEADER ||
        ip_header > frame_size - ETH_HEADER ||
        ip[9] != 17 || memcmp(ip + 16, board_ip, sizeof(board_ip)) != 0 ||
        (be16(ip + 6) & 0x3fffu) != 0 ||
        !valid_ipv4_checksum(ip, ip_header)) return 0;
    ip_size = be16(ip + 2);
    if (ip_size < ip_header + UDP_HEADER || ip_size > frame_size - ETH_HEADER)
        return 0;
    udp = ip + ip_header;
    udp_size = be16(udp + 4);
    if (be16(udp + 2) != port || udp_size < UDP_HEADER ||
        udp_size != ip_size - ip_header) return 0;

    memcpy(swap, frame, 6);
    memcpy(frame, frame + 6, 6);
    memcpy(frame + 6, swap, 6);
    memcpy(swap, ip + 12, 4);
    memcpy(ip + 12, ip + 16, 4);
    memcpy(ip + 16, swap, 4);
    memcpy(swap, udp, 2);
    memcpy(udp, udp + 2, 2);
    memcpy(udp + 2, swap, 2);
    // Source/destination exchange leaves both IPv4 and UDP checksums unchanged.
    *payload = udp + UDP_HEADER;
    return udp_size - UDP_HEADER;
}
