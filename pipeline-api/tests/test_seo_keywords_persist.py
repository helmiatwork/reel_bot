"""SEO analyze persists its keywords into the keywords table, which ATM blueprints read by niche."""
import sys
from pathlib import Path
from unittest.mock import call, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app, _seo_trends  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
AUTO = ["kucing lucu", "kucing oren"]
TRENDS = {"related_top": [{"query": "kucing hitam", "value": 80}],
          "related_rising": [{"query": "kucing viral", "value": 5000}],
          "interest": []}


class _DownConn(FakeConn):
    def cursor(self):
        raise RuntimeError("connection lost")


def _analyze(conn, body, auto=AUTO, trends=TRENDS):
    with patch("main._seo_autocomplete", return_value=auto) as ac, \
            patch("main._seo_trends", return_value=trends) as tr, \
            patch("main._seo_synthesize", return_value={}), \
            patch("main._db_conn", return_value=conn):
        r = client.post("/seo/analyze", json=body)
    return r, {"autocomplete": ac, "trends": tr}


def _inserted(conn):
    """{(keyword, source): (seed, region, niche, score)} from the INSERT params (order: keyword, seed, source, region, niche, score, raw)."""
    return {(p[0], p[2]): (p[1], p[3], p[4], p[5]) for _, p in conn.sqls("INSERT INTO keywords")}


def test_analyze_persists_autocomplete_and_trends_rows_with_scores():
    conn = FakeConn()
    r, m = _analyze(conn, {"topic": "Kucing", "platform": "youtube", "niche": "kucing"})
    assert m["trends"].call_args == call("Kucing", "youtube")
    assert r.status_code == 200
    assert _inserted(conn) == {
        ("kucing lucu", "yt_autocomplete"): ("Kucing", "global", "kucing", 60),
        ("kucing oren", "yt_autocomplete"): ("Kucing", "global", "kucing", 58),
        ("kucing hitam", "trends_top"): ("Kucing", "global", "kucing", 80),
        ("kucing viral", "trends_rising"): ("Kucing", "global", "kucing", 100),
    }
    assert conn.sqls("ON CONFLICT (keyword, region, source) DO UPDATE SET seed = EXCLUDED.seed, niche = EXCLUDED.niche, "
                     "score = EXCLUDED.score, raw = EXCLUDED.raw, fetched_at = now()")
    assert conn.commits == 1 and conn.closed


def test_autocomplete_source_is_google_off_youtube_and_niche_defaults_to_topic():
    conn = FakeConn()
    r, _ = _analyze(conn, {"topic": "  Kucing Lucu ", "platform": "tiktok"}, auto=["kucing tiktok"], trends={})
    assert r.status_code == 200
    assert _inserted(conn) == {("kucing tiktok", "google_autocomplete"): ("Kucing Lucu", "global", "kucing lucu", 60)}


def test_autocomplete_score_has_floor_of_ten():
    conn = FakeConn()
    many = [f"kucing {i}" for i in range(30)]
    _analyze(conn, {"topic": "kucing", "platform": "youtube", "niche": "kucing"}, auto=many, trends={})
    scores = {k[0]: v[3] for k, v in _inserted(conn).items()}
    assert scores["kucing 0"] == 60 and scores["kucing 25"] == 10 and scores["kucing 29"] == 10


def test_db_failure_still_returns_200_with_keywords():
    r, _ = _analyze(_DownConn(), {"topic": "kucing", "niche": "kucing"})
    assert r.status_code == 200
    assert [k["term"] for k in r.json()["keywords"]][:2] == AUTO


def test_failed_rollback_is_also_non_fatal():
    class _DeadConn(_DownConn):
        def rollback(self):
            raise RuntimeError("socket closed")
    r, _ = _analyze(_DeadConn(), {"topic": "kucing", "niche": "kucing"})
    assert r.status_code == 200 and r.json()["keywords"]


def test_no_database_skips_persist_and_returns_200():
    r, _ = _analyze(None, {"topic": "kucing", "niche": "kucing"})
    assert r.status_code == 200 and r.json()["keywords"]


@patch("pytrends.request.TrendReq")
def test_trends_uses_youtube_gprop_on_youtube(cls):
    cls.return_value.related_queries.return_value = {}
    _seo_trends("kucing", "youtube")
    cls.return_value.build_payload.assert_called_once_with(["kucing"], timeframe="today 3-m", gprop="youtube")


@patch("pytrends.request.TrendReq")
def test_trends_keeps_web_payload_on_other_platforms(cls):
    cls.return_value.related_queries.return_value = {}
    _seo_trends("kucing", "tiktok")
    cls.return_value.build_payload.assert_called_once_with(["kucing"], timeframe="today 3-m")
