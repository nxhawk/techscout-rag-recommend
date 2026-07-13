#!/usr/bin/env bash
# Regenerate Python gRPC stubs from the shared proto submodule into src/grpc_gen/.
# `proto/` is the techscout-protos submodule; contracts now live at
# proto/techscout/<svc>/v1/<svc>.proto. This service only needs recommend.proto,
# so we name it explicitly instead of a recursive proto/**/*.proto glob.
# Usage: bash scripts/gen_proto.sh   (needs `uv sync --group dev` for grpcio-tools)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=src/grpc_gen
mkdir -p "$OUT"
uv run python -m grpc_tools.protoc -I proto \
  --python_out="$OUT" --grpc_python_out="$OUT" proto/techscout/recommend/v1/recommend.proto
# Make generated grpc imports package-relative, and stamp __init__.py in every
# generated package directory (techscout/, techscout/recommend/, .../v1/).
python3 - "$OUT" <<'PY'
import sys, re, glob, os
d = sys.argv[1]
for f in glob.glob(os.path.join(d, "**", "*_pb2_grpc.py"), recursive=True):
    s = open(f).read()
    # Newer grpcio-tools emits `from techscout.recommend.v1 import recommend_pb2 as ...`;
    # older ones emit a bare `import recommend_pb2 as ...`. Both need to become
    # a same-directory relative import so grpc_gen doesn't have to be on sys.path.
    s = re.sub(r'^from [\w.]+ import (\w+_pb2) as', r'from . import \1 as', s, flags=re.M)
    s = re.sub(r'^import (\w+_pb2) as', r'from . import \1 as', s, flags=re.M)
    open(f, "w").write(s)
for root, _dirs, _files in os.walk(d):
    init = os.path.join(root, "__init__.py")
    if not os.path.exists(init):
        open(init, "w").write('"""Generated gRPC stubs (do not edit; run scripts/gen_proto.sh)."""\n')
PY
echo "Regenerated stubs in $OUT"
