"""Tests for PDF/arXiv parsing."""

from upshot.parsers.pdf import arxiv_to_pdf_url, extract_arxiv_id


def test_arxiv_abs_to_pdf():
    url = "https://arxiv.org/abs/2401.12345"
    assert arxiv_to_pdf_url(url) == "https://arxiv.org/pdf/2401.12345.pdf"


def test_arxiv_pdf_unchanged():
    url = "https://arxiv.org/pdf/2401.12345.pdf"
    assert arxiv_to_pdf_url(url) == url


def test_non_arxiv_returns_none():
    assert arxiv_to_pdf_url("https://example.com/paper") is None


def test_extract_arxiv_id():
    assert extract_arxiv_id("https://arxiv.org/abs/2401.12345") == "2401.12345"
    assert extract_arxiv_id("https://arxiv.org/pdf/2401.12345.pdf") == "2401.12345"
    assert extract_arxiv_id("https://example.com") is None
