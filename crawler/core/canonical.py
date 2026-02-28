from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import posixpath
import re
from typing import Iterable


@dataclass(frozen=True)
class CanonicalizeResult:
    url: str
    changed: bool


class Canonicalizer:

    _RE_MULTI_SLASH = re.compile(r"/{2,}")
    _RE_DEFAULT_PORT = re.compile(r"^(?P<host>\[[^\]]+\]|[^:]+):(?P<port>\d+)$")  

    def __init__(
        self,
        strip_fragment: bool = True,
        drop_query_prefixes: list[str] | None = None,
        drop_query_keys: list[str] | None = None,
        normalize_trailing_slash: bool = True,
        strip_default_ports: bool = True,
        strip_www: bool = False,
        force_https_default_scheme: bool = False,
        lowercase_path: bool = False,  
    ) -> None:
        self.strip_fragment = bool(strip_fragment)
        self.drop_query_prefixes = tuple(p.lower() for p in (drop_query_prefixes or []))
        self.drop_query_keys = frozenset(k.lower() for k in (drop_query_keys or []))
        self.normalize_trailing_slash = bool(normalize_trailing_slash)
        self.strip_default_ports = bool(strip_default_ports)
        self.strip_www = bool(strip_www)
        self.force_https_default_scheme = bool(force_https_default_scheme)
        self.lowercase_path = bool(lowercase_path)

    def normalize(self, url: str) -> str:
        """
        Returns canonical URL or "" if URL is unusable (e.g., not http(s), missing host).
        """
        u = (url or "").strip()
        if not u:
            return ""

        parts = urlsplit(u)

        scheme = (parts.scheme or "").lower()
        if not scheme:
            if not self.force_https_default_scheme:
                return ""
            scheme = "https"

        if scheme not in ("http", "https"):
            return ""

        netloc = (parts.netloc or "").strip().lower()
        if not netloc:
            return ""

        if self.strip_www and netloc.startswith("www."):
            netloc = netloc[4:]

        if self.strip_default_ports:
            m = self._RE_DEFAULT_PORT.match(netloc)
            if m:
                host = m.group("host")
                port = m.group("port")
                if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
                    netloc = host

        path = parts.path or "/"
        path = self._RE_MULTI_SLASH.sub("/", path)

        path = posixpath.normpath(path)
        if path == ".":
            path = "/"
        if not path.startswith("/"):
            path = "/" + path

        if self.lowercase_path:
            path = path.lower()

        if self.normalize_trailing_slash and path != "/" and path.endswith("/"):
            path = path[:-1]

        kept: list[tuple[str, str]] = []
        if parts.query:
            for k, v in parse_qsl(parts.query, keep_blank_values=True):
                kl = (k or "").lower()

                if kl in self.drop_query_keys:
                    continue
                if self.drop_query_prefixes and any(kl.startswith(pfx) for pfx in self.drop_query_prefixes):
                    continue
                kept.append((k, v))

        kept.sort(key=lambda kv: (kv[0].lower(), kv[1]))
        query = urlencode(kept, doseq=True)

        fragment = "" if self.strip_fragment else (parts.fragment or "")

        return urlunsplit((scheme, netloc, path, query, fragment))

    def normalize_with_change(self, url: str) -> CanonicalizeResult:
        u0 = (url or "").strip()
        u1 = self.normalize(u0)
        return CanonicalizeResult(url=u1, changed=(u1 != u0))

    def normalize_many(self, urls: Iterable[str]) -> list[str]:
        out: list[str] = []
        for u in urls:
            cu = self.normalize(u)
            if cu:
                out.append(cu)
        return out
