/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0x80000000, LENGTH = 64K }
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
  .text : { KEEP(*(.text.start)) *(.text .text.*) *(.rodata .rodata.*) } >ram :text
  .data : ALIGN(16) { __global_pointer$ = . + 0x800; *(.sdata .sdata.* .data .data.*) } >ram :data
  .bss (NOLOAD) : ALIGN(16) {
    __bss_start = .; *(.bss .bss.* .sbss .sbss.* COMMON)
    . = ALIGN(8); __bss_end = .;
  } >ram :data
  .stack (NOLOAD) : ALIGN(16) { . += 4096; __stack_top = .; } >ram :data
  ASSERT(__stack_top <= ORIGIN(ram) + LENGTH(ram), "Host smoke exceeds DDR reservation")
  /DISCARD/ : { *(.comment .eh_frame .note*) }
}
