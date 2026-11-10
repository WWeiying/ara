/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_RISCV_ARA_STAGE4_H
#define HW_RISCV_ARA_STAGE4_H
#include "hw/boards.h"
void riscv_ara_stage4_init(MachineState *machine);
void riscv_ara_stage4_reset_vec(MachineState *machine, hwaddr rom_base,
                               hwaddr rom_size, uint64_t entry);
#endif
