OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS
{
  . = 0x80000000;
  .text.init : { KEEP(*(.text.init)) }
  . = ALIGN(0x1000);
  .tohost : { *(.tohost) }
  . = ALIGN(0x1000);
  .text : { *(.text .text.*) }
  .rodata ALIGN(128) : { *(.rodata .rodata.*) }
  .data ALIGN(128) : { *(.data .data.*) }
  .sdata ALIGN(128) : {
    __global_pointer$ = . + 0x800;
    *(.srodata .srodata.* .sdata .sdata.*)
  }
  .bss ALIGN(128) : {
    __bss_start = .;
    *(.sbss .sbss.* .bss .bss.* COMMON)
    . = ALIGN(8);
    __bss_end = .;
  }
  _end = .;
  ASSERT(_start == 0x80000000, "VCS fixed boot address must equal ELF entry")
  ASSERT(_end < 0x80100000, "test image must not overlap stack")
}
