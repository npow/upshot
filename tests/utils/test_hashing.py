"""Tests for hashing utilities."""

from upshot.utils.hashing import sha256_hash, content_hash, cache_key


def test_sha256_hash_string():
    result = sha256_hash("hello")
    assert len(result) == 64
    assert result == sha256_hash("hello")  # deterministic


def test_sha256_hash_bytes():
    result = sha256_hash(b"hello")
    assert len(result) == 64


def test_sha256_different_inputs():
    assert sha256_hash("hello") != sha256_hash("world")


def test_content_hash():
    h1 = content_hash("Subject", "Body text")
    h2 = content_hash("Subject", "Body text")
    h3 = content_hash("Different", "Body text")
    assert h1 == h2
    assert h1 != h3


def test_cache_key():
    k1 = cache_key("model-a", "v1", "input text")
    k2 = cache_key("model-a", "v1", "input text")
    k3 = cache_key("model-b", "v1", "input text")
    assert k1 == k2
    assert k1 != k3
