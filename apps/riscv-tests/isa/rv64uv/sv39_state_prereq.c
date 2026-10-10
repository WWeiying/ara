// Actual-SoC S/Sv39 directed test; see verification/cva6/sv39_state_prereq.md.
#include "vector_macros.h"

#if !defined(__clang__) || defined(vec) || defined(ARA_FPGA) || defined(ARA_LINUX) || defined(__SPIKE__)
#error "Use the non-ZCC scalar-C bare-metal SoC build (vec=0)"
#endif
#if NR_LANES != 4 || VLEN != 1024
#error "This frozen test targets config=default: 4 lanes, VLEN=1024"
#endif

#define PLANNED_CHECKS 116
#define FAILURE_CAPACITY 128
#if FAILURE_CAPACITY < PLANNED_CHECKS
#error "Failure log must hold every planned check"
#endif
#define DONE UINT64_C(0x73763339707265)
#define GUARD UINT32_C(0x6b6b6b6b)
#define VA_BASE UINT64_C(0x40000000)
#define RAM_BASE UINT64_C(0x80000000)
#define RAM_END UINT64_C(0xc0000000)
#define SV39 (UINT64_C(8) << 60)
#define LEAF (PTE_V | PTE_R | PTE_W | PTE_A | PTE_D)
#define VS_INITIAL (MSTATUS_VS & (MSTATUS_VS >> 1))
#define TRAP_STATUS_MASK (MSTATUS_MPP | MSTATUS_MPIE | MSTATUS_MIE | MSTATUS_MPRV | MSTATUS_MPV)
#define READ_CSR(csr, value) \
  asm volatile("csrr %0, " #csr : "=r"(value) : : "memory")
#define WRITE_CSR(csr, value) \
  asm volatile("csrw " #csr ", %0" : : "r"((uint64_t)(value)) : "memory")
#define STR_(x) #x
#define STR(x) STR_(x)
#define OFF(x) STR(8 * x)

// Shared with basic asm: all state slots are 64 bits, explicitly initialized.
#define PHASE 0
#define FATAL 1
#define TRAPS 2
#define LOAD_FIXED 3
#define STORE_FIXED 4
#define S_DONE 5
#define S_SATP 6
#define SCALAR_LOAD 7
#define SCALAR_RELOAD 8
#define S_VL 9
#define S_VTYPE 10
#define LOAD_VSTART 11
#define STORE_VSTART 12
#define RETURN_STATUS 13
#define CONTROL_VSTART 14
#define STATE_SLOTS 15

static volatile uint64_t state[STATE_SLOTS] __attribute__((used));
// mcause, mepc, mtval, vstart, mstatus, phase, invalid PTE, VL.
static volatile uint64_t traps[4][8] __attribute__((used));
static volatile uint64_t root_pt[512] __attribute__((used, aligned(4096)));
static volatile uint64_t mid_pt[512] __attribute__((used, aligned(4096)));
static volatile uint64_t leaf_pt[512] __attribute__((used, aligned(4096)));
// Physical gaps prevent an accidentally contiguous PA burst from passing.
static volatile uint32_t pages[6][1024] __attribute__((used, aligned(4096)));
static volatile uint32_t load_out[10] __attribute__((used, aligned(64)));
static volatile uint32_t store_in[8] __attribute__((used, aligned(64)));
static volatile uint32_t store_prefix[4] __attribute__((used));
static volatile uint64_t repair_pte[2] __attribute__((used));
static volatile uint64_t m_frame __attribute__((used));
static unsigned char trap_stack[256] __attribute__((used, aligned(16)));
static volatile uint64_t completed;
static struct { uint64_t id, actual, expected; } failures[FAILURE_CAPACITY];
static unsigned failure_count, failure_overflow;

extern char sv39_s_entry[], sv39_load_fault[], sv39_store_fault[];
extern char sv39_s_ecall[], sv39_m_resume[];

// No C calls, no vector data instructions, no use of the interrupted stack.
// t0-t6 are the only clobbered GPRs; SP is exchanged back on every return.
static void __attribute__((naked, used, aligned(4))) sv39_m_handler(void) {
  asm volatile(
      "csrrw sp, mscratch, sp\n"
      "addi sp, sp, -64\n"
      "sd t0, 0(sp)\nsd t1, 8(sp)\nsd t2, 16(sp)\nsd t3, 24(sp)\n"
      "sd t4, 32(sp)\nsd t5, 40(sp)\nsd t6, 48(sp)\n"
      "la t0, state\n"
      "ld t1, " OFF(TRAPS) "(t0)\n"
      "li t2, 4\nbgeu t1, t2, .Lsv39_fatal\n"
      "addi t2, t1, 1\nsd t2, " OFF(TRAPS) "(t0)\n"
      "slli t1, t1, 6\nla t2, traps\nadd t2, t2, t1\n"
      "csrr t3, mcause\nsd t3, 0(t2)\n"
      "csrr t4, mepc\nsd t4, 8(t2)\n"
      "csrr t5, mtval\nsd t5, 16(t2)\n"
      "csrr t6, vstart\nsd t6, 24(t2)\n"
      "csrr t1, mstatus\nsd t1, 32(t2)\n"
      "ld t1, " OFF(PHASE) "(t0)\nsd t1, 40(t2)\n"
      "sd zero, 48(t2)\ncsrr t1, vl\nsd t1, 56(t2)\n"
      "ld t1, 32(t2)\nli t6, " STR(TRAP_STATUS_MASK) "\nand t1, t1, t6\n"
      "li t6, 0x800\nbne t1, t6, .Lsv39_fatal\n"
      "li t1, 9\nbeq t3, t1, .Lsv39_ecall\n"
      "ld t1, 24(t2)\nli t6, 4\nbne t1, t6, .Lsv39_fatal\n"
      "ld t1, 56(t2)\nli t6, 8\nbne t1, t6, .Lsv39_fatal\n"
      "li t1, 13\nbeq t3, t1, .Lsv39_load\n"
      "li t1, 15\nbne t3, t1, .Lsv39_fatal\n"
      "la t1, sv39_store_fault\nbne t4, t1, .Lsv39_fatal\n"
      "li t1, 0x40003000\nbne t5, t1, .Lsv39_fatal\n"
      "ld t1, " OFF(PHASE) "(t0)\nli t6, 3\nbne t1, t6, .Lsv39_fatal\n"
      "ld t1, " OFF(STORE_FIXED) "(t0)\nbnez t1, .Lsv39_fatal\n"
      // The trap's CSR reads drain Ara; fence orders scalar observations.
      "fence rw, rw\nla t3, pages\nli t4, 16368\nadd t3, t3, t4\n"
      "la t4, store_prefix\n"
      "lwu t1, 0(t3)\nsw t1, 0(t4)\nlwu t1, 4(t3)\nsw t1, 4(t4)\n"
      "lwu t1, 8(t3)\nsw t1, 8(t4)\nlwu t1, 12(t3)\nsw t1, 12(t4)\n"
      "la t3, leaf_pt\naddi t3, t3, 24\n"
      "la t4, repair_pte\nld t4, 8(t4)\n"
      "addi t5, t0, " OFF(STORE_FIXED) "\nj .Lsv39_repair\n"
      ".Lsv39_load:\n"
      "la t1, sv39_load_fault\nbne t4, t1, .Lsv39_fatal\n"
      "li t1, 0x40001000\nbne t5, t1, .Lsv39_fatal\n"
      "ld t1, " OFF(PHASE) "(t0)\nli t6, 2\nbne t1, t6, .Lsv39_fatal\n"
      "ld t1, " OFF(LOAD_FIXED) "(t0)\nbnez t1, .Lsv39_fatal\n"
      "la t3, leaf_pt\naddi t3, t3, 8\n"
      "la t4, repair_pte\nld t4, 0(t4)\n"
      "addi t5, t0, " OFF(LOAD_FIXED) "\n"
      ".Lsv39_repair:\n"
      "ld t1, 0(t3)\nsd t1, 48(t2)\nbnez t1, .Lsv39_fatal\n"
      "li t1, 1\nsd t1, 0(t5)\nsd t4, 0(t3)\n"
      "fence rw, rw\nsfence.vma zero, zero\n"
      // Leave mepc and vstart untouched: retry exactly the faulting instruction.
      "j .Lsv39_trap_return\n"
      ".Lsv39_ecall:\n"
      "la t1, sv39_s_ecall\nbne t4, t1, .Lsv39_fatal\n"
      "ld t1, " OFF(PHASE) "(t0)\nli t6, 4\nbne t1, t6, .Lsv39_fatal\n"
      "ld t1, " OFF(S_DONE) "(t0)\nli t6, 1\nbne t1, t6, .Lsv39_fatal\n"
      "j .Lsv39_to_m\n"
      ".Lsv39_fatal:\n"
      "li t1, 1\nsd t1, " OFF(FATAL) "(t0)\n"
      ".Lsv39_to_m:\n"
      "csrr t1, mstatus\n"
      "li t2, " STR(MSTATUS_MPIE | MSTATUS_MIE | MSTATUS_MPRV | MSTATUS_MPV) "\n"
      "not t2, t2\nand t1, t1, t2\n"
      "li t2, " STR(MSTATUS_MPP) "\nor t1, t1, t2\ncsrw mstatus, t1\n"
      "la t1, sv39_m_resume\ncsrw mepc, t1\n"
      ".Lsv39_trap_return:\n"
      "ld t0, 0(sp)\nld t1, 8(sp)\nld t2, 16(sp)\nld t3, 24(sp)\n"
      "ld t4, 32(sp)\nld t5, 40(sp)\nld t6, 48(sp)\n"
      "addi sp, sp, 64\ncsrrw sp, mscratch, sp\nmret\n");
}

// ABI boundary: S code below uses only t0-t6/v8, never s0-s11/gp/tp/ra/SP.
// Recover the M frame explicitly, including on an unexpected S exception.
static void __attribute__((naked, noinline, used))
enter_s(uint64_t s_status, uint64_t satp_value) {
  asm volatile(
      "addi sp, sp, -16\nsd ra, 0(sp)\ncsrr t0, mtvec\nsd t0, 8(sp)\n"
      "la t0, m_frame\nsd sp, 0(t0)\n"
      "la t0, trap_stack\naddi t0, t0, 256\ncsrw mscratch, t0\n"
      "la t0, sv39_m_handler\ncsrw mtvec, t0\n"
      "csrw mstatus, a0\ncsrw satp, a1\n"
      "fence rw, rw\nsfence.vma zero, zero\n"
      "la t0, sv39_s_entry\ncsrw mepc, t0\nmret\n"
      ".globl sv39_m_resume\nsv39_m_resume:\n"
      "la t0, m_frame\nld sp, 0(t0)\n"
      "la t0, state\ncsrr t1, mstatus\nsd t1, " OFF(RETURN_STATUS) "(t0)\n"
      "ld t0, 8(sp)\ncsrw mtvec, t0\nld ra, 0(sp)\naddi sp, sp, 16\nret\n");
}

static void __attribute__((naked, used)) s_body(void) {
  asm volatile(
      ".globl sv39_s_entry\nsv39_s_entry:\n"
      "la t0, state\nli t1, 1\nsd t1, " OFF(PHASE) "(t0)\n"
      "csrr t1, satp\nsd t1, " OFF(S_SATP) "(t0)\n"
      "li t2, 0x40000000\nlwu t1, 32(t2)\nsd t1, " OFF(SCALAR_LOAD) "(t0)\n"
      "li t1, 0x2468ace0\nsw t1, 36(t2)\nfence rw, rw\n"
      "lwu t1, 36(t2)\nsd t1, " OFF(SCALAR_RELOAD) "(t0)\n"
      "vsetivli t1, 8, e32, m1, tu, mu\nsd t1, " OFF(S_VL) "(t0)\n"
      "csrr t1, vtype\nsd t1, " OFF(S_VTYPE) "(t0)\n"
      "addi t3, t2, 64\nvle32.v v8, (t3)\n"
      "addi t3, t2, 128\nvse32.v v8, (t3)\n"
      "csrr t1, vstart\nfence rw, rw\nsd t1, " OFF(CONTROL_VSTART) "(t0)\n"
      "li t1, 2\nsd t1, " OFF(PHASE) "(t0)\nli t3, 0x40000ff0\n"
      ".balign 4\n.globl sv39_load_fault\nsv39_load_fault: vle32.v v8, (t3)\n"
      "csrr t1, vstart\nsd t1, " OFF(LOAD_VSTART) "(t0)\n"
      "la t3, load_out\naddi t3, t3, 4\nvse32.v v8, (t3)\n"
      "csrr zero, vl\nfence rw, rw\n"
      "la t3, store_in\nvle32.v v8, (t3)\ncsrr zero, vl\n"
      "li t1, 3\nsd t1, " OFF(PHASE) "(t0)\nli t3, 0x40002ff0\n"
      ".balign 4\n.globl sv39_store_fault\nsv39_store_fault: vse32.v v8, (t3)\n"
      "csrr t1, vstart\nfence rw, rw\nsd t1, " OFF(STORE_VSTART) "(t0)\n"
      "li t1, 4\nsd t1, " OFF(PHASE) "(t0)\n"
      "li t1, 1\nsd t1, " OFF(S_DONE) "(t0)\nfence rw, rw\n"
      ".balign 4\n.globl sv39_s_ecall\nsv39_s_ecall: ecall\n"
      "unimp\n");
}

static uint64_t pte(const volatile void *page, uint64_t flags) {
  return ((uint64_t)page >> 12 << 10) | flags;
}

static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    if (failure_count < FAILURE_CAPACITY) {
      failures[failure_count].id = id;
      failures[failure_count].actual = actual;
      failures[failure_count].expected = expected;
      ++failure_count;
    } else {
      ++failure_overflow;
    }
    ++num_failed;
  }
}

static int ram_object(const volatile void *p, uint64_t size, uint64_t align) {
  uint64_t a = (uint64_t)p;
  return a >= RAM_BASE && a < RAM_END && size <= RAM_END - a && !(a & (align - 1));
}

// Exact integer oracles, not values read from the DUT or copied from its output.
static uint32_t load_word(unsigned i) { return UINT32_C(0x11223040) + i * 0x101; }
static uint32_t store_word(unsigned i) { return UINT32_C(0x55667080) + i * 0x103; }
static uint32_t control_word(unsigned i) { return UINT32_C(0x31415000) + i * 0x107; }

static void summarize(uint64_t satp_value) {
  check(20, state[FATAL], 0);
  check(21, state[TRAPS], 3);
  check(22, state[LOAD_FIXED], 1);
  check(23, state[STORE_FIXED], 1);
  check(24, state[S_DONE], 1);
  check(25, state[PHASE], 4);
  check(26, state[S_SATP], satp_value);
  check(27, state[SCALAR_LOAD], UINT32_C(0x13579bdf));
  check(28, state[SCALAR_RELOAD], UINT32_C(0x2468ace0));
  check(29, state[S_VL], 8);
  check(30, state[S_VTYPE], 0x10);
  check(31, state[LOAD_VSTART], 0);
  check(32, state[STORE_VSTART], 0);
  check(33, state[CONTROL_VSTART], 0);
  // MRET resets MPP to U; a CSR read here is nevertheless privileged M code.
  check(34, state[RETURN_STATUS] & (MSTATUS_MPP | MSTATUS_MIE | MSTATUS_MPRV | MSTATUS_MPV), 0);

  for (unsigned i = 0; i < 3; ++i) {
    check(50 + 8 * i, traps[i][0], i == 0 ? 13 : i == 1 ? 15 : 9);
    check(51 + 8 * i, traps[i][1], (uint64_t)(i == 0 ? sv39_load_fault : i == 1 ? sv39_store_fault : sv39_s_ecall));
    check(52 + 8 * i, traps[i][2], i == 0 ? VA_BASE + 4096 : i == 1 ? VA_BASE + 12288 : 0);
    check(53 + 8 * i, traps[i][3], i < 2 ? 4 : 0);
    check(54 + 8 * i, traps[i][4] & TRAP_STATUS_MASK, 0x800);
    check(55 + 8 * i, traps[i][5], i + 2);
    check(56 + 8 * i, traps[i][6], 0);
    check(57 + 8 * i, traps[i][7], 8);
  }
  for (unsigned i = 0; i < 8; ++i) {
    check(100 + i, pages[0][32 + i], control_word(i));
    check(110 + i, load_out[1 + i], load_word(i));
    check(120 + i, i < 4 ? pages[3][1020 + i] : pages[5][i - 4], store_word(i));
    check(130 + i, i < 4 ? pages[0][1020 + i] : pages[2][i - 4], load_word(i));
  }
  for (unsigned i = 0; i < 4; ++i)
    check(140 + i, store_prefix[i], store_word(i));
  check(150, pages[0][8], UINT32_C(0x13579bdf));
  check(151, pages[0][9], UINT32_C(0x2468ace0));
  check(160, load_out[0], GUARD);
  check(161, load_out[9], GUARD);
  check(162, pages[0][15], GUARD);
  check(163, pages[0][24], GUARD);
  check(164, pages[0][31], GUARD);
  check(165, pages[0][40], GUARD);
  check(166, pages[0][1019], GUARD);
  check(167, pages[2][4], GUARD);
  check(168, pages[3][1019], GUARD);
  check(169, pages[5][4], GUARD);
  unsigned gap1_bad = 0, gap4_bad = 0;
  for (unsigned i = 0; i < 1024; ++i) {
    gap1_bad += pages[1][i] != GUARD;
    gap4_bad += pages[4][i] != GUARD;
  }
  check(170, gap1_bad, 0);
  check(171, gap4_bad, 0);
  check(180, root_pt[1], pte(mid_pt, PTE_V));
  check(181, root_pt[2], (RAM_BASE >> 12 << 10) | LEAF | PTE_X);
  check(182, mid_pt[0], pte(leaf_pt, PTE_V));
  check(183, leaf_pt[0], pte(pages[0], LEAF));
  check(184, leaf_pt[1], pte(pages[2], LEAF));
  check(185, leaf_pt[2], pte(pages[3], LEAF));
  check(186, leaf_pt[3], pte(pages[5], LEAF));
}

// crt0 supplies a valid stack and VS=Initial in M before its U-mode main.
void rvtest_init(void) {
  uint64_t status, mie, mtvec, mepc, mcause, mtval, satp, medeleg, mideleg, mscratch;
  uint64_t vl, vtype, vstart, vcsr, actual, sp;
  INIT_CHECK();
  completed = 0;
  failure_count = failure_overflow = 0;
  asm volatile("csrrci %0, mstatus, 8" : "=r"(status) : : "memory");
  READ_CSR(mie, mie);
  WRITE_CSR(mie, 0); // MIE alone does not mask machine interrupts while in S.
  READ_CSR(mtvec, mtvec);
  READ_CSR(mepc, mepc);
  READ_CSR(mcause, mcause);
  READ_CSR(mtval, mtval);
  READ_CSR(satp, satp);
  READ_CSR(medeleg, medeleg);
  READ_CSR(mideleg, mideleg);
  READ_CSR(mscratch, mscratch);
  READ_CSR(vl, vl);
  READ_CSR(vtype, vtype);
  READ_CSR(vstart, vstart);
  READ_CSR(vcsr, vcsr);
  WRITE_CSR(vstart, 0);
  WRITE_CSR(medeleg, 0);
  WRITE_CSR(mideleg, 0);
  for (unsigned i = 0; i < STATE_SLOTS; ++i) state[i] = 0;
  state[LOAD_VSTART] = state[STORE_VSTART] = state[CONTROL_VSTART] = UINT64_MAX;
  state[RETURN_STATUS] = UINT64_MAX;
  for (unsigned i = 0; i < 4; ++i) {
    store_prefix[i] = GUARD;
    for (unsigned j = 0; j < 8; ++j) traps[i][j] = UINT64_MAX;
  }
  for (unsigned i = 0; i < 512; ++i) root_pt[i] = mid_pt[i] = leaf_pt[i] = 0;
  for (unsigned p = 0; p < 6; ++p)
    for (unsigned i = 0; i < 1024; ++i) pages[p][i] = GUARD;
  for (unsigned i = 0; i < 10; ++i) load_out[i] = GUARD;
  for (unsigned i = 0; i < 8; ++i) {
    pages[0][16 + i] = control_word(i);
    store_in[i] = store_word(i);
    if (i < 4) pages[0][1020 + i] = load_word(i);
    else pages[2][i - 4] = load_word(i);
  }
  pages[0][8] = UINT32_C(0x13579bdf);
  root_pt[1] = pte(mid_pt, PTE_V);
  root_pt[2] = (RAM_BASE >> 12 << 10) | LEAF | PTE_X;
  mid_pt[0] = pte(leaf_pt, PTE_V);
  leaf_pt[0] = pte(pages[0], LEAF);
  leaf_pt[2] = pte(pages[3], LEAF);
  repair_pte[0] = pte(pages[2], LEAF);
  repair_pte[1] = pte(pages[5], LEAF);
  const uint64_t satp_value = SV39 | ((uint64_t)root_pt >> 12);
  asm volatile("mv %0, sp" : "=r"(sp));
  check(1, satp, 0);
  check(2, sp >= RAM_BASE + 4096 && sp <= RAM_END && !(sp & 15), 1);
  check(3, ram_object(root_pt, sizeof(root_pt), 4096) &&
           ram_object(mid_pt, sizeof(mid_pt), 4096) &&
           ram_object(leaf_pt, sizeof(leaf_pt), 4096) &&
           ram_object(pages, sizeof(pages), 4096) &&
           ram_object(load_out, sizeof(load_out), 64) &&
           ram_object(store_in, sizeof(store_in), 64) &&
           ram_object(trap_stack, sizeof(trap_stack), 16), 1);
  READ_CSR(medeleg, actual); check(4, actual, 0);
  READ_CSR(mideleg, actual); check(5, actual, 0);
  READ_CSR(mie, actual); check(6, actual, 0);
  const uint64_t s_status = (status & ~(uint64_t)(MSTATUS_MPP | MSTATUS_MPIE |
      MSTATUS_MIE | MSTATUS_SIE | MSTATUS_MPRV | MSTATUS_MPV | MSTATUS_TVM |
      MSTATUS_SUM | MSTATUS_MXR | MSTATUS_VS)) | 0x800 | VS_INITIAL;
  asm volatile("fence rw, rw" : : : "memory");
  if (!num_failed) enter_s(s_status, satp_value);

  // Even fatal S traps reach this scalar-only M cleanup and all comparisons.
  WRITE_CSR(satp, satp);
  asm volatile("sfence.vma zero, zero\nfence rw, rw" : : : "memory");
  summarize(satp_value);
  asm volatile("vsetvl zero, %0, %1" : : "r"(vl), "r"(vtype) : "memory");
  WRITE_CSR(vcsr, vcsr);
  WRITE_CSR(vstart, vstart);
  WRITE_CSR(mtvec, mtvec);
  WRITE_CSR(mepc, mepc);
  WRITE_CSR(mcause, mcause);
  WRITE_CSR(mtval, mtval);
  WRITE_CSR(mscratch, mscratch);
  WRITE_CSR(medeleg, medeleg);
  WRITE_CSR(mideleg, mideleg);
  WRITE_CSR(mie, mie);
#define RESTORED(ID, CSR, SAVED) do { READ_CSR(CSR, actual); check(ID, actual, SAVED); } while (0)
  RESTORED(200, satp, satp);
  RESTORED(201, mtvec, mtvec);
  RESTORED(202, mepc, mepc);
  RESTORED(203, mcause, mcause);
  RESTORED(204, mtval, mtval);
  RESTORED(205, medeleg, medeleg);
  RESTORED(206, mideleg, mideleg);
  RESTORED(207, mscratch, mscratch);
  RESTORED(208, mie, mie);
  RESTORED(209, vl, vl);
  RESTORED(210, vtype, vtype);
  RESTORED(211, vstart, vstart);
  RESTORED(212, vcsr, vcsr);
  WRITE_CSR(mstatus, status & ~MSTATUS_MIE);
  RESTORED(213, mstatus, status & ~MSTATUS_MIE);
#undef RESTORED
  completed = DONE;
  WRITE_CSR(mstatus, status);
}

int main(void) {
  if (completed != DONE) {
    printf("ERROR: sv39_state_prereq M hook incomplete\n");
    return 1;
  }
  for (unsigned i = 0; i < failure_count; ++i)
    printf("Failure #%lu: got %016lx expected %016lx\n",
           failures[i].id, failures[i].actual, failures[i].expected);
  if (state[FATAL])
    for (unsigned i = 0; i < state[TRAPS] && i < 4; ++i)
      printf("Trap %u: cause=%lx epc=%lx tval=%lx vstart=%lu phase=%lu\n",
             i, traps[i][0], traps[i][1], traps[i][2], traps[i][3], traps[i][5]);
  if (failure_overflow)
    printf("ERROR: failure overflow=%u\n", failure_overflow);
  printf("sv39_state_prereq: %d checks\n", test_case);
  if (test_case != PLANNED_CHECKS || failure_overflow || num_failed || state[FATAL]) {
    printf("FAIL: sv39_state_prereq failures=%d planned=%d\n", num_failed, PLANNED_CHECKS);
    return num_failed ? num_failed : 1;
  }
  // Avoid EXIT_CHECK's extra vector CSR access after restoring the saved CSRs.
  printf("PASSED: sv39_state_prereq\n");
  return 0;
}
