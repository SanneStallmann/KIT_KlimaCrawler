# analyze_topics.py
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
from sklearn.feature_extraction.text import CountVectorizer
from sentence_transformers import SentenceTransformer


DB_PATH = Path("crawler/data/db/crawl.sqlite")
OUT_DIR = Path("topic_out")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_scored_segments(
    db_path: Path,
    limit: int = 100_000,
    min_len: int = 150,
    min_score: int = 15,
    per_doc: int = 6,
) -> pd.DataFrame:
    """
    Loads only relevant segments using stored crawler scores.
    Requires Storage to have created: segments.impact_score, segments.is_negative
    """
    query = """
    WITH ranked AS (
      SELECT
        s.text,
        s.document_id,
        d.municipality_id,
        COALESCE(s.impact_score, 0) AS impact_score,
        COALESCE(s.is_negative, 0) AS is_negative,
        ROW_NUMBER() OVER (
          PARTITION BY s.document_id
          ORDER BY COALESCE(s.impact_score, 0) DESC
        ) AS rn
      FROM segments s
      JOIN documents_raw d ON d.document_id = s.document_id
      WHERE length(s.text) >= ?
        AND COALESCE(s.is_negative, 0) = 0
        AND COALESCE(s.impact_score, 0) >= ?
    )
    SELECT text, document_id, municipality_id, impact_score
    FROM ranked
    WHERE rn <= ?
    ORDER BY impact_score DESC
    LIMIT ?;
    """

    with sqlite3.connect(str(db_path)) as conn:
        df = pd.read_sql_query(query, conn, params=(min_len, min_score, per_doc, limit))

    # minimal cleanup
    df["text"] = (
        df["text"]
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    df = df[df["text"].str.len() >= min_len]
    df = df.drop_duplicates(subset=["text"])
    return df.reset_index(drop=True)


def main():
    # ---- Load corpus (scored) ----
    df = load_scored_segments(
        DB_PATH,
        limit=120_000,
        min_len=150,
        min_score=15,
        per_doc=6,
    )
    if df.empty:
        raise RuntimeError("No segments matched the scored filter. Did you crawl with the patched engine/storage?")

    docs = df["text"].tolist()
    print(f"Loaded {len(docs):,} scored segments for topic modeling.")

    # ---- GPU embedding (if available) ----
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Embedding device: {device}")

    embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device=device)
    embedding_model.max_seq_length = 256

    # Precompute embeddings (faster & reproducible)
    batch_size = 256 if device == "cuda" else 64
    embeddings = embedding_model.encode(
        docs,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    # ---- Vectorizer / Representation (quality boost) ----
    # (sklearn has no built-in german stopwords; keep it simple or plug stopwordsiso if you want)
    vectorizer_model = CountVectorizer(
        ngram_range=(1, 3),
        min_df=5,
        max_df=0.95,
        max_features=120_000,
        token_pattern=r"(?u)\b[\wäöüÄÖÜß]{2,}\b",
    )
    representation_model = KeyBERTInspired()

    topic_model = BERTopic(
        embedding_model=None,  # we pass embeddings explicitly
        language="german",
        vectorizer_model=vectorizer_model,
        representation_model=representation_model,
        calculate_probabilities=False,  # faster; enable only if needed
        nr_topics="auto",
        min_topic_size=25,
        verbose=True,
    )

    topics, probs = topic_model.fit_transform(docs, embeddings=embeddings)

    # ---- Save outputs ----
    info = topic_model.get_topic_info()
    info.to_csv(OUT_DIR / "topic_info.csv", index=False)

    assignments = df.copy()
    assignments["topic"] = topics
    assignments.to_parquet(OUT_DIR / "doc_segments_topics.parquet", index=False)
    assignments[["document_id", "municipality_id", "impact_score", "topic"]].to_csv(
        OUT_DIR / "doc_segments_topics.csv", index=False
    )

    topic_model.visualize_topics().write_html(str(OUT_DIR / "topic_map.html"))
    topic_model.visualize_barchart(top_n_topics=15).write_html(str(OUT_DIR / "topic_bar_chart.html"))

    print(f"Done. Outputs in {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()