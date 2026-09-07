#include <akv/akv_decode.h>
#include <akv/akv_features.h>

int main(void) {
  akv_device_t device;
  akv_attention_features_t features = {0};
  return akv_device_init_reference(&device) != AKV_STATUS_OK ||
         akv_attention_features_validate(&features, 1, 65) != AKV_STATUS_OK;
}
