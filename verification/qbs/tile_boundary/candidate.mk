include Makefile

# Same test composition and source inventory; replace only the integer engine.
RTL_ENGINE_SOURCES := $(subst $(ROOT)/hardware/src/vlsu/qbs/qbs_profile_engine_int.sv,$(ROOT)/verification/qbs/tile_boundary/retire_candidate.sv,$(RTL_ENGINE_SOURCES))
