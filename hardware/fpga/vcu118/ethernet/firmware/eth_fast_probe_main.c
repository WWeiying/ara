#include "eth_fast_probe_frame.h"
#include "eth_loader_platform.h"

#include "lwip/init.h"
#include "lwip/pbuf.h"
#include "netif/ethernet.h"
#include "netif/xadapter.h"
#include "netif/xtopology.h"
#include "xaxiethernet.h"
#include "xil_printf.h"
#include "xparameters.h"

#include <string.h>

#if defined(ETH_LOADER_ARA) && !defined(ETH_PROBE_USE_CDMA)
#error "Ara integration requires the CDMA loader"
#endif

#ifdef ETH_PROBE_USE_CDMA
#include "eth_fast_load.h"
#include "xaxicdma.h"
#include "xtmrctr_l.h"
#include "xstatus.h"
#endif

#if NO_SYS != 1 || LWIP_IPV6 != 0
#error "The fast probe requires the standalone lwIP IPv4 raw-API BSP"
#endif

static struct netif ethernet;
struct netif *echo_netif = &ethernet;
volatile uint32_t eth_probe_stage;
volatile uint32_t eth_probe_echoed_frames;
volatile uint32_t eth_probe_echoed_bytes;
volatile uint32_t eth_probe_tx_drops;
volatile uint32_t eth_probe_ddr_bytes;
volatile uint32_t eth_probe_bad_frames;
#ifdef ETH_PROBE_USE_CDMA
volatile uint32_t eth_probe_cdma_error;
volatile uint32_t eth_probe_cdma_timeouts;
volatile uint32_t eth_probe_load_rejected;
volatile uint32_t eth_probe_cdma_ticks;
volatile uint32_t eth_probe_cdma_calls;
volatile uint32_t eth_probe_input_ticks;
volatile uint32_t eth_probe_tx_ticks;
volatile uint32_t eth_probe_profile_frames;
// CPU-only control objects use BRAM; DMA packet buffers remain in DDR.
static XAxiCdma cdma __attribute__((section(".data"))) = {0};
static struct eth_fast_load_state load_state __attribute__((section(".data"))) = {0};
#endif

#ifndef ETH_LOADER_ARA
#define DDR_PROBE_START UINT64_C(0x82000ff8)
#define DDR_PROBE_LIMIT (DDR_PROBE_START + UINT64_C(16) * 1024 * 1024)
#define DDR_PROBE_STRIDE 1392u

static int ddr_probe_roundtrip(uint8_t *payload, size_t payload_size) {
    uint32_t sequence;
    uint64_t address;
    size_t size, i;
    volatile uint8_t *memory;
    if (payload_size <= 8 || payload_size > 8 + DDR_PROBE_STRIDE ||
        memcmp(payload, "AFSP", 4) != 0) return -1;
    sequence = (uint32_t)payload[4] << 24 | (uint32_t)payload[5] << 16 |
               (uint32_t)payload[6] << 8 | payload[7];
    address = DDR_PROBE_START + (uint64_t)sequence * DDR_PROBE_STRIDE;
    size = payload_size - 8;
    if (address < DDR_PROBE_START || address >= DDR_PROBE_LIMIT ||
        size > DDR_PROBE_LIMIT - address) return -1;
    memory = (volatile uint8_t *)(uintptr_t)address;
    for (i = 0; i + 4 <= size; i += 4) {
        uint32_t word;
        memcpy(&word, payload + 8 + i, 4);
        *(volatile uint32_t *)(memory + i) = word;
    }
    for (; i < size; ++i) memory[i] = payload[8 + i];
    for (i = 0; i + 4 <= size; i += 4) {
        uint32_t word = *(volatile uint32_t *)(memory + i);
        memcpy(payload + 8 + i, &word, 4);
    }
    for (; i < size; ++i) payload[8 + i] = memory[i];
    // IPv4 permits a zero UDP checksum; the readback bytes might differ.
    payload[-2] = 0;
    payload[-1] = 0;
    eth_probe_ddr_bytes += size;
    return 0;
}
#endif

#ifdef ETH_PROBE_USE_CDMA
static int cdma_copy(uintptr_t source, uintptr_t destination, size_t size) {
    uint32_t start = XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1);
    uint32_t result = XAxiCdma_SimpleTransfer(&cdma, source, destination,
                                               (int)size, NULL, NULL);
    if (result != XST_SUCCESS) {
        eth_probe_cdma_error = result;
        return -1;
    }
    while (XAxiCdma_IsBusy(&cdma)) {
        if ((uint32_t)(XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1) - start) >
            10000000u) {
            ++eth_probe_cdma_timeouts;
            XAxiCdma_Reset(&cdma);
            return -1;
        }
    }
    eth_probe_cdma_error = XAxiCdma_GetError(&cdma);
    eth_probe_cdma_ticks +=
        XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1) - start;
    ++eth_probe_cdma_calls;
    return eth_probe_cdma_error ? -1 : 0;
}

#ifndef ETH_LOADER_ARA
static int cdma_probe_roundtrip(uint8_t *payload, size_t payload_size) {
    uint32_t sequence;
    uint64_t address;
    uintptr_t source;
    size_t size;
    if (payload_size <= 8 || payload_size > 8 + DDR_PROBE_STRIDE ||
        memcmp(payload, "AFSP", 4) != 0) return -1;
    sequence = (uint32_t)payload[4] << 24 | (uint32_t)payload[5] << 16 |
               (uint32_t)payload[6] << 8 | payload[7];
    address = DDR_PROBE_START + (uint64_t)sequence * DDR_PROBE_STRIDE;
    size = payload_size - 8;
    source = (uintptr_t)(payload + 8);
    if (address < DDR_PROBE_START || address >= DDR_PROBE_LIMIT ||
        size > DDR_PROBE_LIMIT - address ||
        !eth_fast_load_dma_source_ok(source, size)) return -1;
    if (cdma_copy(source, (uintptr_t)address, size) ||
        cdma_copy((uintptr_t)address, source, size)) return -1;
    payload[-2] = 0;
    payload[-1] = 0;
    eth_probe_ddr_bytes += size;
    return 0;
}
#endif

static uint16_t load_be16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] << 8 | p[1]);
}

static uint32_t load_be32(const uint8_t *p) {
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8 | p[3];
}

static void store_be16(uint8_t *p, uint16_t value) {
    p[0] = (uint8_t)(value >> 8);
    p[1] = (uint8_t)value;
}

static void store_be32(uint8_t *p, uint32_t value) {
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

static int fast_load_exchange(uint8_t *payload, const uint8_t *header, size_t size) {
    uint32_t session, arg0, arg1, address = 0;
    uint16_t opcode, status;
    uintptr_t source;
    if (size < 20 || memcmp(header, "AFLD", 4) != 0) return -1;
    session = load_be32(header + 4);
    opcode = load_be16(header + 8);
    arg0 = load_be32(header + 12);
    arg1 = load_be32(header + 16);
    if (load_be16(header + 10) != 0) return -1;
    switch (opcode) {
    case 4:
        if (size != 20 || arg0 != 0 || arg1 != 0) return -1;
        store_be32(payload + 12, (uint32_t)ETH_FAST_LOAD_DDR_START);
        store_be32(payload + 16, (uint32_t)ETH_FAST_LOAD_DDR_LIMIT);
        status = ETH_FAST_LOAD_OK;
        break;
    case 1:
        if (size != 20) return -1;
        status = eth_fast_load_begin(&load_state, session, arg0, arg1);
        break;
    case 2:
        if (size < 21 || size - 20 != arg1) return -1;
        status = eth_fast_load_prepare(&load_state, session, arg0, arg1, &address);
        source = (uintptr_t)(payload + 20);
        if (status == ETH_FAST_LOAD_OK &&
            !eth_fast_load_dma_source_ok(source, arg1))
            status = ETH_FAST_LOAD_RANGE;
        if (status == ETH_FAST_LOAD_OK) {
            if (cdma_copy(source, address, arg1) ||
                cdma_copy(address, source, arg1)) {
                status = ETH_FAST_LOAD_COPY;
            } else {
                eth_fast_load_commit(&load_state, arg0);
                eth_probe_ddr_bytes += arg1;
            }
        }
        break;
    case 3:
        if (size != 20 || arg1 != 0) return -1;
        status = eth_fast_load_finish(&load_state, session, arg0);
        break;
    default:
        return -1;
    }
    store_be16(payload + 8, opcode | UINT16_C(0x8000));
    store_be16(payload + 10, status);
    payload[-2] = 0;
    payload[-1] = 0;
    if (status != ETH_FAST_LOAD_OK) ++eth_probe_load_rejected;
    return 0;
}
#endif

static err_t probe_input(struct pbuf *p, struct netif *netif) {
#ifdef ETH_PROBE_USE_CDMA
    uint32_t profile_start = XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1);
    uint32_t tx_start;
#endif
    size_t data_size = 0;
    uint8_t *payload = NULL;
#ifndef ETH_LOADER_ARA
    int ddr_mode = 0;
#endif
#ifdef ETH_PROBE_USE_CDMA
#ifndef ETH_LOADER_ARA
    int cdma_mode = 0;
#endif
    int load_mode = 0;
    uint32_t header_words[26];
    uint8_t *frame_header = (uint8_t *)header_words;
    size_t header_size = 0;
#endif
    if (p && p->len == p->tot_len && !p->next) {
#ifdef ETH_PROBE_USE_CDMA
        // Ethernet + maximum IPv4 + UDP + loader header fit in local BRAM.
        header_size = p->len < sizeof(header_words) ? p->len : sizeof(header_words);
        if (((uintptr_t)p->payload & 3u) == 0) {
            size_t i = 0;
            const volatile uint32_t *source = p->payload;
            for (; i + 4 <= header_size; i += 4) header_words[i / 4] = source[i / 4];
            for (; i < header_size; ++i) frame_header[i] = ((uint8_t *)p->payload)[i];
        } else {
            memcpy(frame_header, p->payload, header_size);
        }
        data_size = eth_fast_probe_reflect(frame_header, p->len, 49204, &payload);
        if (data_size) load_mode = 1;
#ifndef ETH_LOADER_ARA
        if (!data_size) {
            data_size = eth_fast_probe_reflect(frame_header, p->len, 49203, &payload);
            if (data_size) cdma_mode = 1;
        }
        if (!data_size) {
            data_size = eth_fast_probe_reflect(frame_header, p->len, 49202, &payload);
            if (data_size) ddr_mode = 1;
            else data_size = eth_fast_probe_reflect(frame_header, p->len, 49201, &payload);
        }
#endif
        if (data_size) {
            size_t offset = (size_t)(payload - frame_header);
            size_t i = 0;
            if (((uintptr_t)p->payload & 3u) == 0) {
                volatile uint32_t *destination = p->payload;
                for (; i + 4 <= offset; i += 4) destination[i / 4] = header_words[i / 4];
            }
            for (; i < offset; ++i) ((uint8_t *)p->payload)[i] = frame_header[i];
            payload = (uint8_t *)p->payload + offset;
        }
#else
        data_size = eth_fast_probe_reflect(p->payload, p->len, 49202, &payload);
        if (data_size) ddr_mode = 1;
        else data_size = eth_fast_probe_reflect(p->payload, p->len, 49201, &payload);
#endif
    }
    if (!data_size) return ethernet_input(p, netif);
#ifdef ETH_PROBE_USE_CDMA
    if (load_mode && fast_load_exchange(payload,
            frame_header + (payload - (uint8_t *)p->payload), data_size)) {
        ++eth_probe_bad_frames;
        pbuf_free(p);
        return ERR_OK;
    }
#ifndef ETH_LOADER_ARA
    if (cdma_mode && cdma_probe_roundtrip(payload, data_size)) {
        ++eth_probe_bad_frames;
        pbuf_free(p);
        return ERR_OK;
    }
#endif
#endif
#ifndef ETH_LOADER_ARA
    if (ddr_mode && ddr_probe_roundtrip(payload, data_size)) {
        ++eth_probe_bad_frames;
        pbuf_free(p);
        return ERR_OK;
    }
#endif
#ifdef ETH_PROBE_USE_CDMA
    tx_start = XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1);
#endif
    if (netif->linkoutput(netif, p) == ERR_OK) {
        ++eth_probe_echoed_frames;
        eth_probe_echoed_bytes += data_size;
    } else {
        ++eth_probe_tx_drops;
    }
    pbuf_free(p);
#ifdef ETH_PROBE_USE_CDMA
    eth_probe_tx_ticks += XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1) - tx_start;
    eth_probe_input_ticks +=
        XTmrCtr_GetTimerCounterReg(XPAR_TIMER_BASEADDR, 1) - profile_start;
    ++eth_probe_profile_frames;
#endif
    return ERR_OK;
}

int main(void) {
    ip_addr_t address, netmask, gateway;
    XAxiEthernet_Config *mac_config;
    int topology_index;
    unsigned char mac[6] = {0x02, 0x00, 0x00, 0x00, 0x01, 0x18};

    eth_probe_stage = 1;
    if (eth_loader_platform_init()) {
        eth_probe_stage = 0x81;
        return 1;
    }
    eth_loader_platform_wait_phy_settle();
    eth_probe_stage = 2;
#ifdef ETH_PROBE_USE_CDMA
    {
        XAxiCdma_Config *config = XAxiCdma_LookupConfig(XPAR_AXICDMA_0_DEVICE_ID);
        if (!config || config->BaseAddress != XPAR_AXICDMA_0_BASEADDR ||
            !config->HasDRE || config->DataWidth != 64 ||
            XAxiCdma_CfgInitialize(&cdma, config, config->BaseAddress) != XST_SUCCESS) {
            eth_probe_stage = 0x86;
            return 1;
        }
    }
#endif
    mac_config = XAxiEthernet_LookupConfig(XPAR_AXIETHERNET_0_DEVICE_ID);
    topology_index = xtopology_find_index(XPAR_AXIETHERNET_0_BASEADDR);
    if (!mac_config || topology_index < 0 || topology_index >= xtopology_n_emacs ||
        xtopology[topology_index].emac_type != xemac_type_axi_ethernet ||
        XPAR_AXIETHERNET_0_CONNECTED_DMATX_INTR >= XPAR_INTC_0_NUM_INTR_INPUTS ||
        XPAR_AXIETHERNET_0_CONNECTED_DMARX_INTR >= XPAR_INTC_0_NUM_INTR_INPUTS ||
        XPAR_INTC_0_AXIETHERNET_0_VEC_ID >= XPAR_INTC_0_NUM_INTR_INPUTS ||
        (mac_config->TemacIntr != 0xff &&
         mac_config->TemacIntr != XPAR_INTC_0_AXIETHERNET_0_VEC_ID) ||
        (xtopology[topology_index].intc_baseaddr != 0 &&
         xtopology[topology_index].intc_baseaddr != XPAR_INTC_0_BASEADDR)) {
        eth_probe_stage = 0x82;
        return 1;
    }
    mac_config->TemacIntr = XPAR_INTC_0_AXIETHERNET_0_VEC_ID;
    xtopology[topology_index].intc_baseaddr = XPAR_INTC_0_BASEADDR;
    IP4_ADDR(&address, 192, 168, 1, 10);
    IP4_ADDR(&netmask, 255, 255, 255, 0);
    IP4_ADDR(&gateway, 192, 168, 1, 1);
    lwip_init();
    if (!xemac_add(&ethernet, &address, &netmask, &gateway,
                   mac, XPAR_AXIETHERNET_0_BASEADDR)) {
        eth_probe_stage = 0x83;
        return 1;
    }
    netif_set_default(&ethernet);
    eth_loader_platform_enable_interrupts();
    netif_set_up(&ethernet);
    ethernet.input = probe_input;
    eth_probe_stage = 8;
    xil_printf("Ethernet fast probe 192.168.1.10 ready\r\n");
    for (;;) {
        if (eth_loader_link_ticks) {
            eth_link_detect(&ethernet);
            --eth_loader_link_ticks;
        }
        xemacif_input(&ethernet);
    }
}
