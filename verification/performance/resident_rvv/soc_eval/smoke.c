/* One real candidate call, not ABBA and not hardware/performance acceptance. */
#define main resident_soc_eval_abba_main
#include "main.c"
#undef main

/* Accepted akv_pair_integration_vcs_20261107_01/result.json: measured.fcsr=3.
 * This expectation applies only to the inherited fixed D128/H2/T137 workload.
 */
enum { SMOKE_EXPECT_FCSR = 3 };

int main(void) {
  const uint64_t vlenb = initialize();
  drain();
  if (vlenb != 128) {
    printf("SMOKE_FAIL vlenb=%lu\n", vlenb);
    printf("SMOKE_DONE calls=0 errors=1\n");
    return 1;
  }

  selected_arm = 1;
  memset(&workspace, 0xa5, sizeof(workspace));
  memset(&query, 0xa5, sizeof(query));
  memset(&output, 0xa5, sizeof(output));
  drain();
  reset_csr();
  uint64_t initial_fcsr, initial_vcsr, initial_vstart;
  read_csr(&initial_fcsr, &initial_vcsr, &initial_vstart);
  uint64_t groups = 0;
  const uint64_t begin = cycles();
  const akv_status_t status = full_call(&groups);
  const uint64_t returned = cycles();
  drain();
  const uint64_t end = cycles();
  uint64_t fcsr, vcsr, vstart;
  read_csr(&fcsr, &vcsr, &vstart);

  const uint64_t query_hash = hash_bytes(UINT64_C(14695981039346656037),
                                         query.value, sizeof(query.value));
  const uint64_t guard_hash = guards();
  const uint64_t data_bytes = (uintptr_t)data_end - (uintptr_t)data_begin;
  const uint64_t data_hash = hash_bytes(UINT64_C(14695981039346656037),
                                        data_begin, data_bytes);
  uint64_t errors = 0;
  errors += status != AKV_STATUS_OK || groups != 1 || resident_pv_rotation_selected != 1;
  errors += initial_fcsr != 0 || initial_vcsr != 0 || initial_vstart != 0;
  errors += fcsr != SMOKE_EXPECT_FCSR || vcsr != 0 || vstart != 0;
  errors += !(begin < returned && returned < end);
  errors += query_hash != PAIR_EXPECT_QUERY_HASH ||
            memcmp(query.value, decode_query_f16, sizeof(query.value)) != 0;
  errors += guard_hash != PAIR_EXPECT_GUARD_HASH;
  errors += data_bytes != PAIR_EXPECT_DATA_BYTES || data_hash != PAIR_EXPECT_DATA_HASH;

  printf("SMOKE_META d=128 heads=2 tokens=137 tile=64 arm=1 vlenb=%lu status=%u groups=%lu begin=%lu returned=%lu end=%lu initial_fcsr=%lu initial_vcsr=%lu initial_vstart=%lu fcsr=%lu vcsr=%lu vstart=%lu\n",
         vlenb, (unsigned)status, groups, begin, returned, end,
         initial_fcsr, initial_vcsr, initial_vstart, fcsr, vcsr, vstart);
  printf("SMOKE_MEMORY query_hash=%016lx guard_hash=%016lx data_hash=%016lx data_bytes=%lu\n",
         query_hash, guard_hash, data_hash, data_bytes);
  for (unsigned i = 0; i < HEADS * DIM; ++i) {
    uint32_t actual, expected;
    memcpy(&actual, &output.value[i], sizeof(actual));
    memcpy(&expected, &native_golden[i], sizeof(expected));
    errors += actual != expected;
    printf("SMOKE_OUT index=%u bits=%08x expected=%08x\n", i, actual, expected);
  }
  printf("SMOKE_DONE calls=1 errors=%lu\n", errors);
  return errors != 0;
}
