"""
Keyword Search - In-memory BM25 (Okapi) index over product documents.

Pure-Python on purpose: the corpus (product chunks) is small, so the index
builds in milliseconds and avoids adding a dependency for ~60 lines of math.
"""
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lowercase and split into unicode word tokens (Vietnamese diacritics kept)."""
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """BM25 (Okapi) index with standard parameters k1=1.5, b=0.75.

    idf uses the standard smoothed form ``log(1 + (N - df + 0.5) / (df + 0.5))``
    so scores are always non-negative.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict] = []
        self._term_freqs: list[Counter] = []
        self._doc_lens: list[int] = []
        self._avg_doc_len: float = 0.0
        self._idf: dict[str, float] = {}

    @property
    def size(self) -> int:
        return len(self.ids)

    def build(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
        """(Re)build the index from a full corpus snapshot."""
        self.ids = list(ids)
        self.documents = list(documents)
        self.metadatas = list(metadatas)
        self._term_freqs = []
        self._doc_lens = []

        doc_freq: Counter = Counter()
        for doc in self.documents:
            tokens = tokenize(doc)
            freqs = Counter(tokens)
            self._term_freqs.append(freqs)
            self._doc_lens.append(len(tokens))
            doc_freq.update(freqs.keys())

        n_docs = len(self.documents)
        self._avg_doc_len = (sum(self._doc_lens) / n_docs) if n_docs else 0.0
        self._idf = {
            term: math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Score every document against the query; return top_k hits.

        Returns dicts shaped like retriever candidates:
        ``{"id", "document", "metadata", "bm25_score"}``, best first.
        Documents with zero overlap are omitted.
        """
        query_tokens = tokenize(query)
        if not query_tokens or not self.ids:
            return []

        scores: list[float] = [0.0] * len(self.ids)
        for term in query_tokens:
            idf = self._idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self._term_freqs):
                tf = freqs.get(term, 0)
                if tf == 0:
                    continue
                norm = 1 - self.b + self.b * (self._doc_lens[i] / self._avg_doc_len)
                scores[i] += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * norm)

        ranked = sorted(
            (i for i, s in enumerate(scores) if s > 0),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]
        return [
            {
                "id": self.ids[i],
                "document": self.documents[i],
                "metadata": self.metadatas[i],
                "bm25_score": round(scores[i], 4),
            }
            for i in ranked
        ]
