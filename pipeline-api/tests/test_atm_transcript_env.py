import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

OUT = MagicMock(returncode=0, stdout=json.dumps({"segments": [{"start": 0, "end": 1, "text": "hi"}]}))


def _run(scrape):
    with patch.dict(os.environ, {}, clear=False), patch("main._scrape_cookie_file", return_value=scrape) as sc, \
            patch("subprocess.run", return_value=OUT) as run:
        os.environ.pop("YTDLP_COOKIES_FILE", None)
        segs = main._fetch_transcript("https://www.youtube.com/watch?v=abc")
    sc.assert_called_once_with("youtube")
    return segs, run.call_args.kwargs["env"]


def test_transcript_uses_scrape_cookie_file():
    segs, env = _run(Path("/tmp/scrape_cookies.txt"))
    assert segs and env["YTDLP_COOKIES_FILE"] == "/tmp/scrape_cookies.txt"


def test_transcript_without_scrape_cookie_sets_nothing():
    _, env = _run(None)
    assert "YTDLP_COOKIES_FILE" not in env
