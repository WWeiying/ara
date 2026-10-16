#define SYS_write 64
#define SYS_mount 40
#define SYS_openat 56
#define SYS_exit 93
#define SYS_kill 129
#define SYS_ptrace 117
#define SYS_getpid 172
#define SYS_clone 220
#define SYS_execve 221
#define SYS_wait4 260

#define PTRACE_TRACEME 0
#define PTRACE_GETREGSET 0x4204
#define PTRACE_SYSCALL 24
#define PTRACE_SETOPTIONS 0x4200
#define PTRACE_O_TRACESYSGOOD 1
#define NT_PRSTATUS 1
#define SIGCHLD 17
#define SIGSTOP 19

struct iovec {
  void *base;
  unsigned long length;
};

static long output_fd = 1;

static long call4(long number, long arg0, long arg1, long arg2, long arg3) {
  register long a0 __asm__("a0") = arg0;
  register long a1 __asm__("a1") = arg1;
  register long a2 __asm__("a2") = arg2;
  register long a3 __asm__("a3") = arg3;
  register long a7 __asm__("a7") = number;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a7) : "memory");
  return a0;
}

static long call5(long number, long arg0, long arg1, long arg2, long arg3,
                  long arg4) {
  register long a0 __asm__("a0") = arg0;
  register long a1 __asm__("a1") = arg1;
  register long a2 __asm__("a2") = arg2;
  register long a3 __asm__("a3") = arg3;
  register long a4 __asm__("a4") = arg4;
  register long a7 __asm__("a7") = number;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a7) : "memory");
  return a0;
}

static unsigned long length(const char *s) {
  unsigned long n = 0;
  while (s[n]) ++n;
  return n;
}

static void print(const char *s) {
  call4(SYS_write, output_fd, (long)s, length(s), 0);
}

static void print_hex(unsigned long value) {
  char out[19] = "0x0000000000000000";
  const char digits[] = "0123456789abcdef";
  for (int i = 17; i >= 2; --i) {
    out[i] = digits[value & 15];
    value >>= 4;
  }
  call4(SYS_write, output_fd, (long)out, 18, 0);
}

static void print_stop(unsigned long number, unsigned long result, int entering) {
  static const char digits[] = "0123456789abcdef";
  char line[] = "T? 0000 00000000\n";
  line[1] = entering ? '>' : '<';
  for (int i = 6; i >= 3; --i) {
    line[i] = digits[number & 15];
    number >>= 4;
  }
  for (int i = 15; i >= 8; --i) {
    line[i] = digits[result & 15];
    result >>= 4;
  }
  call4(SYS_write, output_fd, (long)line, sizeof(line) - 1, 0);
}

__attribute__((noreturn)) void _start(void) {
  static const char devtmpfs[] = "devtmpfs";
  static const char dev[] = "/dev";
  static const char kmsg[] = "/dev/kmsg";
  static char *const argv[] = {"/bin/busybox", 0};
  static char *const envp[] = {"PATH=/bin:/sbin", 0};
  static const char path[] = "/bin/busybox";
  call5(SYS_mount, (long)devtmpfs, (long)dev, (long)devtmpfs, 0, 0);
  long fd = call4(SYS_openat, -100, (long)kmsg, 1, 0);
  if (fd >= 0) output_fd = fd;
  print("ARA_TRACE_OUTPUT_READY\n");
  long pid = call4(SYS_clone, SIGCHLD, 0, 0, 0);
  if (pid == 0) {
    call4(SYS_ptrace, PTRACE_TRACEME, 0, 0, 0);
    long self = call4(SYS_getpid, 0, 0, 0, 0);
    call4(SYS_kill, self, SIGSTOP, 0, 0);
    call4(SYS_execve, (long)path, (long)argv, (long)envp, 0);
    call4(SYS_exit, 127, 0, 0, 0);
  }
  if (pid < 0) {
    print("ARA_TRACE_CLONE_FAILED\n");
    for (;;) { }
  }
  print("ARA_TRACE_PARENT_READY\n");
  int status = 0;
  call4(SYS_wait4, pid, (long)&status, 0, 0);
  call4(SYS_ptrace, PTRACE_SETOPTIONS, pid, 0, PTRACE_O_TRACESYSGOOD);
  int entering = 1;
  for (int i = 0; i < 96; ++i) {
    long ret = call4(SYS_ptrace, PTRACE_SYSCALL, pid, 0, 0);
    if (ret < 0) {
      print("ARA_TRACE_RESUME_FAILED\n");
      break;
    }
    ret = call4(SYS_wait4, pid, (long)&status, 0, 0);
    if (ret < 0 || (status & 0xff) != 0x7f) {
      print("ARA_TRACE_CHILD_EXIT status=");
      print_hex((unsigned int)status);
      print("\n");
      break;
    }
    unsigned long regs[32];
    struct iovec io = {regs, sizeof(regs)};
    ret = call4(SYS_ptrace, PTRACE_GETREGSET, pid, NT_PRSTATUS, (long)&io);
    if (ret < 0) {
      print("ARA_TRACE_REGS_FAILED\n");
      break;
    }
    if (((status >> 8) & 0xff) == (5 | 0x80)) {
      print_stop(regs[17], regs[10], entering);
      entering = !entering;
    } else {
      print("ARA_TRACE_OTHER_STOP\n");
    }
  }
  print("ARA_TRACE_END\n");
  for (;;) { }
}
