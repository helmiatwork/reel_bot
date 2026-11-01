import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yt_pipeline  # noqa: E402


def test_prefers_binary_beside_interpreter(tmp_path):
    exe = tmp_path / "python"
    (tmp_path / "yt-dlp").write_text("")
    with patch.object(sys, "executable", str(exe)):
        assert yt_pipeline.ytdlp_bin() == str(tmp_path / "yt-dlp")


def test_falls_back_to_path_lookup(tmp_path):
    with patch.object(sys, "executable", str(tmp_path / "python")), \
         patch("shutil.which", return_value="/usr/local/bin/yt-dlp"):
        assert yt_pipeline.ytdlp_bin() == "/usr/local/bin/yt-dlp"
