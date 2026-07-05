"""Unit tests for songs extraction and storage."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import sys

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from main import _extract_audio, _save_song, _songs_init_db


class TestSongsExtraction(unittest.TestCase):
    """Test audio extraction from YouTube videos."""

    @patch('main._db_conn')
    @patch('main.subprocess.run')
    @patch('main._extract_video_id_from_youtube_url')
    def test_save_song_check_and_skip_exists(self, mock_extract_id, mock_subprocess, mock_db):
        """Test that _save_song skips if song already exists."""
        mock_extract_id.return_value = "test_id"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Song already exists
        mock_cursor.fetchone.return_value = (1,)

        _save_song("https://youtube.com/watch?v=test")

        # Verify we only checked existence, didn't extract or insert
        mock_cursor.execute.assert_called_once()
        mock_subprocess.run.assert_not_called()

    @patch('main._db_conn')
    @patch('main.subprocess.run')
    @patch('main._extract_video_id_from_youtube_url')
    @patch('main._fetch_channel_meta')
    def test_save_song_new_song(self, mock_meta, mock_extract_id, mock_subprocess, mock_db):
        """Test that _save_song extracts and inserts new song."""
        mock_extract_id.return_value = "new_id"
        mock_meta.return_value = {"title": "Test Video"}
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Song doesn't exist
        mock_cursor.fetchone.side_effect = [None, None]  # Check query returns None
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        with patch('main.Path.exists', return_value=True):
            with patch('main._extract_audio') as mock_extract:
                mock_extract.return_value = {
                    "audio_path": "/path/to/new_id.mp3",
                    "title": "Test Video",
                    "duration_sec": 60
                }
                _save_song("https://youtube.com/watch?v=new")

                # Verify extraction was called
                mock_extract.assert_called_once()

                # Verify insert was called
                calls = mock_cursor.execute.call_args_list
                # Should have: SELECT query, then INSERT query
                self.assertGreaterEqual(len(calls), 2)

    @patch('main._db_conn')
    def test_save_song_non_fatal_on_db_none(self, mock_db):
        """Test that _save_song is non-fatal when DB is None."""
        mock_db.return_value = None
        # Should not raise
        _save_song("https://youtube.com/watch?v=test")

    @patch('main.subprocess.run')
    @patch('main._extract_video_id_from_youtube_url')
    @patch('main._fetch_channel_meta')
    def test_extract_audio_returns_empty_on_ytdlp_failure(self, mock_meta, mock_extract_id, mock_subprocess):
        """Test that _extract_audio returns {} on yt-dlp failure."""
        mock_extract_id.return_value = "test_id"
        mock_meta.return_value = {"title": "Test"}

        # First call (check if exists) returns False, second call (yt-dlp) fails
        def subprocess_side_effect(*args, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stderr = "Error"
            return result

        mock_subprocess.run.side_effect = subprocess_side_effect

        with patch('main.Path.exists', return_value=False):
            result = _extract_audio("https://youtube.com/watch?v=test")

            # Should return empty dict on error
            self.assertEqual(result, {})

    @patch('main._db_conn')
    def test_songs_init_db_creates_table(self, mock_db):
        """Test that _songs_init_db creates the songs table."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        _songs_init_db()

        # Verify CREATE TABLE was called
        calls = mock_cursor.execute.call_args_list
        self.assertGreaterEqual(len(calls), 2)
        # First call should be CREATE TABLE
        first_call_sql = calls[0][0][0]
        self.assertIn("CREATE TABLE IF NOT EXISTS songs", first_call_sql)

    @patch('main._db_conn')
    def test_songs_init_db_non_fatal_on_failure(self, mock_db):
        """Test that _songs_init_db is non-fatal on DB error."""
        mock_db.return_value = None
        # Should not raise
        _songs_init_db()


if __name__ == '__main__':
    unittest.main()
