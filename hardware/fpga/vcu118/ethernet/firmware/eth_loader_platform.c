#include "eth_loader_platform.h"

#include "mb_interface.h"
#include "xintc.h"
#include "xparameters.h"
#include "xstatus.h"
#include "xtmrctr_l.h"

#if XPAR_MICROBLAZE_USE_DCACHE || XPAR_MICROBLAZE_USE_ICACHE
#error "The loader requires the cache-disabled MicroBlaze configuration"
#endif

#if XPAR_TIMER_CLOCK_FREQ_HZ != 100000000U
#error "Review the loader timer interval for this hardware clock"
#endif

#define TIMER_LOAD (XPAR_TIMER_CLOCK_FREQ_HZ / 4U)

volatile uint32_t eth_loader_fast_ticks;
volatile uint32_t eth_loader_slow_ticks;
volatile uint32_t eth_loader_link_ticks;

static XIntc interrupt_controller;

static void timer_interrupt(void *context) {
    static unsigned quarters;
    (void)context;
    ++eth_loader_fast_ticks;
    if (++quarters == 2) {
        ++eth_loader_slow_ticks;
    } else if (quarters == 4) {
        ++eth_loader_slow_ticks;
        ++eth_loader_link_ticks;
        quarters = 0;
    }

    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 0,
                                XTC_CSR_INT_OCCURED_MASK | XTC_CSR_LOAD_MASK);
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 0,
                                XTC_CSR_ENABLE_TMR_MASK | XTC_CSR_ENABLE_INT_MASK |
                                XTC_CSR_AUTO_RELOAD_MASK | XTC_CSR_DOWN_COUNT_MASK);
    XIntc_AckIntr(XPAR_INTC_0_BASEADDR, XPAR_TIMER_INTERRUPT_MASK);
}

int eth_loader_platform_init(void) {
    if (XIntc_Initialize(&interrupt_controller, XPAR_INTC_0_DEVICE_ID) != XST_SUCCESS ||
        XIntc_Start(&interrupt_controller, XIN_REAL_MODE) != XST_SUCCESS) {
        return -1;
    }
    XIntc_MasterEnable(XPAR_INTC_0_BASEADDR);
    microblaze_register_handler((XInterruptHandler)XIntc_InterruptHandler,
                                &interrupt_controller);
    XIntc_RegisterHandler(XPAR_INTC_0_BASEADDR,
                          XPAR_INTC_0_TMRCTR_0_VEC_ID,
                          (XInterruptHandler)timer_interrupt, NULL);
    XTmrCtr_SetLoadReg(XPAR_TIMER_BASEADDR, 0, TIMER_LOAD);
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 0,
                                XTC_CSR_INT_OCCURED_MASK | XTC_CSR_LOAD_MASK);
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 0,
                                XTC_CSR_ENABLE_TMR_MASK | XTC_CSR_ENABLE_INT_MASK |
                                XTC_CSR_AUTO_RELOAD_MASK | XTC_CSR_DOWN_COUNT_MASK);
    XTmrCtr_SetLoadReg(XPAR_TIMER_BASEADDR, 1, 0);
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 1, XTC_CSR_LOAD_MASK);
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 1,
                                XTC_CSR_ENABLE_TMR_MASK | XTC_CSR_AUTO_RELOAD_MASK);
    XIntc_Enable(&interrupt_controller, XPAR_INTC_0_TMRCTR_0_VEC_ID);
    return 0;
}

void eth_loader_platform_wait_phy_settle(void) {
    while (!(XTmrCtr_GetControlStatusReg(XPAR_TIMER_BASEADDR, 0) &
             XTC_CSR_INT_OCCURED_MASK)) {}
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 0,
                                XTC_CSR_INT_OCCURED_MASK | XTC_CSR_LOAD_MASK);
    XTmrCtr_SetControlStatusReg(XPAR_TIMER_BASEADDR, 0,
                                XTC_CSR_ENABLE_TMR_MASK | XTC_CSR_ENABLE_INT_MASK |
                                XTC_CSR_AUTO_RELOAD_MASK | XTC_CSR_DOWN_COUNT_MASK);
    XIntc_AckIntr(XPAR_INTC_0_BASEADDR, XPAR_TIMER_INTERRUPT_MASK);
}

void eth_loader_platform_enable_interrupts(void) {
    microblaze_enable_interrupts();
}
