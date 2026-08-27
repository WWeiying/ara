ENTRY(_start)

SECTIONS {
  . = 0x80000000;
  .text : { *(.text.init) *(.text .text.*) }
  .rodata : { *(.rodata .rodata.*) }
  PROVIDE(__global_pointer$ = . + 0x800);
  .data : { *(.data .data.*) }
  .bss : { *(.bss .bss.*) *(COMMON) }
  . = ALIGN(16);
  . += 16384;
  __stack_top = .;
}
