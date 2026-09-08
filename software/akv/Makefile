CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -Iinclude

BUILD := build
SOURCES := src/akv_runtime.c src/akv_native_riscv.c \
		src/akv_v2_native_riscv.c src/akv_v2_reference.c \
		src/akv_prefill_reference.c src/akv_features.c src/akv_decode.c
OBJECTS := $(SOURCES:%.c=$(BUILD)/%.o)

.PHONY: all check clean

all: $(BUILD)/libakv_runtime.a

check: $(BUILD)/akv_runtime_test $(BUILD)/akv_portability_test $(BUILD)/akv_online_test
	$(BUILD)/akv_runtime_test
	$(BUILD)/akv_portability_test
	$(BUILD)/akv_online_test

$(BUILD)/libakv_runtime.a: $(OBJECTS)
	$(AR) rcs $@ $^

$(BUILD)/akv_runtime_test: tests/akv_runtime_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -lm -o $@

$(BUILD)/akv_portability_test: tests/akv_portability_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -lm -o $@

$(BUILD)/akv_online_test: tests/akv_online_test.c src/akv_online_internal.h
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -fno-fast-math -ffp-contract=off $< -lm -o $@

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

clean:
	rm -rf $(BUILD)

-include $(OBJECTS:.o=.d)
