OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 0x01000000 }
SECTIONS {
    . = ORIGIN(RAM);
    .text : { KEEP(*(.text._start)) *start.o(.text) *(.text .text.*) } > RAM
    .rodata : { *(.rodata .rodata.*) } > RAM
    .data : { *(.data .data.*) } > RAM
    .sdata : { __global_pointer$ = . + 0x800; *(.sdata .sdata.*) } > RAM
    .bss (NOLOAD) : { . = ALIGN(64); *(.sbss .sbss.* .bss .bss.* COMMON) } > RAM
    _image_end = .;
    _stack_top = 0x80fe0000;
    ASSERT(_image_end < 0x80f00000, "Directed image overlaps reserved fault/stack region")
}
