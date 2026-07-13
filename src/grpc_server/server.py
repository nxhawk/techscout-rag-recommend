"""Build and run the RecommendService gRPC server."""
import logging
import os
from concurrent import futures

import grpc

from src.grpc_gen.techscout.recommend.v1 import recommend_pb2_grpc
from src.grpc_server.service import RecommendServicer

logger = logging.getLogger(__name__)


def build_server(port: int) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    recommend_pb2_grpc.add_RecommendServiceServicer_to_server(RecommendServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    return server


def serve_in_thread(port: int | None = None) -> grpc.Server:
    """Start the gRPC server on its own threads and return it (non-blocking)."""
    port = port or int(os.getenv("GRPC_PORT", "50052"))
    server = build_server(port)
    server.start()
    logger.info("gRPC RecommendService listening on :%d", port)
    return server


def serve() -> None:
    """Blocking entry point (standalone gRPC-only process)."""
    logging.basicConfig(level=logging.INFO)
    server = serve_in_thread()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
