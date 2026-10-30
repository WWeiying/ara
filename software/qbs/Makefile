CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -Iinclude

BUILD := build
SOURCES := src/qbs_runtime.c src/qbs_native_riscv.c src/qbs_format.c
OBJECTS := $(SOURCES:%.c=$(BUILD)/%.o)

.PHONY: all check example traffic-audit clean

all: $(BUILD)/libqbs_runtime.a

check: $(BUILD)/qbs_runtime_test $(BUILD)/qbs_runtime_adapter_example $(BUILD)/qbs_format_test $(BUILD)/qbs_segmented_test $(BUILD)/qbs_planner_traffic
	$(BUILD)/qbs_runtime_test
	$(BUILD)/qbs_runtime_adapter_example
	$(BUILD)/qbs_format_test
	$(BUILD)/qbs_segmented_test
	$(BUILD)/qbs_planner_traffic > /dev/null

example: $(BUILD)/qbs_runtime_adapter_example

traffic-audit: $(BUILD)/qbs_planner_traffic

$(BUILD)/qbs_planner_traffic: examples/planner_traffic.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/libqbs_runtime.a: $(OBJECTS)
	$(AR) rcs $@ $^

$(BUILD)/qbs_runtime_test: tests/qbs_runtime_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/qbs_format_test: tests/qbs_format_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/qbs_segmented_test: tests/qbs_segmented_test.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/qbs_runtime_adapter_example: examples/runtime_adapter.c $(OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

clean:
	rm -rf $(BUILD)

-include $(OBJECTS:.o=.d)
