#ifndef ETH_LOADER_PLATFORM_H
#define ETH_LOADER_PLATFORM_H

#include <stdint.h>

extern volatile uint32_t eth_loader_fast_ticks;
extern volatile uint32_t eth_loader_slow_ticks;
extern volatile uint32_t eth_loader_link_ticks;

int eth_loader_platform_init(void);
void eth_loader_platform_wait_phy_settle(void);
void eth_loader_platform_enable_interrupts(void);

#endif
