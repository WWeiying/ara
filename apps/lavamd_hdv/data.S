// Data section for lavamd_asm: anchors .data/TLS layout and holds the
// neighbour-particle arrays + reference params + force outputs.  Values are
// filled at runtime in main(); here they are just zero-reserved storage.
.section .data,"aw",@progbits

.global bx
.balign 64
bx:      .space 256*4
.global by
.balign 64
by:      .space 256*4
.global bz
.balign 64
bz:      .space 256*4
.global bv
.balign 64
bv:      .space 256*4
.global bq
.balign 64
bq:      .space 256*4
.global aparams
.balign 8
aparams: .space 5*4
.global fout_v
.balign 8
fout_v:  .space 4*4
.global fout_s
.balign 8
fout_s:  .space 4*4
