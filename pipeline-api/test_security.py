"""
Tests for security validators in pipeline-api/main.py
Tests the YouTube URL SSRF guard.
"""

from urllib.parse import urlparse


# YouTube hosts allowlist (replicated from main.py to avoid fastapi import)
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be",
}


def _validate_youtube_url_test(url: str) -> bool:
    """Test version of _validate_youtube_url that returns bool instead of raising.
    Returns True if valid, False if invalid."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return host in _YOUTUBE_HOSTS


class TestYouTubeURLValidator:
    """Tests for YouTube URL validation (SSRF guard)."""

    def test_accepts_standard_youtube_urls(self):
        """Should accept standard YouTube URLs."""
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        ]
        for url in valid_urls:
            assert _validate_youtube_url_test(url), f"Should accept {url}"

    def test_accepts_youtu_be_short_urls(self):
        """Should accept youtu.be short links."""
        assert _validate_youtube_url_test("https://youtu.be/dQw4w9WgXcQ")
        assert _validate_youtube_url_test("http://youtu.be/dQw4w9WgXcQ")

    def test_accepts_music_youtube(self):
        """Should accept music.youtube.com."""
        assert _validate_youtube_url_test("https://music.youtube.com/watch?v=abc123")

    def test_rejects_localhost(self):
        """Should reject localhost URLs (SSRF)."""
        assert not _validate_youtube_url_test("http://localhost/")
        assert not _validate_youtube_url_test("http://localhost:8000/")
        assert not _validate_youtube_url_test("http://127.0.0.1/")

    def test_rejects_private_ips(self):
        """Should reject private IP ranges (SSRF)."""
        assert not _validate_youtube_url_test("http://10.0.0.5/")
        assert not _validate_youtube_url_test("http://192.168.1.1/")
        assert not _validate_youtube_url_test("http://172.16.0.1/")

    def test_rejects_metadata_endpoint(self):
        """Should reject cloud metadata endpoints (SSRF)."""
        assert not _validate_youtube_url_test("http://169.254.169.254/latest/meta-data/")

    def test_rejects_arbitrary_domains(self):
        """Should reject arbitrary domains (SSRF)."""
        assert not _validate_youtube_url_test("https://evil.com/")
        assert not _validate_youtube_url_test("https://attacker.com/")
        assert not _validate_youtube_url_test("https://internal.company.com/")

    def test_rejects_wrong_scheme(self):
        """Should reject non-http(s) schemes (SSRF)."""
        assert not _validate_youtube_url_test("ftp://youtube.com/")
        assert not _validate_youtube_url_test("file:///etc/passwd")
        assert not _validate_youtube_url_test("gopher://youtube.com/")

    def test_rejects_suffix_spoofing(self):
        """Should reject domain suffix spoofing."""
        assert not _validate_youtube_url_test("https://youtube.com.evil.com/")
        assert not _validate_youtube_url_test("https://www.youtube.com.attacker.com/")

    def test_rejects_invalid_url(self):
        """Should reject invalid URLs."""
        assert not _validate_youtube_url_test("not-a-url")
        assert not _validate_youtube_url_test("")
        assert not _validate_youtube_url_test("//no-scheme")


if __name__ == "__main__":
    # Run all tests manually
    import sys

    test_instance = TestYouTubeURLValidator()
    test_methods = [m for m in dir(test_instance) if m.startswith("test_")]

    passed = 0
    failed = 0

    for test_name in test_methods:
        try:
            method = getattr(test_instance, test_name)
            method()
            print(f"✓ {test_name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_name}: ERROR: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
