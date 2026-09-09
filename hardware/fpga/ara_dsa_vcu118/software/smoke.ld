/* SPDX-License-Identifier: Apache-2.0 */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0x80000000, LENGTH = 128K }
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
  .text : { KEEP(*(.text.start)) *(.text .text.*) *(.rodata .rodata.*) } >ram :text
  .data : ALIGN(16) { __global_pointer$ = . + 0x800; *(.sdata .sdata.* .data .data.*) } >ram :data
  .bss (NOLOAD) : ALIGN(64) {
    __bss_start = .; *(.bss .bss.* .sbss .sbss.* COMMON)
    . = ALIGN(8); __bss_end = .;
  } >ram :data
  __stack_top = ORIGIN(ram) + LENGTH(ram);
  ASSERT(__bss_end + 8192 <= __stack_top, "Smoke test exceeds reserved RAM")
  /DISCARD/ : { *(.comment .eh_frame .note*) }
}
