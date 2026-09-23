/* SPDX-License-Identifier: Apache-2.0 */
#include "fpga_debug.h"

static volatile uint64_t memory_check[32];

void host_report_trap(uint64_t cause, uint64_t pc, uint64_t tval) {
    fpga_debug_report_trap(cause, pc, tval);
}

int main(void) {
    if (!fpga_debug_present() || !(fpga_debug_read(FPGA_DEBUG_CAPS) & FPGA_DEBUG_CAP_HOST)) {
        /* The debug block cannot be trusted: do not manufacture a done record. */
        return 1;
    }
    fpga_debug_begin();
    fpga_debug_marker(UINT32_C(0x484f5354));
    fpga_debug_write(FPGA_DEBUG_MAILBOX, FPGA_DEBUG_MAGIC);
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 4, fpga_debug_read(FPGA_DEBUG_RUN_ID));
#ifdef HOST_DDR2_CANARY
    if (fpga_debug_read(FPGA_DEBUG_CAPS) & FPGA_DEBUG_CAP_DDR2) {
        volatile uint64_t *first = (volatile uint64_t *)(uintptr_t)UINT64_C(0xffff0000);
        volatile uint64_t *second = (volatile uint64_t *)(uintptr_t)UINT64_C(0x17fff0000);
        *first = UINT64_C(0x0123456789abcdef);
        *second = UINT64_C(0xfedcba9876543210);
        fpga_debug_fence();
        if (*first != UINT64_C(0x0123456789abcdef) || *second != UINT64_C(0xfedcba9876543210)) {
            fpga_debug_finish(3);
            return 3;
        }
        fpga_debug_write(FPGA_DEBUG_MAILBOX + 8, UINT32_C(0x44445232));
    } else {
        /* This ELF specifically tests the >4-GiB CPU path; absent is not PASS. */
        fpga_debug_finish(4);
        return 4;
    }
#endif
#ifdef HOST_FORCE_TRAP
    __asm__ volatile(".word 0" ::: "memory");
#endif
    for (unsigned i = 0; i < 32; ++i) {
        memory_check[i] = UINT64_C(0x0123456789abcdef) ^ (uint64_t)i;
    }
    fpga_debug_fence();
    for (unsigned i = 0; i < 32; ++i) {
        if (memory_check[i] != (UINT64_C(0x0123456789abcdef) ^ (uint64_t)i)) {
            fpga_debug_finish(2);
            return 2;
        }
    }
    fpga_debug_marker(UINT32_C(0x50415353));
    fpga_debug_finish(0);
    return 0;
}
