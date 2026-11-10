/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Bare-metal ELF transport only: not an Ara device/timing model. */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "qemu/units.h"
#include "system/address-spaces.h"
#include "system/runstate.h"
#include "chardev/char-fe.h"
#include "hw/riscv/ara_stage4.h"
#include "hw/loader.h"

typedef struct {
    MemoryRegion control;
    MemoryRegion uart;
    CharBackend console;
    uint64_t dram_end;
} AraStage4Transport;

static uint64_t ara_control_read(void *opaque, hwaddr address, unsigned size)
{
    AraStage4Transport *s = opaque;
    if (size == 8 && address == 8) {
        return UINT64_C(0x80000000);
    }
    if (size == 8 && address == 16) {
        return s->dram_end;
    }
    return 0;
}

static void ara_control_write(void *opaque, hwaddr address, uint64_t value,
                               unsigned size)
{
    (void)opaque;
    if (address == 0 && size == 8) {
        /* Never hide an error by truncating a nonzero 64-bit return to zero. */
        qemu_system_shutdown_request_with_code(SHUTDOWN_CAUSE_GUEST_SHUTDOWN,
                                               value ? 1 : 0);
    }
    /* event_trigger/hw_cnt_en have no timing semantics in this transport. */
}

static void ara_uart_write(void *opaque, hwaddr address, uint64_t value,
                            unsigned size)
{
    AraStage4Transport *s = opaque;
    uint8_t byte = value;
    if (address == 0 && size == 1) {
        qemu_chr_fe_write_all(&s->console, &byte, 1);
    }
}

static const MemoryRegionOps ara_control_ops = {
    .read = ara_control_read, .write = ara_control_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 8, .max_access_size = 8 },
    .impl = { .min_access_size = 8, .max_access_size = 8 },
};

static const MemoryRegionOps ara_uart_ops = {
    .write = ara_uart_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
    .impl = { .min_access_size = 1, .max_access_size = 1 },
};

void riscv_ara_stage4_init(MachineState *machine)
{
    AraStage4Transport *s;
    Chardev *chr = qemu_chr_find("ara-stage4");

    if (machine->smp.cpus != 1 || machine->ram_size < 16 * MiB ||
        machine->ram_size > 512 * MiB || !chr) {
        error_report("x-ara-stage4 requires one hart, 16..512 MiB RAM, "
                     "and -chardev stdio,id=ara-stage4");
        exit(1);
    }
    s = g_new0(AraStage4Transport, 1);
    s->dram_end = UINT64_C(0x80000000) + machine->ram_size;
    qemu_chr_fe_init(&s->console, chr, &error_fatal);
    memory_region_init_io(&s->control, OBJECT(machine), &ara_control_ops, s,
                          "ara-stage4-control", 0x1000);
    memory_region_init_io(&s->uart, OBJECT(machine), &ara_uart_ops, s,
                          "ara-stage4-uart", 0x1000);
    memory_region_add_subregion(get_system_memory(), UINT64_C(0xd0000000),
                               &s->control);
    memory_region_add_subregion(get_system_memory(), UINT64_C(0xc0000000),
                               &s->uart);
}

void riscv_ara_stage4_reset_vec(MachineState *machine, hwaddr rom_base,
                               hwaddr rom_size, uint64_t entry)
{
    /* Frozen crt0 sets pmpaddr0, but not pmpcfg0, before mret to U mode.
     * Establish its original permissive bare-metal platform assumption here,
     * never by changing the ELF or granting AKV guest-memory admission. */
    uint32_t boot[] = {
        0xfff00293, /* addi t0, zero, -1 */
        0x3b029073, /* csrw pmpaddr0, t0 */
        0x01f00293, /* addi t0, zero, 31: NAPOT/R/W/X, unlocked */
        0x3a029073, /* csrw pmpcfg0, t0 */
        0x00000297, /* auipc t0, 0 */
        0x0102b283, /* ld t0, 16(t0) */
        0x00028067, /* jalr zero, 0(t0) */
        0x00000013, /* nop; align address literal */
        (uint32_t)entry, (uint32_t)(entry >> 32),
    };
    if (!machine->firmware || strcmp(machine->firmware, "none") ||
        !machine->kernel_filename || entry != UINT64_C(0x80000000) ||
        rom_size < sizeof(boot)) {
        error_report("x-ara-stage4 requires -bios none and unchanged ELF at 0x80000000");
        exit(1);
    }
    for (unsigned i = 0; i < ARRAY_SIZE(boot); ++i) {
        boot[i] = cpu_to_le32(boot[i]);
    }
    rom_add_blob_fixed_as("ara-stage4.reset", boot, sizeof(boot),
                          rom_base, &address_space_memory);
}
