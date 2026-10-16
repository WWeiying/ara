OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS { code PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
  . = 0x80000000;
  .text : { *(.text.init) *(.text*) } :code
  . = 0x81000000;
  .data : { *(.data*) *(.bss*) } :data
}
