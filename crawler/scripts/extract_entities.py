import sqlite3
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple, Optional


# ---------- ANSI colors (optional) ----------
COLOR_MONEY = "\033[92m"
COLOR_ORG = "\033[96m"
COLOR_RESET = "\033[0m"


# ---------- Patterns ----------
# Money: "12.500 €", "12.500,00 Euro", "2 Mio €", "3,5 Mrd Euro", "800 Tsd."
MONEY_RE = re.compile(
    r"""
    (?:
        \b\d{1,3}(?:\.\d{3})*(?:,\d+)?\s*(?:€|euro)\b
        |
        \b\d+(?:[.,]\d+)?\s*(?:mio|mio\.|tsd|tsd\.|mrd|mrd\.)\s*(?:€|euro)?\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Funding/finance trigger words
FINANCE_TRIGGERS_RE = re.compile(
    r"\b(förder\w*|zuschuss\w*|invest\w*|finanz\w*|mittel\w*|haushalt\w*|kfw\b|bafa\b|efre\b|eler\b|eu[- ]?förder\w*|bund\b|land\b)\b",
    re.IGNORECASE,
)

# Actor/org hints (very rough, just for highlighting)
ORG_RE = re.compile(
    r"\b(gmbh|ag|e\.v\.|verein|genossenschaft|stiftung|stadtwerk\w*|landkreis|gemeinde|ministerium|bund|freistaat)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    municipality_id: str
    document_id: str
    url_final: str
    segment_rowid: int
    impact_score: int
    text: str


def highlight_text(text: str, *, use_color: bool = True) -> str:
    if not use_color:
        return text

    text = MONEY_RE.sub(lambda m: f"{COLOR_MONEY}{m.group(0)}{COLOR_RESET}", text)
    text = ORG_RE.sub(lambda m: f"{COLOR_ORG}{m.group(0)}{COLOR_RESET}", text)
    # highlight finance triggers too (same color as org)
    text = FINANCE_TRIGGERS_RE.sub(lambda m: f"{COLOR_ORG}{m.group(0)}{COLOR_RESET}", text)
    return text


def fetch_finance_candidates(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
    min_len: int = 160,
    min_score: int = 15,
    per_doc: int = 2,
) -> List[Candidate]:
    """
    Uses the crawler-scored fields:
      - segments.impact_score
      - segments.is_negative
    plus finance triggers (regex-ish via LIKE / cheap prefilter).
    """
    # Fast SQL prefilter (cheap), final highlighting is regex on Python side.
    query = """
    WITH ranked AS (
      SELECT
        s.rowid AS segment_rowid,
        d.municipality_id,
        d.document_id,
        COALESCE(d.url_final, d.url_canonical) AS url_final,
        s.text,
        COALESCE(s.impact_score, 0) AS impact_score,
        ROW_NUMBER() OVER (
          PARTITION BY s.document_id
          ORDER BY COALESCE(s.impact_score, 0) DESC
        ) AS rn
      FROM segments s
      JOIN documents_raw d ON d.document_id = s.document_id
      WHERE length(s.text) >= ?
        AND COALESCE(s.is_negative, 0) = 0
        AND COALESCE(s.impact_score, 0) >= ?
        -- cheap finance prefilter (avoid regex in SQL)
        AND (
          s.text LIKE '%€%' OR s.text LIKE '%Euro%' OR s.text LIKE '%Mio%' OR s.text LIKE '%Mrd%' OR s.text LIKE '%Tsd%'
        )
        AND (
          s.text LIKE '%Förder%' OR s.text LIKE '%Zuschuss%' OR s.text LIKE '%Invest%' OR s.text LIKE '%Haushalt%' OR
          s.text LIKE '%KfW%' OR s.text LIKE '%BAFA%' OR s.text LIKE '%EFRE%' OR s.text LIKE '%ELER%' OR
          s.text LIKE '%EU%' OR s.text LIKE '%Bund%' OR s.text LIKE '%Land%'
        )
    )
    SELECT municipality_id, document_id, url_final, segment_rowid, impact_score, text
    FROM ranked
    WHERE rn <= ?
    ORDER BY impact_score DESC
    LIMIT ?;
    """

    cur = conn.cursor()
    cur.execute(query, (min_len, min_score, per_doc, limit))
    rows = cur.fetchall()

    out: List[Candidate] = []
    for muni_id, doc_id, url_final, rowid, score, text in rows:
        out.append(
            Candidate(
                municipality_id=str(muni_id),
                document_id=str(doc_id),
                url_final=str(url_final),
                segment_rowid=int(rowid),
                impact_score=int(score or 0),
                text=str(text or ""),
            )
        )
    return out


def analyze_finances(
    *,
    db_path: Path = Path("crawler/data/db/crawl.sqlite"),
    limit: int = 15,
    min_len: int = 160,
    min_score: int = 15,
    per_doc: int = 2,
    wrap_width: int = 100,
    use_color: bool = True,
) -> None:
    if not db_path.exists():
        print(f"❌ Datenbank nicht gefunden unter: {db_path}")
        return

    conn = sqlite3.connect(str(db_path), timeout=60.0, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=60000;")

        cands = fetch_finance_candidates(
            conn,
            limit=limit,
            min_len=min_len,
            min_score=min_score,
            per_doc=per_doc,
        )
    finally:
        conn.close()

    print("\n" + "=" * 90)
    print(f"💰 FINANZ-EXPLORER: {len(cands)} Kandidaten (score≥{min_score}, len≥{min_len}, per_doc={per_doc})")
    print("=" * 90 + "\n")

    if not cands:
        print("Keine Kandidaten gefunden. Entweder fehlen Scores (Crawler nicht gepatcht) oder thresholds zu hart.")
        return

    for c in cands:
        print(f"📍 muni={c.municipality_id}  doc={c.document_id}  rowid={c.segment_rowid}  score={c.impact_score}")
        print(f"🔗 Quelle: {c.url_final}")
        print("-" * 90)

        clean_text = " ".join(c.text.split())
        highlighted = highlight_text(clean_text, use_color=use_color)
        print(textwrap.fill(highlighted, width=wrap_width))
        print("\n" + "=" * 90 + "\n")


if __name__ == "__main__":
    analyze_finances(limit=15, min_len=160, min_score=15, per_doc=2, wrap_width=110, use_color=True)