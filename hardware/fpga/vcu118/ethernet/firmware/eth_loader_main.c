#include "eth_loader_ddr.h"
#include "eth_loader_platform.h"
#include "eth_loader_raw.h"

#include "lwip/init.h"
#include "lwip/tcp.h"
#include "netif/xadapter.h"
#include "netif/xtopology.h"
#include "xaxiethernet.h"
#include "xil_printf.h"
#include "xparameters.h"

#if NO_SYS != 1 || LWIP_IPV6 != 0
#error "The loader requires the standalone lwIP IPv4 raw-API BSP"
#endif

void tcp_fasttmr(void);
void tcp_slowtmr(void);

static struct netif ethernet;
struct netif *echo_netif = &ethernet;
static uint32_t scratch[8192] __attribute__((section(".sbss2")));
volatile uint32_t eth_loader_stage;

int main(void) {
    ip_addr_t address, netmask, gateway;
    XAxiEthernet_Config *mac_config;
    int topology_index;
    unsigned char mac[6] = {0x02, 0x00, 0x00, 0x00, 0x01, 0x18};

    eth_loader_stage = 1;
    if (eth_loader_platform_init()) {
        eth_loader_stage = 0x81;
        return 1;
    }
    eth_loader_stage = 2;
    eth_loader_platform_wait_phy_settle();
    eth_loader_stage = 3;
    mac_config = XAxiEthernet_LookupConfig(XPAR_AXIETHERNET_0_DEVICE_ID);
    if (!mac_config ||
        XPAR_AXIETHERNET_0_CONNECTED_DMATX_INTR >= XPAR_INTC_0_NUM_INTR_INPUTS ||
        XPAR_AXIETHERNET_0_CONNECTED_DMARX_INTR >= XPAR_INTC_0_NUM_INTR_INPUTS ||
        XPAR_INTC_0_AXIETHERNET_0_VEC_ID >= XPAR_INTC_0_NUM_INTR_INPUTS ||
        (mac_config->TemacIntr != 0xff &&
         mac_config->TemacIntr != XPAR_INTC_0_AXIETHERNET_0_VEC_ID)) {
        eth_loader_stage = 0x82;
        return 1;
    }
    mac_config->TemacIntr = XPAR_INTC_0_AXIETHERNET_0_VEC_ID;
    topology_index = xtopology_find_index(XPAR_AXIETHERNET_0_BASEADDR);
    if (topology_index < 0 || topology_index >= xtopology_n_emacs ||
        xtopology[topology_index].emac_type != xemac_type_axi_ethernet ||
        (xtopology[topology_index].intc_baseaddr != 0 &&
         xtopology[topology_index].intc_baseaddr != XPAR_INTC_0_BASEADDR)) {
        eth_loader_stage = 0x85;
        return 1;
    }
    // Vitis 2020.1 HSI can emit zero here even when AXI INTC is connected.
    xtopology[topology_index].intc_baseaddr = XPAR_INTC_0_BASEADDR;
    IP4_ADDR(&address, 192, 168, 1, 10);
    IP4_ADDR(&netmask, 255, 255, 255, 0);
    IP4_ADDR(&gateway, 192, 168, 1, 1);
    eth_loader_stage = 4;
    lwip_init();
    eth_loader_stage = 5;
    if (!xemac_add(&ethernet, &address, &netmask, &gateway,
                   mac, XPAR_AXIETHERNET_0_BASEADDR)) {
        eth_loader_stage = 0x83;
        xil_printf("Ethernet netif setup failed\r\n");
        return 1;
    }
    eth_loader_stage = 6;
    netif_set_default(&ethernet);
    eth_loader_platform_enable_interrupts();
    netif_set_up(&ethernet);
    eth_loader_stage = 7;
    if (eth_loader_raw_listen(49200, &eth_loader_ddr_io, NULL, scratch,
                              sizeof(scratch), ETH_LOADER_DDR_START,
                              ETH_LOADER_DDR_LIMIT)) {
        eth_loader_stage = 0x84;
        xil_printf("Ethernet loader listen failed\r\n");
        return 1;
    }
    eth_loader_stage = 8;
    xil_printf("Ethernet loader 192.168.1.10:49200 ready; transfer only\r\n");
    for (;;) {
        if (eth_loader_fast_ticks) {
            tcp_fasttmr();
            --eth_loader_fast_ticks;
        }
        if (eth_loader_slow_ticks) {
            tcp_slowtmr();
            --eth_loader_slow_ticks;
        }
        if (eth_loader_link_ticks) {
            eth_link_detect(&ethernet);
            --eth_loader_link_ticks;
        }
        xemacif_input(&ethernet);
    }
}
