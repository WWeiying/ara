#define SYS_mount 40
#define SYS_openat 56
#define SYS_close 57
#define SYS_read 63
#define SYS_write 64
#define SYS_exit 93
#define SYS_clone 220
#define SYS_execve 221

#define SIGCHLD 17

static long log_fd = 1;

static long call5(long number, long p0, long p1, long p2, long p3, long p4) {
  register long a0 __asm__("a0") = p0;
  register long a1 __asm__("a1") = p1;
  register long a2 __asm__("a2") = p2;
  register long a3 __asm__("a3") = p3;
  register long a4 __asm__("a4") = p4;
  register long a7 __asm__("a7") = number;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a7) : "memory");
  return a0;
}

static void log_text(const char *text) {
  long n = 0;
  while (text[n]) ++n;
  call5(SYS_write, log_fd, (long)text, n, 0, 0);
}

static char *pid_path(char *out, long pid, const char *name) {
  const char *prefix = "/proc/";
  int n = 0;
  while (prefix[n]) {
    out[n] = prefix[n];
    ++n;
  }
  char digits[20];
  int count = 0;
  do {
    digits[count++] = '0' + pid % 10;
    pid /= 10;
  } while (pid && count < 20);
  while (count) out[n++] = digits[--count];
  out[n++] = '/';
  for (int i = 0; name[i]; ++i) out[n++] = name[i];
  out[n] = 0;
  return out;
}

static void log_file(const char *label, const char *path) {
  long fd = call5(SYS_openat, -100, (long)path, 0, 0, 0);
  log_text(label);
  if (fd < 0) {
    log_text("open failed\n");
    return;
  }
  char contents[256];
  long n = call5(SYS_read, fd, (long)contents, sizeof(contents) - 1, 0, 0);
  if (n > 0) {
    call5(SYS_write, log_fd, (long)contents, n, 0, 0);
    log_text("\n");
  } else {
    log_text("read failed\n");
  }
  call5(SYS_close, fd, 0, 0, 0, 0);
}

__attribute__((noreturn)) void _start(void) {
  static const char proc[] = "proc";
  static const char proc_dir[] = "/proc";
  static const char devtmpfs[] = "devtmpfs";
  static const char dev_dir[] = "/dev";
  static const char kmsg[] = "/dev/kmsg";
  static const char program[] = "/bin/busybox";
  static char *const argv[] = {"/bin/busybox", 0};
  static char *const envp[] = {"PATH=/bin:/sbin", 0};

  call5(SYS_mount, (long)proc, (long)proc_dir, (long)proc, 0, 0);
  call5(SYS_mount, (long)devtmpfs, (long)dev_dir, (long)devtmpfs, 0, 0);
  long fd = call5(SYS_openat, -100, (long)kmsg, 1, 0, 0);
  if (fd >= 0) log_fd = fd;
  log_text("ARA_MONITOR_READY\n");
  long pid = call5(SYS_clone, SIGCHLD, 0, 0, 0, 0);
  if (pid == 0) {
    call5(SYS_execve, (long)program, (long)argv, (long)envp, 0, 0);
    call5(SYS_exit, 127, 0, 0, 0, 0);
  }
  if (pid < 0) log_text("ARA_MONITOR_CLONE_FAILED\n");
  log_text("ARA_MONITOR_CLONE_RETURNED\n");
  char path[64];
  log_text("ARA_MONITOR_FIRST_SAMPLE\n");
  log_file("syscall: ", pid_path(path, pid, "syscall"));
  log_file("wchan: ", pid_path(path, pid, "wchan"));
  for (int i = 0; i < 10; ++i) {
    for (volatile unsigned long spin = 0; spin < 1000; ++spin) { }
    log_text("ARA_MONITOR_SAMPLE\n");
    log_file("syscall: ", pid_path(path, pid, "syscall"));
    log_file("wchan: ", pid_path(path, pid, "wchan"));
  }
  log_text("ARA_MONITOR_END\n");
  for (;;) { }
}
