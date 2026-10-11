# SPDX-License-Identifier: SHL-0.51
# Exact-seed integration test profile; run from hardware with both Makefiles.
# This matches full110 (both mechanisms enabled), not the default Make profile.
include config/reduction_completion_4lane.mk
reduction_rce_exact_external_seed ?= 1
# Kept separately switchable; no extra application-cycle gain in nine windows.
reduction_rce_exact_seed_receive ?= 1
