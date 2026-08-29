CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -Iinclude

BUILD := build
SOURCES := src/qbs_runtime.c src/qbs_native_riscv.c
OBJECTS := $(SOURCES:%.c=$(BUILD)/%.o)

.PHONY: all check example clean

all: $(BUILD)/libqbs_runtime.a

check: $(BUILD)/qbs_runtime_test $(BUILD)/qbs_runtime_adapter_example
	$(BUILD)/qbs_runtime_test
	$(BUILD)/qbs_runtime_adapter_example

example: $(BUILD)/qbs_runtime_adapter_example

$(BUILD)/libqbs_runtime.a: $(OBJECTS)
	$(AR) rcs $@ $^

$(BUILD)/qbs_runtime_test: tests/qbs_runtime_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/qbs_runtime_adapter_example: examples/runtime_adapter.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf $(BUILD)
