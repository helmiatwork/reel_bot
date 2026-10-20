"""Unit and integration tests for content hierarchy and music scraper."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Setup path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import main
from main import (
    app,
    _slugify,
    _get_or_create_category,
    _get_or_create_artist,
    _scrape_lyrics,
    _scrape_music_content,
    _songs_init_db,
)


class TestContentHierarchyAndScraper(unittest.TestCase):
    """Test suite for content categories, artists, and music scraper."""

    def setUp(self):
        self.client = TestClient(app)

    def test_slugify(self):
        """Test slug generation from strings."""
        self.assertEqual(_slugify("Rhoma Irama"), "rhoma-irama")
        self.assertEqual(_slugify("Dangdut & Pop 100%"), "dangdut-pop-100")
        self.assertEqual(_slugify("   Ska Music!   "), "ska-music")
        self.assertEqual(_slugify(""), "unknown")

    @patch('main._db_conn')
    def test_get_or_create_category_existing(self, mock_db):
        """Test returning existing category ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.return_value = (1, "music", "music")

        cat_id = _get_or_create_category("music", "Music description")
        self.assertEqual(cat_id, 1)

    @patch('main._db_conn')
    def test_get_or_create_category_new(self, mock_db):
        """Test creating new category."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # First query: not found -> second query (insert): returns 2
        mock_cursor.fetchone.side_effect = [None, (2, "podcast", "podcast")]

        cat_id = _get_or_create_category("podcast", "Podcasts")
        self.assertEqual(cat_id, 2)

    @patch('main._db_conn')
    def test_get_or_create_artist(self, mock_db):
        """Test creating or retrieving artist under category."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [None, (10, "Rhoma Irama")]

        artist_id = _get_or_create_artist(category_id=1, name="Rhoma Irama")
        self.assertEqual(artist_id, 10)

    @patch('urllib.request.urlopen')
    def test_scrape_lyrics_from_lrclib(self, mock_urlopen):
        """Test lyrics scraping via LRCLIB API mock."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "plainLyrics": "Begadang jangan begadang\nKalau tiada artinya",
            "syncedLyrics": "[00:10.00] Begadang jangan begadang\n[00:15.00] Kalau tiada artinya"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        raw, lrc = _scrape_lyrics(artist="Rhoma Irama", title="Begadang")
        self.assertIn("Begadang jangan begadang", raw)
        self.assertIn("[00:10.00]", lrc)

    @patch('urllib.request.urlopen')
    def test_scrape_lyrics_resilient_on_error(self, mock_urlopen):
        """Test that lyrics scraping fails gracefully on network exception."""
        mock_urlopen.side_effect = Exception("Network timeout")

        raw, lrc = _scrape_lyrics(artist="NonExistent", title="Unknown")
        self.assertIsNone(raw)
        self.assertIsNone(lrc)

    @patch('main._scrape_lyrics')
    @patch('main.subprocess.run')
    @patch('main._db_conn')
    def test_scrape_music_content_end_to_end(self, mock_db, mock_subprocess, mock_lyrics):
        """Test end-to-end music content scraping."""
        mock_lyrics.return_value = ("Sample raw lyrics", "[00:01.00] Sample synced")
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = json.dumps({
            "id": "abc12345",
            "title": "Begadang",
            "duration": 180,
            "uploader": "Rhoma Irama"
        })

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock: 1. check category, 2. check artist, 3. check existing song (None), 4. insert song
        mock_cursor.fetchone.side_effect = [
            (1, "music", "music"),              # category
            (5, "Rhoma Irama"),                 # artist
            None,                               # existing song check
            (99, "https://youtube.com/watch?v=abc12345", "Begadang",
             "data/songs/audio/abc12345.mp3", "data/songs/video/abc12345.mp4",
             "Sample raw lyrics", "[00:01.00] Sample synced", 180, 1, 5)  # insert return
        ]

        result = _scrape_music_content(
            category="music",
            artist="Rhoma Irama",
            title="Begadang",
            youtube_url="https://youtube.com/watch?v=abc12345"
        )

        self.assertEqual(result["id"], 99)
        self.assertEqual(result["title"], "Begadang")
        self.assertEqual(result["artist_id"], 5)
        self.assertEqual(result["category_id"], 1)
        self.assertIn("audio_path", result)
        self.assertIn("video_path", result)
        self.assertIn("lyrics_raw", result)
        self.assertIn("lyrics_lrc", result)

    @patch('main._scrape_music_content')
    def test_api_content_scrape_endpoint(self, mock_scrape):
        """Test POST /content/scrape API endpoint."""
        mock_scrape.return_value = {
            "id": 101,
            "title": "Begadang",
            "category": "music",
            "artist": "Rhoma Irama",
            "audio_path": "data/songs/audio/test.mp3",
            "video_path": "data/songs/video/test.mp4",
            "lyrics_raw": "Lirik lagu",
            "lyrics_lrc": "[00:00.00] Lirik lagu",
            "duration_sec": 200
        }

        res = self.client.post("/content/scrape", json={
            "category": "music",
            "artist": "Rhoma Irama",
            "title": "Begadang",
            "youtube_url": "https://www.youtube.com/watch?v=abc12345"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], 101)
        self.assertEqual(data["artist"], "Rhoma Irama")

    def test_api_content_scrape_invalid_input(self):
        """Test POST /content/scrape validation with empty/invalid body."""
        res = self.client.post("/content/scrape", json={
            "category": "",
            "artist": "",
            "title": "",
            "youtube_url": "not-a-url"
        })
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
