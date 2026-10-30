`ifndef QBS_AKV_SHARED_READER_TYPES_SVH
`define QBS_AKV_SHARED_READER_TYPES_SVH

// Invoke inside the caller's package/module. No dependency on Ara interfaces.
`define QBS_AKV_SHARED_READER_TYPEDEF_REQ_T(__name, __vaddr_width) \
  typedef struct packed { \
    logic range_valid; \
    logic [(__vaddr_width)-1:0] range_vaddr; \
    logic [15:0] range_bytes; \
    logic [15:0] range_tag; \
    axi_pkg::cache_t range_cache; \
    axi_pkg::prot_t range_prot; \
    logic data_ready; \
    logic completion_ready; \
    logic fault_ready; \
  } __name;

`define QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(__name, __data_width, __vaddr_width, __exception_t) \
  typedef struct packed { \
    logic range_ready; \
    logic data_valid; \
    logic [(__data_width)-1:0] data; \
    logic [(__data_width)/8-1:0] data_strb; \
    logic [15:0] data_offset; \
    logic [15:0] data_tag; \
    logic completion_valid; \
    logic [15:0] completion_tag; \
    logic fault_valid; \
    qbs_pkg::qbs_read_fault_e fault_kind; \
    logic [(__vaddr_width)-1:0] fault_vaddr; \
    logic [15:0] fault_tag; \
    __exception_t fault_mmu_exception; \
    logic [31:0] range_count; \
    logic [31:0] translation_count; \
    logic [31:0] ar_count; \
    logic [31:0] r_beat_count; \
    logic [31:0] payload_byte_count; \
    logic [31:0] store_wait_cycles; \
    logic [31:0] r_backpressure_cycles; \
    logic [31:0] outstanding_occupancy_sum; \
    logic [1:0] outstanding_max; \
    logic [31:0] outstanding_full_cycles; \
    logic busy; \
  } __name;

`endif
