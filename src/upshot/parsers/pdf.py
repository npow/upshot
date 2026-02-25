"""PDF extraction — arXiv URL rewriting, PDF download, text extraction."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

import httpx
import pymupdf

from upshot.utils.rate_limiter import get_rate_limiter
from upshot.utils.retry import retry
from upshot.utils.text import clean_text

logger = logging.getLogger(__name__)


def arxiv_to_pdf_url(url: str) -> str | None:
    """Convert an arXiv abstract URL to a PDF URL.

    Examples:
        https://arxiv.org/abs/2301.12345 → https://arxiv.org/pdf/2301.12345.pdf
        https://arxiv.org/pdf/2301.12345.pdf → unchanged
    """
    # Already a PDF URL
    if "/pdf/" in url:
        return url

    match = re.search(r"arxiv\.org/abs/([\d.]+)", url)
    if match:
        arxiv_id = match.group(1)
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    return None


def extract_arxiv_id(url: str) -> str | None:
    """Extract arXiv ID from a URL."""
    match = re.search(r"(\d{4}\.\d{4,5})", url)
    return match.group(1) if match else None


@retry(max_attempts=2, base_delay=3.0, exceptions=(httpx.HTTPError,))
def download_pdf(url: str, output_dir: Path | None = None) -> Path:
    """Download a PDF file from a URL."""
    rate_limiter = get_rate_limiter()
    rate_limiter.acquire(url)

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        resp = client.get(url)
        resp.raise_for_status()

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = url.split("/")[-1]
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        path = output_dir / filename
        path.write_bytes(resp.content)
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(resp.content)
        tmp.close()
        path = Path(tmp.name)

    return path


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    doc = pymupdf.open(str(pdf_path))
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return clean_text("\n".join(text_parts))


def fetch_paper(url: str) -> dict:
    """Fetch and extract a paper from an arXiv URL (or generic PDF URL).

    Returns dict with: arxiv_id, pdf_url, text, authors, abstract
    """
    arxiv_id = extract_arxiv_id(url)
    pdf_url = arxiv_to_pdf_url(url) or url

    pdf_path = download_pdf(pdf_url)
    text = extract_pdf_text(pdf_path)

    # Clean up temp file
    try:
        pdf_path.unlink()
    except OSError:
        pass

    # Try to extract abstract and authors from text
    abstract = ""
    authors = []

    # Simple abstract extraction from paper text
    abstract_match = re.search(
        r"(?:abstract|summary)\s*[:\n]\s*(.+?)(?:\n\s*\n|\n\d+\.?\s+introduction)",
        text[:5000],
        re.IGNORECASE | re.DOTALL,
    )
    if abstract_match:
        abstract = clean_text(abstract_match.group(1))

    return {
        "arxiv_id": arxiv_id,
        "pdf_url": pdf_url,
        "text": text,
        "authors": authors,
        "abstract": abstract,
    }
