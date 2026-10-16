#include <fcntl.h>
#include <unistd.h>

int main(void) {
  static const char message[] = "ARA_LIBC_INIT_STDOUT\n";
  static const char kmsg[] = "<0>ARA_LIBC_INIT_KMSG\n";
  int fd = open("/dev/kmsg", O_WRONLY);
  if (fd >= 0) write(fd, kmsg, sizeof(kmsg) - 1);
  write(STDOUT_FILENO, message, sizeof(message) - 1);
  for (;;) { }
}
