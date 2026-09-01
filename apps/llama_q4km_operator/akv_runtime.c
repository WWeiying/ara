#include "../common/runtime.h"

#define AKV_PROFILE_PHASE(phase) HW_CNT_PHASE(phase)
#include "../../software/akv/src/akv_runtime.c"
#include "../../software/akv/src/akv_native_riscv.c"
#include "../../software/akv/src/akv_v2_native_riscv.c"
#undef AKV_PROFILE_PHASE
