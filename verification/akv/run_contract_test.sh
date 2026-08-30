#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT

python3 "${repo_root}/scripts/gen_akv_abi.py" --check
cc -std=c11 -Wall -Wextra -Werror \
  "${repo_root}/verification/akv/akv_contract_test.c" \
  -o "${tmp}/akv_contract_test"
"${tmp}/akv_contract_test"

c++ -std=c++17 -Wall -Wextra -Werror -x c++ -c \
  "${repo_root}/apps/common/akv_abi.h" -o "${tmp}/akv_abi.o"
