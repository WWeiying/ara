#include <fcntl.h>
#include <unistd.h>

static void write_all(int fd, const char *text)
{
    const char *cursor = text;
    size_t remaining = 0;

    while (text[remaining] != '\0')
        ++remaining;
    while (remaining != 0) {
        ssize_t written = write(fd, cursor, remaining);
        if (written <= 0)
            return;
        cursor += written;
        remaining -= (size_t)written;
    }
}

int main(void)
{
    int console = open("/dev/console", O_WRONLY | O_NOCTTY);
    if (console < 0)
        console = STDOUT_FILENO;

    write_all(console, "Ara DSA VCU118 Linux init reached\n");
    write_all(console, "Linux console, DDR and RVV handoff are alive\n");
    if (console != STDOUT_FILENO)
        close(console);

    for (;;)
        pause();
}
