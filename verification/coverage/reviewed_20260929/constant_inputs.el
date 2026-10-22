// Configuration-specific scalar input toggles only. No functional branch
// or software-visible interrupt/debug state is excluded.
// ara_system.sv:182-185 ties these inputs to zero; cva6.sv:1193,1250,1251
// forwards the same inputs to csr_regfile_i.
CHECKSUM: "376119937 1939539040"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ariane
ANNOTATION: "External IPI/timer/debug inputs tied zero in this compiled SoC; retain software interrupt and debug coverage"
Toggle ipi_i "net ipi_i"
Toggle time_irq_i "net time_irq_i"
Toggle debug_req_i "net debug_req_i"

CHECKSUM: "1371260681 1176918775"
INSTANCE: ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i
ANNOTATION: "CVA6 forwards tied-zero external IPI/timer/debug inputs; no CSR operation excluded"
Toggle ipi_i "net ipi_i"
Toggle time_irq_i "net time_irq_i"
Toggle debug_req_i "net debug_req_i"
