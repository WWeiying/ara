// Actual-SoC trap payload/delegation prerequisite, not a timer/PLIC test.
#include "vector_macros.h"

#if !defined(__clang__) || defined(vec) || defined(ARA_FPGA) || defined(ARA_LINUX) || defined(__SPIKE__)
#error "Use the non-ZCC scalar-C bare-metal SoC build"
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
#define OFF(x) STR(8 * x)
#define PHASE 0
#define COUNT 1
#define TARGET 2
#define CAUSE 3
#define EPC 4
#define TVAL 5
#define STATUS 6
#define PENDING 7
#define RESUME 8
#define FRAME 9
#define FATAL 10
#define EXIT_M_COUNT 11
#define EXIT_M_CAUSE 12
#define EXIT_M_TVAL 13
#define EXIT_S_COUNT 14
#define EXIT_S_CAUSE 15
#define EXIT_S_TVAL 16
#define CONTINUED 17
#define NSLOTS 18
#define CASES 24
#define PLANNED_CHECKS (CASES * 18 + 16)
#define SSIP UINT64_C(2)
#define IRQ_SSIP (UINT64_C(1) << 63 | SSIP >> 1)
#define ILLEGAL_CSR UINT32_C(0xfff022f3)
#define DONE UINT64_C(0x74726170707265)
#define SAVE "addi sp, sp, -64\nsd t0, 0(sp)\nsd t1, 8(sp)\nsd t2, 16(sp)\nsd t3, 24(sp)\nsd t4, 32(sp)\nsd t5, 40(sp)\nsd t6, 48(sp)\n"
#define RESTORE "ld t0, 0(sp)\nld t1, 8(sp)\nld t2, 16(sp)\nld t3, 24(sp)\nld t4, 32(sp)\nld t5, 40(sp)\nld t6, 48(sp)\naddi sp, sp, 64\n"
#define READ(csr, dst) asm volatile("csrr %0, " #csr : "=r"(dst) : : "memory")
#define WRITE(csr, src) asm volatile("csrw " #csr ", %0" : : "r"((uint64_t)(src)) : "memory")

static volatile uint64_t state[NSLOTS] __attribute__((used));
static uint64_t snapshots[CASES][NSLOTS];
static unsigned char m_stack[256] __attribute__((used, aligned(16)));
static unsigned char s_stack[256] __attribute__((used, aligned(16)));
static volatile uint64_t completed;
static unsigned cases_run, failures_used;
static struct { uint64_t id, got, expected; } failures[PLANNED_CHECKS];
extern char trap_m_resume[], trap_after[], trap_irq_after[];
extern char trap_ecall[], trap_ebreak[], trap_cebreak[], trap_illegal[], trap_irq[];

static void __attribute__((naked, used, aligned(64))) m_handler(void) {
  asm volatile(
      "csrrw sp, mscratch, sp\n" SAVE
      "la t0, state\nld t1, " OFF(PHASE) "(t0)\nli t2, 1\nbne t1, t2, .Ltrap_m_exit\n"
      "ld t1, " OFF(COUNT) "(t0)\naddi t1, t1, 1\nsd t1, " OFF(COUNT) "(t0)\n"
      "li t1, 3\nsd t1, " OFF(TARGET) "(t0)\n"
      "csrr t1, mcause\nsd t1, " OFF(CAUSE) "(t0)\n"
      "csrr t2, mepc\nsd t2, " OFF(EPC) "(t0)\n"
      "csrr t2, mtval\nsd t2, " OFF(TVAL) "(t0)\n"
      "csrr t2, mstatus\nsd t2, " OFF(STATUS) "(t0)\n"
      "csrr t2, mip\nsd t2, " OFF(PENDING) "(t0)\ncsrci mip, 2\n"
      "li t2, 2\nsd t2, " OFF(PHASE) "(t0)\n"
      "csrr t2, mip\nandi t2, t2, 2\nbeqz t2, .Ltrap_m_cleared\n"
      "li t2, 2\nsd t2, " OFF(FATAL) "(t0)\nj .Ltrap_m_exit\n"
      ".Ltrap_m_cleared:\n"
      // Interrupts resume the interrupted PC; synchronous tests have known labels.
      "bltz t1, .Ltrap_m_return\nld t2, " OFF(RESUME) "(t0)\ncsrw mepc, t2\n"
      "j .Ltrap_m_return\n"
      ".Ltrap_m_exit:\n"
      "ld t1, " OFF(EXIT_M_COUNT) "(t0)\naddi t1, t1, 1\nsd t1, " OFF(EXIT_M_COUNT) "(t0)\n"
      "csrr t1, mcause\nsd t1, " OFF(EXIT_M_CAUSE) "(t0)\n"
      "csrr t1, mtval\nsd t1, " OFF(EXIT_M_TVAL) "(t0)\n"
      "csrw mie, zero\ncsrci mip, 2\ncsrr t1, mstatus\n"
      "li t2, " STR(MSTATUS_MPIE | MSTATUS_MIE | MSTATUS_MPRV | MSTATUS_MPV) "\nnot t2, t2\nand t1, t1, t2\n"
      "li t2, " STR(MSTATUS_MPP) "\nor t1, t1, t2\ncsrw mstatus, t1\n"
      "la t1, trap_m_resume\ncsrw mepc, t1\n"
      ".Ltrap_m_return:\n" RESTORE "csrrw sp, mscratch, sp\nmret\n");
}

static void __attribute__((naked, used, aligned(64))) s_handler(void) {
  asm volatile(
      "csrrw sp, sscratch, sp\n" SAVE
      "la t0, state\nld t1, " OFF(PHASE) "(t0)\nli t2, 1\nbne t1, t2, .Ltrap_s_exit\n"
      "ld t1, " OFF(COUNT) "(t0)\naddi t1, t1, 1\nsd t1, " OFF(COUNT) "(t0)\n"
      "li t1, 1\nsd t1, " OFF(TARGET) "(t0)\n"
      "csrr t1, scause\nsd t1, " OFF(CAUSE) "(t0)\n"
      "csrr t2, sepc\nsd t2, " OFF(EPC) "(t0)\n"
      "csrr t2, stval\nsd t2, " OFF(TVAL) "(t0)\n"
      "csrr t2, sstatus\nsd t2, " OFF(STATUS) "(t0)\n"
      "csrr t2, sip\nsd t2, " OFF(PENDING) "(t0)\ncsrci sip, 2\n"
      "li t2, 2\nsd t2, " OFF(PHASE) "(t0)\n"
      "csrr t2, sip\nandi t2, t2, 2\nbeqz t2, .Ltrap_s_cleared\n"
      "csrci sie, 2\nli t2, 2\nsd t2, " OFF(FATAL) "(t0)\nj .Ltrap_s_exit\n"
      ".Ltrap_s_cleared:\n"
      "bltz t1, .Ltrap_s_return\nld t2, " OFF(RESUME) "(t0)\ncsrw sepc, t2\n"
      ".Ltrap_s_return:\n" RESTORE "csrrw sp, sscratch, sp\nsret\n"
      ".Ltrap_s_exit:\n"
      "ld t1, " OFF(EXIT_S_COUNT) "(t0)\naddi t1, t1, 1\nsd t1, " OFF(EXIT_S_COUNT) "(t0)\n"
      "csrr t1, scause\nsd t1, " OFF(EXIT_S_CAUSE) "(t0)\n"
      "csrr t1, stval\nsd t1, " OFF(EXIT_S_TVAL) "(t0)\n"
      "csrci sip, 2\nli t1, 3\nsd t1, " OFF(PHASE) "(t0)\n"
      // Only an exiting U ECALL is delegated here. S ECALL always goes to M.
      RESTORE "csrrw sp, sscratch, sp\necall\nunimp\n");
}

static void __attribute__((naked, noinline, used))
enter_mode(uint64_t entry, uint64_t status) {
  asm volatile(
      "addi sp, sp, -16\nsd ra, 0(sp)\nla t0, state\nsd sp, " OFF(FRAME) "(t0)\n"
      "csrw mepc, a0\ncsrw mstatus, a1\nmret\n"
      ".globl trap_m_resume\ntrap_m_resume:\n"
      "la t0, state\nld sp, " OFF(FRAME) "(t0)\nld ra, 0(sp)\naddi sp, sp, 16\nret\n");
}

static void __attribute__((naked, used)) bodies(void) {
  asm volatile(
      ".option push\n.option norvc\n"
      ".balign 4\n.globl trap_ecall\ntrap_ecall: .word 0x00000073\nj trap_after\n"
      ".balign 4\n.globl trap_ebreak\ntrap_ebreak: .word 0x00100073\nj trap_after\n"
      ".balign 4\n.globl trap_cebreak\ntrap_cebreak: .hword 0x9002\nj trap_after\n"
      ".balign 4\n.globl trap_illegal\ntrap_illegal: .word 0xfff022f3\nj trap_after\n"
      ".balign 4\n.globl trap_irq\ntrap_irq:\n"
      "li t0, 512\nla t1, state\nli t3, 2\n"
      ".Ltrap_wait: ld t2, " OFF(PHASE) "(t1)\nbeq t2, t3, trap_irq_after\n"
      "addi t0, t0, -1\nbnez t0, .Ltrap_wait\n"
      // A missing interrupt terminates with COUNT=0 instead of hanging forever.
      "li t2, 1\nsd t2, " OFF(FATAL) "(t1)\nli t2, 2\nsd t2, " OFF(PHASE) "(t1)\n"
      ".globl trap_irq_after\ntrap_irq_after:\n"
      ".globl trap_after\ntrap_after:\n"
      "la t0, state\nli t1, 1\nsd t1, " OFF(CONTINUED) "(t0)\necall\nunimp\n.option pop\n");
}

static void check(unsigned id, uint64_t got, uint64_t expected) {
  ++test_case;
  if (got != expected) {
    if (failures_used < PLANNED_CHECKS)
      failures[failures_used++] = (__typeof__(failures[0])){id, got, expected};
    ++num_failed;
  }
}

void rvtest_init(void) {
  uint64_t saved[16], x;
  READ(mstatus, saved[0]);
  asm volatile("csrci mstatus, 8" : : : "memory");
  READ(mie, saved[1]); WRITE(mie, 0);
  READ(medeleg, saved[2]); READ(mideleg, saved[3]);
  READ(mtvec, saved[4]); READ(stvec, saved[5]);
  READ(mscratch, saved[6]); READ(sscratch, saved[7]);
  READ(mepc, saved[8]); READ(sepc, saved[9]);
  READ(mcause, saved[10]); READ(scause, saved[11]);
  READ(mtval, saved[12]); READ(stval, saved[13]);
  READ(satp, saved[14]); READ(mip, saved[15]);
  WRITE(satp, 0); asm volatile("sfence.vma" : : : "memory");
  WRITE(mtvec, m_handler); WRITE(stvec, s_handler);
  WRITE(mscratch, m_stack + sizeof(m_stack)); WRITE(sscratch, s_stack + sizeof(s_stack));
  char *entries[] = {trap_ecall, trap_ebreak, trap_cebreak, trap_illegal, trap_irq};
  const unsigned privileges[] = {3, 1, 0, 1, 0};
  const uint64_t clean = saved[0] & ~(MSTATUS_MPP | MSTATUS_MIE | MSTATUS_MPIE |
      MSTATUS_SIE | MSTATUS_SPIE | MSTATUS_SPP | MSTATUS_MPRV | MSTATUS_MPV |
      MSTATUS_TVM | MSTATUS_TSR | MSTATUS_TW);
  for (unsigned op = 0; op < 5; ++op) {
    for (unsigned route = 0; route < 5; ++route) {
      if (op == 0 && route == 3) continue;
      const unsigned priv = privileges[route], delegated = route >= 3;
      const unsigned irq = op == 4, bridge = op == 0 && route == 4;
      const uint64_t cause = irq ? IRQ_SSIP : op == 0 ? priv + 8 : op == 3 ? 2 : 3;
      for (unsigned i = 0; i < NSLOTS; ++i) state[i] = 0;
      state[PHASE] = 1; state[RESUME] = (uint64_t)trap_after;
      WRITE(medeleg, delegated && !irq ? UINT64_C(1) << cause : 0);
      WRITE(mideleg, delegated && irq ? SSIP : 0);
      WRITE(mip, irq ? SSIP : 0); WRITE(mie, irq ? SSIP : 0);
      const uint64_t status = clean | (uint64_t)priv << 11 |
          (irq ? (priv == 3 ? MSTATUS_MPIE : MSTATUS_SIE) : 0);
      enter_mode((uint64_t)entries[op], status);
      for (unsigned i = 0; i < NSLOTS; ++i) snapshots[cases_run][i] = state[i];
      unsigned id = 1000 + cases_run++ * 100;
      check(id++, state[COUNT], 1);
      check(id++, state[TARGET], delegated ? 1 : 3);
      check(id++, state[CAUSE], cause);
      check(id++, irq ? state[EPC] >= (uint64_t)trap_irq && state[EPC] < (uint64_t)trap_irq_after && !(state[EPC] & 3)
                      : state[EPC] == (uint64_t)entries[op], 1);
      // Breakpoints may report zero or the faulting PC, not instruction bits.
      check(id++, op == 1 || op == 2 ? state[TVAL] == 0 || state[TVAL] == state[EPC]
                                    : state[TVAL] == (op == 3 ? ILLEGAL_CSR : 0), 1);
      check(id++, delegated ? (state[STATUS] & MSTATUS_SPP) >> 8
                            : (state[STATUS] & MSTATUS_MPP) >> 11, priv);
      check(id++, state[STATUS] & (delegated ? MSTATUS_SIE : MSTATUS_MIE), 0);
      check(id++, state[EXIT_M_COUNT], 1);
      check(id++, state[EXIT_M_CAUSE], bridge ? 9 : priv + 8);
      check(id++, state[EXIT_M_TVAL], 0);
      check(id++, state[EXIT_S_COUNT], bridge);
      check(id++, state[EXIT_S_CAUSE], bridge ? 8 : 0);
      check(id++, state[EXIT_S_TVAL], 0);
      check(id++, state[PHASE], bridge ? 3 : 2);
      READ(mip, x); check(id++, x & SSIP, 0);
      check(id++, state[CONTINUED], 1);
      check(id++, state[FATAL], 0);
      check(id++, state[PENDING] & SSIP, irq ? SSIP : 0);
    }
  }
  WRITE(mie, 0); WRITE(mip, saved[15]);
  WRITE(medeleg, saved[2]); WRITE(mideleg, saved[3]);
  WRITE(mtvec, saved[4]); WRITE(stvec, saved[5]);
  WRITE(mscratch, saved[6]); WRITE(sscratch, saved[7]);
  WRITE(mepc, saved[8]); WRITE(sepc, saved[9]);
  WRITE(mcause, saved[10]); WRITE(scause, saved[11]);
  WRITE(mtval, saved[12]); WRITE(stval, saved[13]);
  WRITE(satp, saved[14]); asm volatile("sfence.vma" : : : "memory");
  WRITE(mstatus, saved[0] & ~MSTATUS_MIE); WRITE(mie, saved[1]);
#define RESTORED(n, csr) READ(csr, x); check(4000 + n, x, saved[n])
  READ(mstatus, x); check(4000, x, saved[0] & ~MSTATUS_MIE);
  RESTORED(1, mie); RESTORED(2, medeleg); RESTORED(3, mideleg);
  RESTORED(4, mtvec); RESTORED(5, stvec); RESTORED(6, mscratch); RESTORED(7, sscratch);
  RESTORED(8, mepc); RESTORED(9, sepc); RESTORED(10, mcause); RESTORED(11, scause);
  RESTORED(12, mtval); RESTORED(13, stval); RESTORED(14, satp);
  READ(mip, x); check(4015, x & (SSIP | (UINT64_C(1) << 5) | (UINT64_C(1) << 9)),
                     saved[15] & (SSIP | (UINT64_C(1) << 5) | (UINT64_C(1) << 9)));
#undef RESTORED
  completed = DONE; WRITE(mstatus, saved[0]);
}

int main(void) {
  for (unsigned i = 0; i < cases_run; ++i)
    printf("trap_case=%u target=%lu cause=%016lx epc=%016lx tval=%016lx status=%016lx pending=%016lx count=%lu fatal=%lu\n",
           i, snapshots[i][TARGET], snapshots[i][CAUSE], snapshots[i][EPC],
           snapshots[i][TVAL], snapshots[i][STATUS], snapshots[i][PENDING],
           snapshots[i][COUNT], snapshots[i][FATAL]);
  for (unsigned i = 0; i < failures_used; ++i)
    printf("Failure #%lu: got %016lx expected %016lx\n",
           failures[i].id, failures[i].got, failures[i].expected);
  printf("trap_state_prereq: %u cases %d checks\n", cases_run, test_case);
  if (completed != DONE || cases_run != CASES || test_case != PLANNED_CHECKS || num_failed) {
    printf("FAIL: trap_state_prereq failures=%d\n", num_failed);
    return num_failed ? num_failed : 1;
  }
  printf("PASSED: trap_state_prereq\n");
  return 0;
}
