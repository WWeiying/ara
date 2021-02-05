// Copyright 2020 ETH Zurich and University of Bologna.
//
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Author: Matheus Cavalcante, ETH Zurich
//         Samuel Riedel, ETH Zurich

#include <stdint.h>
#include <string.h>

#include "printf.h"
#include "runtime.h"
#include "kernel/matmul.h"

// Define Matrix dimensions:
// C = AB with A=[MxN], B=[NxP], C=[MxP]
#define M 64
#define N 64
#define P 64
// Specify how the matrices A and B should be initialized
// The entries will follow this format:
// a(i,j) = A_a*i + A_b*j + A_c
// b(i,j) = B_a*i + B_b*j + B_c
// The result will be the following matrix
// c(i,j) = (A_a*B_b*i*j + A_a*B_c*i + A_c*B_b*j + A_c*B_c) * N
//        + (A_a*B_a*i + A_b*B_b*j + A_b*B_c + B_a*A_c) * (N*(N-1))/2
//        + (A_b*B_a) * (N*(N-1)*(2*N-1))/6
// Note: To keep the code simpler, we use indices that go from 0 to N-1 instead
// of 1 to N as the mathematicians do. Hence, for A, i=[0,M-1] j=[0,M-1]
#define A_a 1
#define A_b 1
#define A_c -32
#define B_a 2
#define B_b 1
#define B_c 16

int64_t a[M * N] __attribute__((aligned(4*NR_LANES), section(".l2")));
int64_t b[N * P] __attribute__((aligned(4*NR_LANES), section(".l2")));
int64_t c[M * P] __attribute__((aligned(4*NR_LANES), section(".l2")));

// Initialize the matrices
void init_matrix(int64_t *matrix, uint64_t num_rows, uint64_t num_columns,
                 int64_t a, int64_t b, int64_t c) {
  for (uint64_t i = 0; i < num_rows; ++i) {
    for (uint64_t j = 0; j < num_columns; ++j) {
      matrix[i * num_columns + j] = a * (int64_t)i + b * (int64_t)j + c;
    }
  }
}

// Verify the matrices
int verify_matrix(int64_t *matrix, uint64_t num_rows, uint64_t num_columns,
                  int64_t aa, int64_t ab, int64_t ac, int64_t ba, int64_t bb,
                  int64_t bc) {
  for (int64_t i = 0; i < (int64_t)num_rows; ++i) {
    for (int64_t j = 0; j < (int64_t)num_columns; ++j) {
      int64_t lin = (aa * bb * i * j + aa * bc * i + ac * bb * j + ac * bc) * N;
      int64_t qua =
          ((aa * ba * i + ab * bb * j + ab * bc + ba * ac) * (N * (N - 1))) / 2;
      int64_t cub = ((ab * ba) * (N * (N - 1) * (2 * N - 1))) / 6;
      int64_t golden = lin + qua + cub;
      if (matrix[i * (int64_t)num_columns + j] != golden) {
        return (i + j) == 0 ? -1 : i * (int64_t)num_columns + j;
      }
      matrix[i * (int64_t)num_columns + j] = 0;
    }
  }
  return 0;
}

void print_matrix(int64_t const *matrix, uint64_t num_rows, uint64_t num_columns) {
  printf("0x%8X\n", (uint64_t)matrix);
  for (uint64_t i = 0; i < num_rows; ++i) {
    for (uint64_t j = 0; j < num_columns; ++j) {
      printf("%5d ", matrix[i * num_columns + j]);
    }
    printf("\n");
  }
}


int main() {
  printf("Initializing matrices...\n");

  // Initialize Matrices
  init_matrix(a, M, N, A_a, A_b, A_c);
  init_matrix(b, N, P, B_a, B_b, B_c);

  // Matrices are initialized --> Start calculating
  printf("Calculating matmul...\n");
  start_timer();
  matmul(c, a, b, M, N, P);
  stop_timer();
  asm volatile ("fence");

  // Runtime
  printf("The execution took %d cycles.\n", get_timer());

  // Verify the result
  printf("Verifying result...\n");
  int error = verify_matrix(c, M, P, A_a, A_b, A_c, B_a, B_b, B_c);
  if (error != 0) {
    printf("Error code %d\n", error);
    printf("c[%d]=%d\n", error, c[error]);
  }
  return error;
}