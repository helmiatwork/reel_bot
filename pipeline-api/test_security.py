"""
Tests for security validators in pipeline-api/main.py
Tests the SSRF guard: _validate_source_url
"""

import pytest
import socket
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import main as m


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_getaddrinfo(host, port, family, socktype, public_ip=None, private_ip=None):
    """
    Mock socket.getaddrinfo for hermetic testing.
    Returns a public IP by default; can override for private/loopback cases.
    """
    def mock_getaddrinfo_impl(hostname, port, family, socktype):
        if public_ip:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (public_ip, port or 443))]
        if private_ip:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (private_ip, port or 443))]
        # Default: return a public IP (example.com's real IP)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port or 443))]
    return mock_getaddrinfo_impl


# ── SSRF Validator Tests ──────────────────────────────────────────────────────

class TestSSRFValidator:
    """Tests for _validate_source_url SSRF guard."""

    # ── ACCEPT cases: public URLs that resolve to public IPs ────────────────────

    def test_accepts_youtube_com(self):
        """Should accept youtube.com when it resolves to a public IP."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="93.184.216.34")
            result = m._validate_source_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_accepts_youtu_be(self):
        """Should accept youtu.be short links when they resolve to a public IP."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="93.184.216.34")
            result = m._validate_source_url("https://youtu.be/dQw4w9WgXcQ")
            assert result == "https://youtu.be/dQw4w9WgXcQ"

    def test_accepts_tiktok_com(self):
        """Should accept tiktok.com when it resolves to a public IP."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="93.184.216.34")
            result = m._validate_source_url("https://www.tiktok.com/@user/video/123")
            assert result == "https://www.tiktok.com/@user/video/123"

    def test_accepts_instagram_com(self):
        """Should accept instagram.com when it resolves to a public IP."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="93.184.216.34")
            result = m._validate_source_url("https://www.instagram.com/p/ABC123/")
            assert result == "https://www.instagram.com/p/ABC123/"

    def test_accepts_x_com(self):
        """Should accept x.com (Twitter) when it resolves to a public IP."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="93.184.216.34")
            result = m._validate_source_url("https://x.com/user/status/123")
            assert result == "https://x.com/user/status/123"

    def test_accepts_arbitrary_public_domain(self):
        """Should accept arbitrary public domains that resolve to public IPs."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="1.2.3.4")
            result = m._validate_source_url("https://example.com/path")
            assert result == "https://example.com/path"

    def test_accepts_http_scheme(self):
        """Should accept http:// scheme (not just https://)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, public_ip="93.184.216.34")
            result = m._validate_source_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ")
            assert result == "http://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # ── REJECT cases: security-critical ─────────────────────────────────────────

    def test_rejects_file_scheme(self):
        """Should reject file:// URLs."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("file:///etc/passwd")
        assert exc_info.value.status_code == 400

    def test_rejects_ftp_scheme(self):
        """Should reject ftp:// scheme."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("ftp://example.com/file")
        assert exc_info.value.status_code == 400

    def test_rejects_gopher_scheme(self):
        """Should reject gopher:// scheme."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("gopher://example.com")
        assert exc_info.value.status_code == 400

    def test_rejects_invalid_url_not_a_url(self):
        """Should reject invalid URLs (no scheme, no host)."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("not-a-url")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_url(self):
        """Should reject empty strings."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("")
        assert exc_info.value.status_code == 400

    def test_rejects_no_scheme_url(self):
        """Should reject URLs with no scheme."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("//no-scheme")
        assert exc_info.value.status_code == 400

    def test_rejects_localhost_literal(self):
        """Should reject localhost by hostname literal (SSRF)."""
        # localhost is special-cased in the validator before DNS resolution
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("http://localhost/")
        assert exc_info.value.status_code == 400

    def test_rejects_localhost_with_port(self):
        """Should reject localhost with port."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("http://localhost:8000/")
        assert exc_info.value.status_code == 400

    def test_rejects_localhost_localdomain(self):
        """Should reject localhost.localdomain."""
        with pytest.raises(HTTPException) as exc_info:
            m._validate_source_url("http://localhost.localdomain/")
        assert exc_info.value.status_code == 400

    def test_rejects_loopback_ip_127_0_0_1(self):
        """Should reject 127.0.0.1 (loopback IP, SSRF)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="127.0.0.1")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://127.0.0.1/")
            assert exc_info.value.status_code == 400

    def test_rejects_ipv6_loopback(self):
        """Should reject IPv6 loopback ::1 (SSRF)."""
        with patch("socket.getaddrinfo") as mock_ga:
            def mock_ipv6_loopback(hostname, port, family, socktype):
                return [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::1', port or 443))]
            mock_ga.side_effect = mock_ipv6_loopback
            # Use a non-special hostname so DNS resolution (mocked to ::1) is exercised
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://ipv6-host.example.com/")
            assert exc_info.value.status_code == 400

    def test_rejects_private_range_10_0_0_0(self):
        """Should reject 10.0.0.0/8 private range (SSRF)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="10.0.0.5")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://internal.example.com/")
            assert exc_info.value.status_code == 400

    def test_rejects_private_range_192_168(self):
        """Should reject 192.168.0.0/16 private range (SSRF)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="192.168.1.1")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://router.local/")
            assert exc_info.value.status_code == 400

    def test_rejects_private_range_172_16(self):
        """Should reject 172.16.0.0/12 private range (SSRF)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="172.16.0.1")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://vpc.internal/")
            assert exc_info.value.status_code == 400

    def test_rejects_link_local_169_254(self):
        """Should reject 169.254.0.0/16 link-local range."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="169.254.169.254")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://metadata.example.com/")
            assert exc_info.value.status_code == 400

    def test_rejects_aws_metadata_endpoint(self):
        """Should reject AWS/GCP metadata SSRF endpoint (169.254.169.254, CRITICAL)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="169.254.169.254")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://169.254.169.254/latest/meta-data/")
            assert exc_info.value.status_code == 400

    def test_rejects_unresolvable_hostname(self):
        """Should reject hostnames that do not resolve (gaierror)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://this-definitely-does-not-exist-12345.invalid/")
            assert exc_info.value.status_code == 400

    def test_rejects_malformed_ip_from_getaddrinfo(self):
        """Should reject if getaddrinfo returns unparseable IP."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('not-an-ip', 443))]
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://example.com/")
            assert exc_info.value.status_code == 400

    # ── NEW: Multi-address bypass attacks (FIX #1: check ALL addresses) ────────

    def test_rejects_multi_address_public_then_private(self):
        """Should reject when getaddrinfo returns public IP first + private IP second.
        Attack: attacker puts public IP first to bypass single-check validator,
        then yt-dlp uses the second private IP for SSRF."""
        with patch("socket.getaddrinfo") as mock_ga:
            def mock_multi_address(hostname, port, family, socktype):
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port or 443)),  # public first
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', port or 443))         # private second (ATTACK)
                ]
            mock_ga.side_effect = mock_multi_address
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://attacker.example.com/")
            assert exc_info.value.status_code == 400

    # ── NEW: Empty resolution result (FIX #2: check that we got at least one IP) ──

    def test_rejects_empty_address_list(self):
        """Should reject when getaddrinfo returns empty list."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = []
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://example.com/")
            assert exc_info.value.status_code == 400

    # ── NEW: CGNAT and other ranges (FIX #3: extra blocked networks) ──────────

    def test_rejects_0_0_0_0_this_host(self):
        """Should reject 0.0.0.0/8 (This Host special range)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="0.0.0.5")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://example.com/")
            assert exc_info.value.status_code == 400

    def test_rejects_cgnat_100_64(self):
        """Should reject 100.64.0.0/10 (Carrier-Grade NAT, RFC 6598)."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = _mock_getaddrinfo(None, None, None, None, private_ip="100.64.1.1")
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://example.com/")
            assert exc_info.value.status_code == 400

    # ── NEW: IPv4-mapped IPv6 loopback (FIX #3: check ipv4_mapped) ─────────────

    def test_rejects_ipv4_mapped_loopback(self):
        """Should reject IPv4-mapped loopback ::ffff:127.0.0.1."""
        with patch("socket.getaddrinfo") as mock_ga:
            def mock_ipv4_mapped_loopback(hostname, port, family, socktype):
                # getaddrinfo returns the mapped form in sockaddr
                return [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::ffff:127.0.0.1', port or 443))]
            mock_ga.side_effect = mock_ipv4_mapped_loopback
            with pytest.raises(HTTPException) as exc_info:
                m._validate_source_url("http://example.com/")
            assert exc_info.value.status_code == 400


if __name__ == "__main__":
    # Support running with pytest
    pytest.main([__file__, "-v"])
