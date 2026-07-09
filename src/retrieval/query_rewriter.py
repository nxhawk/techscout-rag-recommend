"""
Query Rewriter - Viết lại câu hỏi trước khi retrieve để tăng recall.

Bốn kỹ thuật, mỗi kỹ thuật là một điểm mở rộng độc lập:

1. ``QueryNormalizer``     - Query Normalization: chuẩn hóa, loại bỏ noise
                             (VD: "điện thoại siêu rẻ" -> "điện thoại giá thấp").
2. ``TypoCorrector`` /
   ``SynonymExpander``     - Query Expansion: sửa lỗi gõ phổ biến và thêm từ
                             đồng nghĩa để mở rộng vùng phủ ngữ nghĩa.
3. ``MultiQueryGenerator`` - Multi-query generation: sinh nhiều phiên bản
                             query để search song song (semantic branch sẽ
                             embed từng phiên bản rồi hợp nhất kết quả).
4. ``IntentAwareRewriter`` - Intent-aware rewriting: làm giàu query bằng
                             use_case/priorities đã được ``UserIntentParser``
                             phân tích trước đó.

Toàn bộ dữ liệu tra cứu (noise phrases, typo corrections, synonyms, intent
terms, stopwords) nằm trong ``src/retrieval/data/query_rewrite_rules.json``
thay vì hard-code trong class - để thêm/sửa từ vựng chỉ cần sửa JSON, không
cần đụng code hay redeploy logic.

Cách thêm một bước normalization/expansion mới:

1. Subclass ``BaseRewriteStrategy`` và implement ``apply(query) -> str``.
2. Thêm instance vào danh sách trả về bởi ``build_default_strategies()``.

Cách mở rộng dữ liệu (không cần sửa code):

- Thêm cặp ``[pattern, replacement]`` vào ``noise_replacements`` để chuẩn
  hóa thêm một cụm từ khẩu ngữ.
- Thêm entry vào ``typo_corrections`` để sửa thêm một lỗi gõ/viết tắt.
- Thêm entry vào ``synonyms`` để mở rộng thêm từ đồng nghĩa.
- Thêm phrase vào danh sách trong ``use_case_terms``/``priority_terms`` để
  làm giàu vocabulary cho intent-aware rewriting (khóa phải khớp với giá trị
  ``UserIntentParser`` sinh ra - xem ``USE_CASE_KEYWORDS``/``PRIORITY_KEYWORDS``
  trong ``src/pipeline/recommend/user_intent_parser.py``).
- Thêm từ vào ``stopwords`` để loại thêm hư từ khi sinh biến thể "từ khóa
  cốt lõi" (``MultiQueryGenerator``).

Chain chạy tuần tự, output của strategy trước là input của strategy sau
(giống ``GuardrailChain`` ở ``src/guardrails/base.py``). Intent-aware rewriting
và multi-query generation nằm ngoài chain tuần tự vì hợp đồng của chúng khác
(cần thêm ``intent_hints``, hoặc trả về nhiều query thay vì một) - đây là các
điểm mở rộng riêng, độc lập với danh sách strategy.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_RULES_PATH = Path(__file__).parent / "data" / "query_rewrite_rules.json"


@lru_cache(maxsize=1)
def _load_default_rules() -> dict[str, Any]:
    """Load and cache the default rule set from the bundled JSON file."""
    with open(_DEFAULT_RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class RewriteResult:
    """Kết quả sau khi rewrite một câu query."""

    original_query: str
    rewritten_query: str
    query_variants: list[str] = field(default_factory=list)
    applied_strategies: list[str] = field(default_factory=list)


class BaseRewriteStrategy(ABC):
    """Một bước biến đổi query (chuẩn hóa hoặc mở rộng). Stateless."""

    name: str = "base"

    @abstractmethod
    def apply(self, query: str) -> str:
        """Trả về query đã biến đổi. Trả về nguyên văn nếu không áp dụng được."""
        raise NotImplementedError


class QueryNormalizer(BaseRewriteStrategy):
    """Query Normalization: chuẩn hóa cách diễn đạt, loại bỏ noise phrase.

    Thay các cụm từ mang tính khẩu ngữ/thổi phồng bằng thuật ngữ chuẩn mà
    ``FilterEngine``/``UserIntentParser`` và embedding model đã quen thuộc,
    đồng thời gộp khoảng trắng thừa. Bảng thay thế nạp từ
    ``data/query_rewrite_rules.json`` -> ``noise_replacements``.
    """

    name = "normalize"

    def __init__(self, noise_replacements: list[tuple[str, str]] | None = None):
        if noise_replacements is not None:
            self.noise_replacements = noise_replacements
        else:
            rules = _load_default_rules()
            self.noise_replacements = [
                (pattern, replacement) for pattern, replacement in rules["noise_replacements"]
            ]

    def apply(self, query: str) -> str:
        text = query.strip()
        for pattern, replacement in self.noise_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()


class TypoCorrector(BaseRewriteStrategy):
    """Query Expansion (typo correction): sửa lỗi gõ/viết tắt phổ biến.

    Whole-word, case-insensitive lookup từ bảng tĩnh nạp từ
    ``data/query_rewrite_rules.json`` -> ``typo_corrections``. Không dùng
    edit distance để tránh sửa nhầm tên riêng - chỉ sửa các biến thể đã biết.
    """

    name = "typo_correction"

    def __init__(self, corrections: dict[str, str] | None = None):
        self.corrections = (
            corrections
            if corrections is not None
            else dict(_load_default_rules()["typo_corrections"])
        )
        # Longest keys first so multi-word corrections win over shorter,
        # overlapping ones.
        keys = sorted(self.corrections, key=len, reverse=True)
        self._pattern = re.compile(
            r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", flags=re.IGNORECASE
        )

    def apply(self, query: str) -> str:
        if not self.corrections:
            return query

        def _replace(match: re.Match[str]) -> str:
            return self.corrections.get(match.group(0).lower(), match.group(0))

        return self._pattern.sub(_replace, query)


class SynonymExpander(BaseRewriteStrategy):
    """Query Expansion (synonyms): nối thêm từ đồng nghĩa vào cuối query.

    Giữ nguyên câu gốc (không thay thế) và chỉ thêm các từ chưa xuất hiện,
    để BM25/embedding phủ được cả biến thể ngôn ngữ mà người dùng không gõ.
    Bảng đồng nghĩa nạp từ ``data/query_rewrite_rules.json`` -> ``synonyms``.
    """

    name = "synonym_expansion"

    def __init__(self, synonyms: dict[str, list[str]] | None = None):
        self.synonyms = (
            synonyms if synonyms is not None else dict(_load_default_rules()["synonyms"])
        )

    def apply(self, query: str) -> str:
        query_lower = query.lower()
        extras: list[str] = []
        for term, synonyms in self.synonyms.items():
            if term not in query_lower:
                continue
            for synonym in synonyms:
                if synonym.lower() not in query_lower and synonym not in extras:
                    extras.append(synonym)
        if not extras:
            return query
        return f"{query} {' '.join(extras)}"


def build_default_strategies() -> list[BaseRewriteStrategy]:
    """Default sequential chain: normalize -> fix typos -> expand synonyms."""
    return [QueryNormalizer(), TypoCorrector(), SynonymExpander()]


class IntentAwareRewriter:
    """Intent-aware rewriting: làm giàu query bằng intent đã được parse.

    Không phải một ``BaseRewriteStrategy`` vì hợp đồng khác (cần thêm
    ``hints``, không chỉ ``query``) - đây là bước áp dụng *sau* khi
    ``UserIntentParser`` (``src/pipeline/recommend/user_intent_parser.py``)
    đã chạy, nên nhận ``hints`` như một ``dict`` thay vì import trực tiếp
    kiểu ``UserIntent`` (tránh retrieval phụ thuộc ngược vào pipeline).

    ``hints`` hỗ trợ các khóa: ``use_case`` (list[str]), ``priorities``
    (list[str]). ``brand_preference``/``category`` không cần xử lý ở đây vì
    đã được ``FilterEngine`` chuyển thành filter cứng.

    Vocabulary nạp từ ``data/query_rewrite_rules.json`` -> ``use_case_terms``/
    ``priority_terms``, mỗi khóa ánh xạ tới một *danh sách* phrase (không
    phải một chuỗi) - mỗi phrase được kiểm tra "đã có trong query chưa" độc
    lập, nên làm giàu thêm phrase mới không phá vỡ phrase cũ.
    """

    name = "intent_aware"

    def __init__(
        self,
        use_case_terms: dict[str, list[str]] | None = None,
        priority_terms: dict[str, list[str]] | None = None,
    ):
        if use_case_terms is not None and priority_terms is not None:
            self.use_case_terms = use_case_terms
            self.priority_terms = priority_terms
        else:
            rules = _load_default_rules()
            self.use_case_terms = use_case_terms or dict(rules["use_case_terms"])
            self.priority_terms = priority_terms or dict(rules["priority_terms"])

    def apply(self, query: str, hints: dict[str, Any]) -> str:
        query_lower = query.lower()
        extras: list[str] = []
        for use_case in hints.get("use_case") or []:
            for term in self.use_case_terms.get(use_case, []):
                if term.lower() not in query_lower and term not in extras:
                    extras.append(term)
        for priority in hints.get("priorities") or []:
            for term in self.priority_terms.get(priority, []):
                if term.lower() not in query_lower and term not in extras:
                    extras.append(term)
        if not extras:
            return query
        return f"{query} ({', '.join(extras)})"


class MultiQueryGenerator:
    """Multi-query generation: sinh nhiều phiên bản query để search song song.

    Mặc định trả về ``[rewritten]`` (không fan-out, giữ chi phí embedding
    không đổi). Khi ``max_variants > 1``, thêm các biến thể hữu ích:

    - ``original`` nếu khác ``rewritten`` (câu gốc, phòng trường hợp việc
      chuẩn hóa/mở rộng làm mất một tín hiệu mà embedding model cần).
    - Một biến thể "từ khóa cốt lõi" - bỏ các từ nối/hư từ tiếng Việt phổ
      biến (nạp từ ``data/query_rewrite_rules.json`` -> ``stopwords``), hữu
      ích khi câu gốc dài dòng.
    """

    def __init__(self, stopwords: frozenset[str] | None = None):
        self.stopwords = (
            stopwords if stopwords is not None else frozenset(_load_default_rules()["stopwords"])
        )

    def generate(self, original: str, rewritten: str, max_variants: int = 1) -> list[str]:
        variants = [rewritten]
        if max_variants <= 1:
            return variants

        if original.strip().lower() != rewritten.strip().lower():
            variants.append(original)

        core = self._strip_stopwords(rewritten)
        if core and core.lower() not in {v.lower() for v in variants}:
            variants.append(core)

        # De-dup while preserving order, then cap.
        seen: set[str] = set()
        deduped: list[str] = []
        for variant in variants:
            key = variant.strip().lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(variant)
        return deduped[:max_variants]

    def _strip_stopwords(self, text: str) -> str:
        words = text.split()
        kept = [w for w in words if w.lower().strip(",.!?") not in self.stopwords]
        return " ".join(kept).strip()


class QueryRewriter:
    """Facade: chạy toàn bộ pipeline rewrite và trả về ``RewriteResult``.

    Thứ tự: normalize/expand chain -> intent-aware (nếu có ``intent_hints``)
    -> multi-query generation.
    """

    def __init__(
        self,
        strategies: list[BaseRewriteStrategy] | None = None,
        intent_aware: IntentAwareRewriter | None = None,
        multi_query: MultiQueryGenerator | None = None,
        max_variants: int = 1,
    ):
        self.strategies = strategies if strategies is not None else build_default_strategies()
        self.intent_aware = intent_aware or IntentAwareRewriter()
        self.multi_query = multi_query or MultiQueryGenerator()
        self.max_variants = max_variants

    def rewrite(self, query: str, intent_hints: dict[str, Any] | None = None) -> RewriteResult:
        """Rewrite ``query``, optionally biased by already-parsed intent hints."""
        applied: list[str] = []
        text = query
        for strategy in self.strategies:
            new_text = strategy.apply(text)
            if new_text != text:
                applied.append(strategy.name)
            text = new_text

        if intent_hints:
            new_text = self.intent_aware.apply(text, intent_hints)
            if new_text != text:
                applied.append(self.intent_aware.name)
            text = new_text

        variants = self.multi_query.generate(query, text, max_variants=self.max_variants)

        return RewriteResult(
            original_query=query,
            rewritten_query=text,
            query_variants=variants,
            applied_strategies=applied,
        )
