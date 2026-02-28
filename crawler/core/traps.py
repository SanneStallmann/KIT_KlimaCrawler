from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TrapConfig:
    block_extensions: tuple[str, ...]
    block_path_patterns: tuple[str, ...]
    pagination_tokens: tuple[str, ...]
    max_pagination_depth: int = 20
    max_url_length: int = 2048
    max_query_params: int = 60
    max_repeated_param: int = 5


class TrapDetector:
    """
    Conservative trap detection to prevent infinite crawl spaces.
    Recall-first: blocks only obvious explosion sources.

    Optimizations vs original:
    - O(1) membership structures where possible (sets)
    - early-exit cheap checks (length, repeated params)
    - precompiled regex, fewer per-call allocations
    - optional caching for repeated URL checks
    - supports depth-based pagination guard
    """

    _RE_EXT = re.compile(r"\.([a-z0-9]{1,6})(?:\?|$)", re.IGNORECASE)
    _RE_PAGE_NUM = re.compile(r"(?:/page/|page=|offset=|start=)(\d+)", re.IGNORECASE)
    _RE_QUERY_SPLIT = re.compile(r"[&;]")

    def __init__(
        self,
        block_extensions: list[str],
        block_path_patterns: list[str],
        pagination_tokens: list[str],
        max_pagination_depth: int = 20,
        *,
        max_url_length: int = 2048,
        max_query_params: int = 60,
        max_repeated_param: int = 5,
        enable_cache: bool = True,
        cache_size: int = 200_000,
    ) -> None:
        self.cfg = TrapConfig(
            block_extensions=tuple(sorted({e.lower().lstrip(".") for e in block_extensions if e})),
            block_path_patterns=tuple(p.lower() for p in block_path_patterns if p),
            pagination_tokens=tuple(sorted({t.lower() for t in pagination_tokens if t})),
            max_pagination_depth=int(max_pagination_depth),
            max_url_length=int(max_url_length),
            max_query_params=int(max_query_params),
            max_repeated_param=int(max_repeated_param),
        )

        self._block_ext = set(self.cfg.block_extensions)
        self._pagination_tokens = set(self.cfg.pagination_tokens)
        self._block_path_patterns = self.cfg.block_path_patterns

        if enable_cache:
            self._should_block_impl = lru_cache(maxsize=int(cache_size))(self._should_block_impl)  
        else:
            self._should_block_impl = self._should_block_impl 

    def should_block(self, url: str, depth: int) -> bool:
        return bool(self._should_block_impl(url, int(depth)))

    def _should_block_impl(self, url: str, depth: int) -> bool:
        if not url:
            return True

        if len(url) > self.cfg.max_url_length:
            return True

        u = url.lower()

        m = self._RE_EXT.search(u)
        if m and m.group(1).lower() in self._block_ext:
            return True

        for pat in self._block_path_patterns:
            if pat in u:
                return True

        qpos = u.find("?")
        if qpos != -1 and qpos + 1 < len(u):
            query = u[qpos + 1 :]
            parts = self._RE_QUERY_SPLIT.split(query) if query else []
            if len(parts) > self.cfg.max_query_params:
                return True

            counts: dict[str, int] = {}
            for part in parts:
                if not part:
                    continue
                key = part.split("=", 1)[0]
                if not key:
                    continue
                c = counts.get(key, 0) + 1
                if c > self.cfg.max_repeated_param:
                    return True
                counts[key] = c

        if self._pagination_tokens and any(tok in u for tok in self._pagination_tokens):
            m2 = self._RE_PAGE_NUM.search(u)
            if m2:
                try:
                    n = int(m2.group(1))
                    if n > self.cfg.max_pagination_depth:
                        return True
                except ValueError:
                    pass
            if depth > self.cfg.max_pagination_depth:
                return True

        return False
