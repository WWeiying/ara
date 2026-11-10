OUTPUT_ARCH("riscv")
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 2M }
SECTIONS {
  .text : { *(.text.init) *(.text .text.*) } > RAM
  .rodata : ALIGN(64) { *(.rodata .rodata.*) } > RAM
  .data : ALIGN(64) { *(.data .data.*) *(.sdata .sdata.*) } > RAM
  .tohost : ALIGN(64) { KEEP(*(.tohost)) } > RAM
  __global_pointer$ = . + 0x800;
  .bss (NOLOAD) : ALIGN(64) {
    __bss_start = .;
    *(.bss .bss.* .sbss .sbss.*) *(COMMON)
    . = ALIGN(8);
    __bss_end = .;
  } > RAM
  __stack_top = ORIGIN(RAM) + LENGTH(RAM) - 16;
  ASSERT(__bss_end < __stack_top - 65536, "test exceeds memory/stack budget")
}
