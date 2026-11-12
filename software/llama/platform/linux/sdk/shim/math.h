#ifndef ARA_KERNEL_MATH_H
#define ARA_KERNEL_MATH_H
float ara_resident_expf(float value);
#define expf ara_resident_expf
#define __builtin_expf ara_resident_expf
float tanhf(float value);
float fmaf(float left, float right, float addend);
#endif
