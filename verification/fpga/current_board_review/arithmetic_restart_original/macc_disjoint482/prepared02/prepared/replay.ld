OUTPUT_ARCH("riscv")
ENTRY(_start)
MEMORY { L2 (rwx) : ORIGIN = 0x80000000, LENGTH = 1M }
SECTIONS {
  .text : { *(.text.init) *(.text .text.*) } > L2
  .rodata : ALIGN(64) { *(.rodata .rodata.*) } > L2
  .data : ALIGN(64) { *(.data .data.*) *(.sdata .sdata.*) } > L2
  .tohost : ALIGN(64) { *(.tohost) } > L2
  __global_pointer$ = . + 0x800;
  .bss (NOLOAD) : ALIGN(64) {
    __bss_start = .;
    *(.bss .bss.* .sbss .sbss.*) *(COMMON)
    . = ALIGN(8);
    __bss_end = .;
  } > L2
  __stack_top = ORIGIN(L2) + LENGTH(L2) - 16;
  ASSERT(__bss_end < __stack_top - 65536, "replay exceeds L2/stack budget")
}
