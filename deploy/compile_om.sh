#!/usr/bin/env bash
# Compile a static YOLO ONNX locally on the AIpro; no network or sudo needed.
set -eo pipefail
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: bash compile_om.sh input.onnx output_prefix [input_size]" >&2
  exit 2
fi
onnx_path=$1
output_prefix=$2
input_size=${3:-640}
if ! [[ "$input_size" =~ ^[0-9]+$ ]] || [ "$input_size" -lt 160 ] || [ "$input_size" -gt 1920 ]; then
  echo "input_size must be an integer from 160 to 1920" >&2
  exit 2
fi
if [ -e "$output_prefix.om" ]; then
  echo "Refusing to overwrite an existing OM: $output_prefix.om" >&2
  exit 2
fi
source /usr/local/Ascend/ascend-toolkit/set_env.sh
# CANN 7.0's compiler uses the board's original Python 3.9/numpy 1.22
# environment. Keep the API's separate Python 3.10 venv untouched.
if [ -x /usr/local/miniconda3/bin/python ]; then
  export PATH="/usr/local/miniconda3/bin:$PATH"
  export LD_LIBRARY_PATH="/usr/local/miniconda3/lib:${LD_LIBRARY_PATH:-}"
fi
exec atc --framework=5 --model="$onnx_path" --output="$output_prefix" \
  --input_format=NCHW --input_shape="images:1,3,$input_size,$input_size" \
  --soc_version=Ascend310B4 --precision_mode=allow_fp32_to_fp16
