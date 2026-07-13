# Chuyển gRPC server sang version proto mới

rag-recommend **implement** (phục vụ) `RecommendService` từ
`proto/techscout/recommend/v1/recommend.proto` trong submodule
`techscout-protos` (xem
[docs của techscout-protos](https://nxhawk.github.io/techscout-protos/) để
biết cách quản lý version ở phía nguồn). Trang này nói về các bước dựng thêm
`v2` của `RecommendService` song song `v1` đang chạy, không làm hỏng gateway
(hay bất kỳ ai khác) vẫn đang gọi `v1`.

## Khác với gateway, script này trỏ đích danh 1 file

`scripts/gen_proto.sh` ở đây gọi `protoc` trực tiếp vào
`proto/techscout/recommend/v1/recommend.proto` (không phải glob đệ quy), vì
service này chỉ cần mỗi `recommend.proto`. Nghĩa là **bạn phải tự thêm path
mới vào script** — nó sẽ không tự nhận ra `v2`.

## Các bước

1. **Kéo version mới về.**

   ```bash
   git submodule update --remote --recursive proto
   ```

   Kiểm tra `proto/techscout/recommend/v2/recommend.proto` đã tồn tại.

2. **Thêm bước sinh code cho `v2`.** Có thể sửa `scripts/gen_proto.sh` để sinh
   thêm từ path mới, hoặc thêm một lệnh gọi thứ hai:

   ```bash
   uv run python -m grpc_tools.protoc -I proto \
     --python_out=src/grpc_gen --grpc_python_out=src/grpc_gen \
     proto/techscout/recommend/v2/recommend.proto
   ```

   Chạy lại bước fix import + tạo `__init__.py` (đã có sẵn trong script) trên
   toàn bộ cây `src/grpc_gen` để file sinh ra của `v2` cũng được fix import
   tương đối cùng thư mục giống `v1`.

3. **Cài đặt servicer cho `v2` song song `v1`.** Giữ nguyên `RecommendServicer`
   (trong `src/grpc_server/service.py`) phục vụ `v1`, thêm class thứ hai cho
   `v2` (vd. `RecommendServicerV2`) theo đúng hình dạng request/response của
   `v2` — tái dùng logic retrieval/recommend/compare bên dưới, chỉ cần điều
   chỉnh phần (de)serialize ở lớp ngoài.

4. **Đăng ký cả hai trên cùng một server.** Trong
   `src/grpc_server/server.py`, import cả hai module `_grpc` đã sinh (đặt
   alias để tránh trùng tên) và đăng ký cả hai servicer trên cùng một
   `grpc.Server`:

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

   Cả hai version được phục vụ trên cùng một port — gRPC dispatch theo tên
   service đầy đủ (`techscout.recommend.v1.RecommendService` khác
   `techscout.recommend.v2.RecommendService`), nên không xung đột.

5. **Cập nhật test.** `tests/test_grpc_service.py` dựng server và gọi
   in-process — thêm test tương ứng cho stub `v2`, giữ nguyên test `v1` vẫn
   pass.

6. **Kiểm tra lại.**

   ```bash
   uv run pytest tests/test_grpc_service.py -v
   ```

## Checklist

- [ ] Đã bump submodule, có `proto/techscout/recommend/v2/recommend.proto`
- [ ] Đã sửa `scripts/gen_proto.sh` để sinh thêm stub `v2` (script này
      **không** tự nhận version mới)
- [ ] Đã có `src/grpc_gen/techscout/recommend/v2/`, không đụng output của `v1`
- [ ] Đã thêm class servicer cho `v2` trong `src/grpc_server/service.py`
- [ ] Đã đăng ký cả `v1` và `v2` trên cùng `grpc.Server` trong
      `src/grpc_server/server.py`
- [ ] `tests/test_grpc_service.py` có test cho cả hai version và pass
- [ ] Đã xác nhận gateway (hay client khác) vẫn dùng `v1` bình thường trong
      lúc `v2` được rollout
- [ ] Khi mọi client đã migrate hết khỏi `v1`: gỡ servicer + đăng ký + code
      sinh ra cho `v1`, theo đúng bước dọn dẹp trong docs của
      techscout-protos
