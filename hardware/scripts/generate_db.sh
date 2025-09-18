#!/bin/bash

LIB_DIR=$1
DB_DIR=$2

mkdir -p $DB_DIR

for lib_file in $LIB_DIR/*.lib; do
  base_name=$(basename "$lib_file" .lib)
  tech_name=$(echo $base_name | cut -d'_' -f1,3)
  
  echo "read_lib $lib_file" >> convert_script.tcl
  echo "write_lib $tech_name -output $DB_DIR/$base_name.db" >> convert_script.tcl
done
