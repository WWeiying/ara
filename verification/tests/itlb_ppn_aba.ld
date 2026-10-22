OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text.init : { KEEP(*(.text.init)) }
  . = 0x80001000;
  .tohost : { *(.tohost) }
  . = 0x80002000;
  .text : { *(.text .text.*) }
  .rodata ALIGN(128) : { *(.rodata .rodata.*) }
  .data ALIGN(128) : { *(.data .data.*) }
  .sdata ALIGN(128) : { __global_pointer$ = . + 0x800; *(.srodata .srodata.* .sdata .sdata.*) }
  .bss ALIGN(128) : { __bss_start = .; *(.sbss .sbss.* .bss .bss.* COMMON) . = ALIGN(8); __bss_end = .; }
  _end = .;
  ASSERT(_end < 0x80055000, "Normal ELF/BSS must precede page A")
  .itlb_a 0x80055000 : { KEEP(*(.itlb_a)) }
  .itlb_b 0x801aa000 : { KEEP(*(.itlb_b)) }
  ASSERT(SIZEOF(.itlb_a) == 4096 && SIZEOF(.itlb_b) == 4096, "Exact two code pages")
  ASSERT(ADDR(.itlb_b) + SIZEOF(.itlb_b) < 0x801f0000, "Reserve upper64KB for stack")
  ASSERT(_start == 0x80000000, "Fixed boot")
}
