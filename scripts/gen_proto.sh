#!/usr/bin/env bash
# Regenerate Python gRPC stubs from the shared proto submodule into src/grpc_gen/.
# `proto/` is now the techscout-protos submodule (holds all 3 contracts); this
# service only needs recommend.proto, so we name it explicitly instead of proto/*.proto.
# Usage: bash scripts/gen_proto.sh   (needs `uv sync --group dev` for grpcio-tools)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=src/grpc_gen
mkdir -p "$OUT"
uv run python -m grpc_tools.protoc -I proto \
  --python_out="$OUT" --grpc_python_out="$OUT" proto/recommend.proto
# Make generated grpc imports package-relative.
python3 - "$OUT" <<'PY'
import sys, re, glob, os
d = sys.argv[1]
for f in glob.glob(os.path.join(d, "*_pb2_grpc.py")):
    s = open(f).read()
    s = re.sub(r'^import (\w+_pb2) as', r'from . import \1 as', s, flags=re.M)
    open(f, "w").write(s)
open(os.path.join(d, "__init__.py"), "w").write('"""Generated gRPC stubs (do not edit; run scripts/gen_proto.sh)."""\n')
PY
echo "Regenerated stubs in $OUT"
