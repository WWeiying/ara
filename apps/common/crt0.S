// Copyright 2020 ETH Zurich and University of Bologna.
//
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Author: Samuel Riedel, ETH Zurich
//         Matheus Cavalcante, ETH Zurich

.globl _start
.globl _eoc
.globl _fail
.section .text;
.section .text.init;

#include "encoding.h"

// For the riscv-tests environment
.weak mtvec_handler
.weak stvec_handler
.weak rvtest_init

_start:
    // Initialize global pointer
    .option push
    .option norelax
    1:auipc gp, %pcrel_hi(__global_pointer$)
      addi  gp, gp, %pcrel_lo(1b)
    .option pop

    /* reset vector */
    j reset_vector
reset_vector:
    li      x1, 0
    li      x4, 0
    li      x5, 0
    li      x6, 0
    li      x7, 0
    li      x8, 0
    li      x9, 0
    li      x10, 0
    li      x11, 0
    li      x12, 0
    li      x13, 0
    li      x14, 0
    li      x15, 0
    li      x16, 0
    li      x17, 0
    li      x18, 0
    li      x19, 0
    li      x20, 0
    li      x21, 0
    li      x22, 0
    li      x23, 0
    li      x24, 0
    li      x25, 0
    li      x26, 0
    li      x27, 0
    li      x28, 0
    li      x29, 0
    li      x30, 0
    li      x31, 0
    // The Ara simulation exposes DRAM end through the CTRL block.  The
    // VCU118 Cheshire design has DDR at 0x80000000 but does not expose that
    // simulation-only CTRL window, so use the top of the 2 MiB bare-metal
    // image region for FPGA-hosted applications.
#if defined(ARA_FPGA)
    li      sp, 0x80200000
#else
    la      t0, dram_end_address_reg
    ld      sp, 0(t0)
#endif
#if defined(ARA_FPGA)
    // The Cheshire boot protocol may leave the 16550 in an unknown state
    // when control is transferred to a bare-metal benchmark.  Match the
    // fixed 50 MHz VCU118 setup used by the board smoke test before any
    // benchmark code can print through serial.c.
    li      t0, 0x03002000
    sw      zero, 4(t0)       // IER = 0
    li      t1, 0x80
    sw      t1, 12(t0)        // LCR: access divisor latch
    li      t1, 27
    sw      t1, 0(t0)         // DLL: 115200 baud at 50 MHz
    sw      zero, 4(t0)       // DLM
    li      t1, 3
    sw      t1, 12(t0)        // LCR: 8 data bits, no parity, 1 stop
    li      t1, 7
    sw      t1, 8(t0)         // FCR: enable and clear FIFOs
    sw      zero, 16(t0)      // MCR
#endif
    // Set up a PMP to permit all accesses
    li t0, (1 << (31 + (__riscv_xlen / 64) * (53 - 31))) - 1
    csrw pmpaddr0, t0
#if defined(ARA_FPGA)
    la      t0, trap_vector
#endif
    csrw    mtvec, t0
    csrwi   medeleg, 0
    csrwi   mideleg, 0
    // If an stvec_handler is defined, delegate exceptions to it
    la t0, stvec_handler
    beqz t0, 1f
    csrw stvec, t0
    li t0, (1 << CAUSE_LOAD_PAGE_FAULT) |  \
           (1 << CAUSE_STORE_PAGE_FAULT) | \
           (1 << CAUSE_FETCH_PAGE_FAULT) | \
           (1 << CAUSE_MISALIGNED_FETCH) | \
           (1 << CAUSE_USER_ECALL) |       \
           (1 << CAUSE_BREAKPOINT)
    csrw medeleg, t0
    .align 2
1:  csrwi mstatus, 0
#if defined(ARA_FPGA)
    // The VCU118 UART loader enters this ELF directly in M-mode.  It does
    // not provide a lower-privilege PMP/S-mode runtime for bare-metal apps,
    // so keep FPGA benchmarks in M-mode, like the board smoke program.
    li      t0, MSTATUS_MPP
    csrs    mstatus, t0
#endif
    // Enable FP Extension
    li      t0, (MSTATUS_FS & (MSTATUS_FS >> 1))
    csrs    mstatus, t0
    csrwi   fcsr, 0
    // Enable Vector Extension
    li      t0, (MSTATUS_VS & (MSTATUS_VS >> 1))
    csrs    mstatus, t0
    // Enable the counters
    csrsi   mcounteren, 1 | (1 << 1) | (1 << 2)
    csrsi   scounteren, 1 | (1 << 1) | (1 << 2)
    // Call the RISC-V Test initialization function, if it exists
    la t0, rvtest_init
    beqz t0, 1f
    jalr t0
1:  // Return to _eoc
    la      ra, _eoc
    // Call main
    la      t0, main
    csrw    mepc, t0
    mret

    .align 2
trap_vector:
    // Jump to the mtvec_handler, if it exists
    call print_trap_cause
    la t5, mtvec_handler
    beqz t5, 1f
    jr t5
1:  csrr a0, mcause
    j _fail

    .align 2
_eoc:
#if defined(ARA_FPGA)
1:  wfi
    j       1b
#else
    la t0, eoc_address_reg
    sd a0, 0(t0)
    jal x0, _eoc
#endif

    .align 2
_fail:
#if defined(ARA_FPGA)
    j       _eoc
#else
    la t0, eoc_address_reg
    sd a0, 0(t0)
    jal x0, _eoc
#endif

.section .data
