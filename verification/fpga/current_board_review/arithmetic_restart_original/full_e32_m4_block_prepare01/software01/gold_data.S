/* Data only: no new instructions. Payloads are pinned existing full5985 gold. */
.section .rodata.e32m4_gold,"a",@progbits
.balign 8
.global e32m4_expected_blocks
.type e32m4_expected_blocks,@object
e32m4_expected_blocks:
.incbin "/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/arithmetic_restart_original/full_e32_m4_source_model01/generated01/dictionary64.bin"
.size e32m4_expected_blocks, .-e32m4_expected_blocks
.balign 2
.global e32m4_expected_ids
.type e32m4_expected_ids,@object
e32m4_expected_ids:
.incbin "/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/arithmetic_restart_original/full_e32_m4_source_model01/generated01/indices_u16le.bin"
.size e32m4_expected_ids, .-e32m4_expected_ids
.section .note.GNU-stack,"",@progbits
