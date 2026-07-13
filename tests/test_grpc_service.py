"""RecommendService gRPC round-trip with the pipelines stubbed (no DB/LLM)."""
from concurrent import futures

import grpc

from src.grpc_gen.techscout.recommend.v1 import recommend_pb2, recommend_pb2_grpc


class _FakePipeline:
    def run(self, query, top_k=None, product_ids=None):
        return {
            "summary": f"reco:{query}",
            "recommendations": [{"id": "1", "name": "iPhone 15", "score": 0.9}],
            "analysis": {"conclusion": f"cmp:{query}"},
        }


def test_recommend_and_compare_grpc(monkeypatch):
    monkeypatch.setattr("api.deps.get_cached_recommend_pipeline", lambda: _FakePipeline())
    monkeypatch.setattr("api.deps.get_cached_compare_pipeline", lambda: _FakePipeline())
    from src.grpc_server.service import RecommendServicer

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    recommend_pb2_grpc.add_RecommendServiceServicer_to_server(RecommendServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        stub = recommend_pb2_grpc.RecommendServiceStub(grpc.insecure_channel(f"127.0.0.1:{port}"))
        r = stub.Recommend(recommend_pb2.RecommendRequest(query="laptop", top_k=3))
        assert r.answer == "reco:laptop"
        assert r.sources[0].title == "iPhone 15"
        c = stub.Compare(recommend_pb2.CompareRequest(query="a vs b"))
        assert c.answer == "cmp:a vs b"
    finally:
        server.stop(0)
