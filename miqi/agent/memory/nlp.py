"""NLP utilities for memory: tokenization, text cleaning, similarity."""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from typing import Any


class TextProcessor:
    """Text processing utilities for memory operations."""

    EN_STOPWORDS = {
        "a", "an", "the", "and", "or", "for", "with", "this", "that",
        "you", "your", "are", "is", "to", "of", "in", "on", "it",
        "we", "our", "can", "please", "from", "now", "then", "still",
        "first", "just",
    }
    ZH_STOPWORDS = {
        "这个", "那个", "一下", "然后", "就是", "我们", "你们",
        "还有", "以及", "是否", "可以", "需要", "已经", "现在",
    }
    TOKEN_SYNONYMS = {
        "paths": "path", "路径": "path",
        "repo": "repo", "repository": "repo", "仓库": "repo",
        "project": "project", "projects": "project", "项目": "project",
        "config": "config", "configuration": "config", "配置": "config",
        "database": "database", "databases": "database", "数据库": "database",
        "memory": "memory", "memories": "memory", "记忆": "memory",
        "lesson": "lesson", "lessons": "lesson", "教训": "lesson",
    }
    TOKEN_SUBSTRING_SYNONYMS = {
        "路径": "path", "仓库": "repo", "项目": "project",
        "配置": "config", "数据库": "database", "记忆": "memory",
        "教训": "lesson",
    }

    @classmethod
    def normalize_token(cls, token: str) -> str:
        """Normalize token and drop low-signal terms."""
        text = token.strip().lower()
        if len(text) < 2:
            return ""
        mapped = cls.TOKEN_SYNONYMS.get(text, text)
        if mapped in cls.EN_STOPWORDS or mapped in cls.ZH_STOPWORDS:
            return ""
        return mapped

    @classmethod
    def tokenize_terms(cls, text: str) -> list[str]:
        """Tokenize text into weighted lexical terms with light normalization."""
        raw_tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
        normalized_terms: list[str] = []
        for token in raw_tokens:
            normalized = cls.normalize_token(token)
            if normalized:
                normalized_terms.append(normalized)
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                for phrase, mapped in cls.TOKEN_SUBSTRING_SYNONYMS.items():
                    if phrase in token:
                        normalized_terms.append(mapped)
        return normalized_terms

    @classmethod
    def tokenize(cls, text: str) -> set[str]:
        """Tokenize text into normalized lexical terms."""
        return set(cls.tokenize_terms(text))

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for deduplication."""
        return re.sub(r"\s+", " ", text.strip().lower())

    @staticmethod
    def clean_text(text: str, max_len: int) -> str:
        """Normalize whitespace and trim to max length."""
        cleaned = re.sub(r"\s+", " ", text.strip())
        if len(cleaned) > max_len:
            return cleaned[: max_len - 3] + "..."
        return cleaned

    @staticmethod
    def clean_text_with_tail(text: str, max_len: int, head_chars: int) -> str:
        """Trim text while keeping both head and tail context."""
        cleaned = re.sub(r"\s+", " ", text.strip())
        if len(cleaned) <= max_len:
            return cleaned
        head = cleaned[: max(20, min(head_chars, max_len - 20))]
        tail_len = max_len - len(head) - 5
        tail = cleaned[-tail_len:] if tail_len > 0 else ""
        return f"{head} ... {tail}".strip()

    @staticmethod
    def recency_bonus(iso_time: str) -> float:
        """Compute a mild recency bonus from ISO timestamp."""
        if not iso_time:
            return 0.0
        try:
            dt = datetime.fromisoformat(iso_time)
            age_hours = max(0.0, (datetime.now() - dt).total_seconds() / 3600)
            return 1.0 / (1.0 + math.log1p(age_hours))
        except Exception:
            return 0.0

    @classmethod
    def select_items_by_relevance(
        cls,
        items: list[dict[str, Any]],
        current_message: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Select items ranked by TF-IDF relevance + recency + hits."""
        if not items:
            return []

        query_terms = cls.tokenize_terms(current_message or "")
        query_counts = Counter(query_terms)
        query_tokens = set(query_terms)

        doc_terms_by_id: dict[str, set[str]] = {}
        doc_frequency: dict[str, int] = {}
        for item in items:
            item_id = str(item.get("id", ""))
            terms = set(cls.tokenize_terms(str(item.get("text", ""))))
            doc_terms_by_id[item_id] = terms
            for term in terms:
                doc_frequency[term] = doc_frequency.get(term, 0) + 1
        doc_total = max(1, len(items))

        def _idf(term: str) -> float:
            return 1.0 + math.log((doc_total + 1.0) / (doc_frequency.get(term, 0) + 1.0))

        def _score(item: dict[str, Any]) -> tuple[float, float, int, str]:
            item_id = str(item.get("id", ""))
            terms = doc_terms_by_id.get(item_id, set())
            relevance = 0.0
            if query_tokens and terms:
                shared = query_tokens & terms
                if shared:
                    overlap = sum(
                        (1.0 + math.log1p(query_counts.get(term, 1))) * _idf(term)
                        for term in shared
                    )
                    coverage = len(shared) / max(1, len(query_tokens))
                    length_norm = math.sqrt(max(1.0, float(len(terms))))
                    relevance = (overlap / length_norm) + (coverage * 0.75)
            recency = str(item.get("updated_at", ""))
            recency_val = cls.recency_bonus(recency)
            hits = int(item.get("hits", 0))
            hit_bonus = math.log1p(max(0, hits)) * 0.05
            return (
                relevance + (recency_val * 0.2) + hit_bonus,
                relevance,
                hits,
                recency,
            )

        items_copy = list(items)
        items_copy.sort(key=_score, reverse=True)
        return items_copy[: max(1, limit)]

    @staticmethod
    def extract_path_hint(result: str) -> str:
        """Extract a likely path token from tool error output."""
        match = re.search(r"(/[\w\-.~/]+(?:/[\w\-.~]+)*)", result)
        if not match:
            return ""
        return match.group(1)

    @staticmethod
    def extract_param_name(result: str) -> str:
        """Extract likely parameter name from validation-style errors."""
        patterns = [
            r"(?:missing required(?: parameter| field)?[:\s`'\"]+)([A-Za-z_][\w.-]*)",
            r"(?:invalid(?: parameter| argument)?[:\s`'\"]+)([A-Za-z_][\w.-]*)",
            r"(?:for parameter[:\s`'\"]+)([A-Za-z_][\w.-]*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""
