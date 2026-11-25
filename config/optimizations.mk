# Candidate build profile only, not functional or physical acceptance.
# Defaults only: explicit command-line settings take precedence.
optimization_profile ?= generic
ifneq ($(words $(optimization_profile)),1)
$(error optimization_profile must be one name)
endif
ifeq ($(filter $(optimization_profile),generic candidate_all),)
$(error optimization_profile must be generic or candidate_all)
endif
ifeq ($(optimization_profile),candidate_all)
qbs ?= 1
akv_v2 ?= 1
optimization_default := 1
else
optimization_default := 0
endif

shared_simd_mul ?= $(optimization_default)
shared_fma ?= $(optimization_default)
akv_resident ?= $(optimization_default)
qbs_lane_mul ?= $(optimization_default)
acc_req_register ?= 0

$(foreach option,shared_simd_mul shared_fma akv_resident qbs_lane_mul acc_req_register,$(if $(and $(filter 1,$(words $($(option)))),$(filter 0 1,$($(option)))),,$(error $(option) must be 0 or 1)))
ifeq ($(acc_req_register),1)
ifneq ($(shell grep -sc '^`ifdef ARA_REGISTER_ACCELERATOR_REQUEST$$' $(ARA_DIR)/hardware/deps/cva6/core/acc_dispatcher.sv),1)
$(error acc_req_register=1 requires hardware/patches/cva6/acc-request-register.patch)
endif
endif
# Resident and cooperative QBS lane routing have fixed RTL geometry gates.
# Independent lane-local shared arithmetic has no such integration restriction.
ifneq ($(filter 1,$(akv_resident) $(qbs_lane_mul))$(filter candidate_all,$(optimization_profile)),)
ifneq ($(nr_lanes)/$(vlen),4/1024)
$(error candidate optimizations require nr_lanes=4 vlen=1024)
endif
endif

# Undefined macros mean OFF: these RTL selectors use ifdef, not numeric tests.
optimization_bender_defs = $(if $(filter 1,$(shared_simd_mul)),--define ARA_SHARED_SIMD_MUL=1) \
    $(if $(filter 1,$(shared_fma)),--define ARA_SHARED_FMA=1) \
    $(if $(filter 1,$(akv_resident)),--define ARA_AKV_RESIDENT_PV_ENABLE=1 --define ARA_AKV_RESIDENT_QK_ENABLE=1) \
    $(if $(filter 1,$(qbs_lane_mul)),--define ARA_QBS_LANE_MUL_ENABLE=1) \
    $(if $(filter 1,$(acc_req_register)),--define ARA_REGISTER_ACCELERATOR_REQUEST=1)
