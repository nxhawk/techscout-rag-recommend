# Migrating the gRPC server to a new proto version

rag-recommend **implements** (serves) `RecommendService` from
`proto/techscout/recommend/v1/recommend.proto` in the `techscout-protos`
submodule (see
[techscout-protos docs](https://nxhawk.github.io/techscout-protos/en/) for how
versions are managed upstream). This page covers the steps for standing up a
`v2` of `RecommendService` alongside the existing `v1`, without breaking the
gateway (or anyone else) still calling `v1`.

## Unlike the gateway, this script targets one file explicitly

`scripts/gen_proto.sh` here calls `protoc` on
`proto/techscout/recommend/v1/recommend.proto` by name (not a recursive
glob), since this service only ever needs `recommend.proto`. That means **you
do need to add the new path to the script** — it won't pick up `v2`
automatically.

## Steps

1. **Pull in the new proto version.**

   ```bash
   git submodule update --remote --recursive proto
   ```

   Confirm `proto/techscout/recommend/v2/recommend.proto` exists.

2. **Add a `v2` codegen step.** Either extend `scripts/gen_proto.sh` to also
   generate from the new path, or add a second invocation:

   ```bash
   uv run python -m grpc_tools.protoc -I proto \
     --python_out=src/grpc_gen --grpc_python_out=src/grpc_gen \
     proto/techscout/recommend/v2/recommend.proto
   ```

   Run the existing import-fixup + `__init__.py` stamping step (already in the
   script) over the whole `src/grpc_gen` tree so `v2`'s generated files get the
   same same-directory-relative import fix as `v1`.

3. **Implement the `v2` servicer alongside `v1`.** Keep `RecommendServicer`
   (in `src/grpc_server/service.py`) serving `v1`, and add a second class for
   `v2` (e.g. `RecommendServicerV2`) built against the `v2` request/response
   shapes — reuse the same retrieval/recommendation/comparison logic
   underneath, just adapt the (de)serialization at the edges.

4. **Register both on the same server.** In `src/grpc_server/server.py`,
   import both generated `_grpc` modules (alias them to avoid name clashes)
   and register both servicers on the same `grpc.Server`:

   ```python
   from src.grpc_gen.techscout.recommend.v1 import recommend_pb2_grpc as recommend_v1_grpc
   from src.grpc_gen.techscout.recommend.v2 import recommend_pb2_grpc as recommend_v2_grpc
   from src.grpc_server.service import RecommendServicer, RecommendServicerV2

   def build_server(port: int) -> grpc.Server:
       server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
       recommend_v1_grpc.add_RecommendServiceServicer_to_server(RecommendServicer(), server)
       recommend_v2_grpc.add_RecommendServiceServicer_to_server(RecommendServicerV2(), server)
       server.add_insecure_port(f"[::]:{port}")
       return server
   ```

   Both versions are then served on the same port — gRPC dispatches by full
   service name (`techscout.recommend.v1.RecommendService` vs
   `techscout.recommend.v2.RecommendService`), so there's no collision.

5. **Update tests.** `tests/test_grpc_service.py` builds a server and calls it
   in-process — add an equivalent test against the `v2` stub, and keep the
   `v1` test passing unchanged.

6. **Verify.**

   ```bash
   uv run pytest tests/test_grpc_service.py -v
   ```

## Checklist

- [ ] Submodule bumped, `proto/techscout/recommend/v2/recommend.proto` present
- [ ] `scripts/gen_proto.sh` updated to also generate `v2` stubs (this
      script does **not** discover new versions automatically)
- [ ] `src/grpc_gen/techscout/recommend/v2/` generated, `v1` output untouched
- [ ] New `v2` servicer class added in `src/grpc_server/service.py`
- [ ] Both `v1` and `v2` registered on the same `grpc.Server` in
      `src/grpc_server/server.py`
- [ ] `tests/test_grpc_service.py` covers both versions and passes
- [ ] Gateway (or any other client) confirmed on `v1` still works unchanged
      while `v2` is rolled out
- [ ] Once every client has migrated off `v1`: remove the `v1` servicer +
      registration + generated code, following the cleanup steps in the
      techscout-protos docs
