/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ARA_FPGA_DEBUG_H
#define ARA_FPGA_DEBUG_H

#include <stdint.h>

#define FPGA_DEBUG_BASE UINT64_C(0x03010000)
#define FPGA_DEBUG_JTAG_BASE UINT32_C(0)
#define FPGA_DEBUG_MAGIC UINT32_C(0x41524442)
#define FPGA_DEBUG_ABI 1u
#define FPGA_DEBUG_CAP_HOST 1u
#define FPGA_DEBUG_CAP_DDR2 2u
#define FPGA_DEBUG_MAGIC_REG 0x00u
#define FPGA_DEBUG_ABI_REG 0x04u
#define FPGA_DEBUG_CAPS 0x08u
#define FPGA_DEBUG_FREQUENCY 0x0cu
#define FPGA_DEBUG_COMMAND 0x10u
#define FPGA_DEBUG_STATUS 0x14u
#define FPGA_DEBUG_SNAPSHOT_SEQUENCE 0x18u
#define FPGA_DEBUG_MARKER 0x1cu
#define FPGA_DEBUG_RESULT 0x20u
#define FPGA_DEBUG_RUN_ID 0x24u
#define FPGA_DEBUG_WATCHDOG 0x28u
#define FPGA_DEBUG_FLAGS 0x2cu
#define FPGA_DEBUG_DONE 0x30u
#define FPGA_DEBUG_MAILBOX 0x40u
#define FPGA_DEBUG_MAILBOX_WORDS 16u
#define FPGA_DEBUG_CLEAR 1u
#define FPGA_DEBUG_SNAPSHOT 2u
#define FPGA_DEBUG_FREEZE 4u
#define FPGA_DEBUG_RESUME 8u
#define FPGA_DEBUG_WATCHDOG_HIT 1u
#define FPGA_DEBUG_SOC_RESETN 1u
#define FPGA_DEBUG_FABRIC_READY 2u
#define FPGA_DEBUG_CLK_LOCKED 4u
#define FPGA_DEBUG_SYS_RST 8u

/* Snapshot fields are little-endian 64-bit words, read under sequence validation. */
#define FPGA_DEBUG_CORE_SNAPSHOT 0x100u
#define FPGA_DEBUG_DDR1_SNAPSHOT 0x180u
#define FPGA_DEBUG_DDR2_SNAPSHOT 0x200u
enum fpga_debug_core_field {
    FPGA_DEBUG_CYCLES, FPGA_DEBUG_RETIRED, FPGA_DEBUG_LAST_PC, FPGA_DEBUG_HEAD_PC,
    FPGA_DEBUG_LAST_TRAP_PC, FPGA_DEBUG_LAST_TRAP_CAUSE, FPGA_DEBUG_LAST_TRAP_TVAL,
    FPGA_DEBUG_TRAP_COUNT
};
enum fpga_debug_ddr_field {
    FPGA_DEBUG_AR_COUNT, FPGA_DEBUG_AW_COUNT, FPGA_DEBUG_R_BYTES, FPGA_DEBUG_W_BYTES,
    FPGA_DEBUG_AR_STALL, FPGA_DEBUG_AW_STALL, FPGA_DEBUG_R_STALL, FPGA_DEBUG_W_STALL,
    FPGA_DEBUG_READ_OUTSTANDING, FPGA_DEBUG_WRITE_OUTSTANDING,
    FPGA_DEBUG_LAST_AR_ADDR, FPGA_DEBUG_LAST_AW_ADDR, FPGA_DEBUG_ERROR_COUNT,
    FPGA_DEBUG_RESERVED_ERROR_ADDR, FPGA_DEBUG_LAST_ERROR_INFO
};
/* R_BYTES: 8 per pre-width-converter R handshake, NOT narrow payload/PHY bytes.
 * W_BYTES: popcount(WSTRB) on W handshakes. Outstanding: AR->RLAST and AW->B.
 * Error info: RESP[1:0], write(B)[2], ID[15:8]. Field 13 is reserved zero;
 * last AR/AW addresses are observations, never attributed to an error response.
 * Watchdog freezes/snapshots on no retirement; it does not stop the processor.
 */
static inline uint32_t fpga_debug_read(unsigned offset) {
    return *(volatile uint32_t *)(uintptr_t)(FPGA_DEBUG_BASE + offset);
}
static inline void fpga_debug_write(unsigned offset, uint32_t value) {
    *(volatile uint32_t *)(uintptr_t)(FPGA_DEBUG_BASE + offset) = value;
}
static inline void fpga_debug_fence(void) {
    __asm__ volatile("fence iorw,iorw" ::: "memory");
}
static inline int fpga_debug_present(void) {
    return fpga_debug_read(FPGA_DEBUG_MAGIC_REG) == FPGA_DEBUG_MAGIC &&
           fpga_debug_read(FPGA_DEBUG_ABI_REG) == FPGA_DEBUG_ABI;
}
static inline void fpga_debug_marker(uint32_t marker) {
    fpga_debug_fence();
    fpga_debug_write(FPGA_DEBUG_MARKER, marker);
}
/* CLEAR also resumes measurement. Cycles include small software boundary costs;
 * an identically fenced empty window can be measured for optional subtraction.
 * These helpers do not wait for an accelerator. The caller must use its own
 * completion protocol/fence before finish(). A CPU fence alone is not that wait.
 */
static inline void fpga_debug_begin(void) {
    fpga_debug_write(FPGA_DEBUG_COMMAND, FPGA_DEBUG_CLEAR);
    fpga_debug_fence();
}
static inline void fpga_debug_finish(uint32_t result) {
    fpga_debug_fence();
    fpga_debug_write(FPGA_DEBUG_COMMAND, FPGA_DEBUG_FREEZE);
    fpga_debug_fence();
    fpga_debug_write(FPGA_DEBUG_COMMAND, FPGA_DEBUG_SNAPSHOT);
    fpga_debug_write(FPGA_DEBUG_RESULT, result);
    fpga_debug_write(FPGA_DEBUG_WATCHDOG, 0);
    fpga_debug_fence();
    fpga_debug_write(FPGA_DEBUG_DONE, 1u);
    fpga_debug_fence();
}
static inline void fpga_debug_report_trap(uint64_t cause, uint64_t pc, uint64_t tval) {
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 0, (uint32_t)cause);
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 4, (uint32_t)(cause >> 32));
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 8, (uint32_t)pc);
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 12, (uint32_t)(pc >> 32));
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 16, (uint32_t)tval);
    fpga_debug_write(FPGA_DEBUG_MAILBOX + 20, (uint32_t)(tval >> 32));
    fpga_debug_marker(UINT32_C(0x54524150));
    fpga_debug_finish(UINT32_C(0x80000000) | (uint32_t)cause);
}
#endif
