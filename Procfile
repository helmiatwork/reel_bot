postgres: pg_ctl -D ./data/pg -o "-p 5432" -l ./data/pg/server.log start
cliproxy: ./data/bin/cli-proxy-api -config ./cliproxy/config.yaml
openclaw: openclaw gateway --port 18789
pipeline-api: uv run --project pipeline-api uvicorn main:app --host 0.0.0.0 --port 8000
arcreel: uv run --project data/arcreel uvicorn server.main:app --host 0.0.0.0 --port 1241
n8n: n8n start
