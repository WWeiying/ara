ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text : { *(.text.init) *(.text .text.*) }
  .rodata : { *(.rodata .rodata.*) }
  PROVIDE(__global_pointer$ = . + 0x800);
  .data : { *(.data .data.*) *(.sdata .sdata.*) }
  .bss : {
    __bss_start = .;
    *(.bss .bss.*) *(.sbss .sbss.*) *(COMMON)
    __bss_end = .;
  }
  . = ALIGN(16);
  . += 65536;
  __stack_top = .;
}
