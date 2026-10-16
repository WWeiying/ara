#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

#define DEFAULT_TTY "/dev/ttyS0"
#define MAX_CHUNK (64u * 1024u)
#define ACK 0x06
#define NAK 0x15

static int read_full(int fd, void *buffer, size_t size) {
    unsigned char *cursor = buffer;
    while (size != 0) {
        ssize_t count = read(fd, cursor, size);
        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (count == 0) {
            return -1;
        }
        cursor += count;
        size -= (size_t) count;
    }
    return 0;
}

static int write_full(int fd, const void *buffer, size_t size) {
    const unsigned char *cursor = buffer;
    while (size != 0) {
        ssize_t count = write(fd, cursor, size);
        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (count == 0) {
            return -1;
        }
        cursor += count;
        size -= (size_t) count;
    }
    return 0;
}

static uint32_t crc32_update(uint32_t crc, const unsigned char *data, size_t size) {
    while (size-- != 0) {
        crc ^= *data++;
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (0xedb88320u & (uint32_t) -(int32_t) (crc & 1u));
        }
    }
    return crc;
}

static int parse_size(const char *text, uint64_t *value) {
    char *end = NULL;
    errno = 0;
    unsigned long long parsed = strtoull(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0' || parsed == 0) {
        return -1;
    }
    *value = (uint64_t) parsed;
    return 0;
}

static void report_error(int tty, const struct termios *saved, const char *message) {
    (void) write_full(tty, "MODEL_RX_ERROR\n", 15);
    tcsetattr(tty, TCSADRAIN, saved);
    fprintf(stderr, "model-rx: %s\n", message);
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "/model/qwen2.5-1.5b-instruct-q4_k_m.gguf";
    const char *size_text = argc > 2 ? argv[2] : NULL;
    uint64_t remaining;
    if (size_text == NULL || parse_size(size_text, &remaining) != 0) {
        fprintf(stderr, "usage: model-rx OUTPUT SIZE\n");
        return 2;
    }
    const uint64_t total_size = remaining;

    int tty = open(DEFAULT_TTY, O_RDWR | O_NOCTTY);
    if (tty < 0) {
        perror("model-rx: open tty");
        return 1;
    }

    struct termios saved;
    if (tcgetattr(tty, &saved) != 0) {
        perror("model-rx: tcgetattr");
        close(tty);
        return 1;
    }
    struct termios raw = saved;
    cfmakeraw(&raw);
    raw.c_cflag |= CLOCAL | CREAD;
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;
    if (tcsetattr(tty, TCSANOW, &raw) != 0) {
        perror("model-rx: tcsetattr");
        close(tty);
        return 1;
    }
    tcflush(tty, TCIOFLUSH);

    int output = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (output < 0) {
        report_error(tty, &saved, "cannot open output");
        close(tty);
        return 1;
    }

    static unsigned char chunk[MAX_CHUNK];
    if (write_full(tty, "MODEL_RX_READY\n", 15) != 0) {
        close(output);
        tcsetattr(tty, TCSADRAIN, &saved);
        close(tty);
        return 1;
    }

    for (;;) {
        uint32_t length;
        if (read_full(tty, &length, sizeof(length)) != 0) {
            report_error(tty, &saved, "short frame length");
            close(output);
            close(tty);
            return 1;
        }
        if (length == 0) {
            if (remaining != 0) {
                report_error(tty, &saved, "end marker before expected size");
                close(output);
                close(tty);
                return 1;
            }
            break;
        }
        if (length > MAX_CHUNK || (uint64_t) length > remaining) {
            unsigned char response = NAK;
            (void) write_full(tty, &response, 1);
            continue;
        }

        if (read_full(tty, chunk, length) != 0) {
            report_error(tty, &saved, "short frame payload");
            close(output);
            close(tty);
            return 1;
        }
        uint32_t expected_crc;
        if (read_full(tty, &expected_crc, sizeof(expected_crc)) != 0) {
            report_error(tty, &saved, "short frame checksum");
            close(output);
            close(tty);
            return 1;
        }

        uint32_t actual_crc = ~crc32_update(~0u, chunk, length);
        unsigned char response = actual_crc == expected_crc ? ACK : NAK;
        if (actual_crc == expected_crc && write_full(output, chunk, length) != 0) {
            response = NAK;
        }
        if (write_full(tty, &response, 1) != 0) {
            close(output);
            tcsetattr(tty, TCSADRAIN, &saved);
            close(tty);
            return 1;
        }
        if (response == ACK) {
            remaining -= length;
        }
    }

    if (fsync(output) != 0 || close(output) != 0) {
        report_error(tty, &saved, "output sync failed");
        close(tty);
        return 1;
    }
    tcsetattr(tty, TCSADRAIN, &saved);
    char done[96];
    int done_size = snprintf(done, sizeof(done), "MODEL_RX_DONE size=%llu\n",
                             (unsigned long long) total_size);
    (void) write_full(tty, done, (size_t) done_size);
    close(tty);
    return 0;
}
