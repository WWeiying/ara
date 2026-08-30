CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -Iinclude

BUILD := build
SOURCES := src/akv_runtime.c src/akv_native_riscv.c
OBJECTS := $(SOURCES:%.c=$(BUILD)/%.o)

.PHONY: all check clean

all: $(BUILD)/libakv_runtime.a

check: $(BUILD)/akv_runtime_test
	$(BUILD)/akv_runtime_test

$(BUILD)/libakv_runtime.a: $(OBJECTS)
	$(AR) rcs $@ $^

$(BUILD)/akv_runtime_test: tests/akv_runtime_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf $(BUILD)
