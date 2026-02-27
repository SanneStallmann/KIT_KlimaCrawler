# crawler/core/parsers/pdf_parser.py
from __future__ import annotations

import subprocess
import logging
from typing import Any

from crawler.core.models import ParseResult, Segment

logger = logging.getLogger(__name__)

def parse_pdf(fetch_result: Any, url: str) -> ParseResult:
    """Extrahiert Text aus einem PDF-FetchResult mittels Poppler (pdftotext)."""
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=fetch_result.body,
            capture_output=True,
            timeout=30  # Timeout für riesige oder kaputte PDFs
        )
        
        if proc.returncode != 0:
            logger.warning(f"Fehler beim Parsen von PDF {url}: {proc.stderr.decode('utf-8', errors='ignore')}")
            return ParseResult(text="", segments=[], out_links=[])
        
        full_text = proc.stdout.decode("utf-8", errors="replace")
        
        # pdftotext trennt Seiten mit Form Feed (\x0c)
        pages = full_text.split('\x0c')
        segments = []
        
        for i, page_text in enumerate(pages):
            cleaned_text = page_text.strip()
            if cleaned_text:
                segments.append(
                    Segment(
                        order_index=i,
                        segment_type="pdf_page",
                        text=cleaned_text,
                        page_ref=str(i + 1)
                    )
                )
                
        return ParseResult(text=full_text, segments=segments, out_links=[])
        
    except FileNotFoundError:
        logger.error("'pdftotext' fehlt. Bitte Poppler installieren (z.B. 'brew install poppler').")
        return ParseResult(text="", segments=[], out_links=[])
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout beim Parsen von PDF: {url}")
        return ParseResult(text="", segments=[], out_links=[])
    except Exception as e:
        logger.error(f"Unerwarteter Fehler bei PDF {url}: {e}")
        return ParseResult(text="", segments=[], out_links=[])