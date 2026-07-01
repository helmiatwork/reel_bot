postgres: pg_ctl -D ./data/pg -o "-p 5432" -l ./data/pg/server.log -w start
cliproxy: ./data/bin/cli-proxy-api -config ./cliproxy/config.yaml
openclaw: openclaw gateway --port 18789
pipeline-api: bash -c "cd pipeline-api && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000"
arcreel: bash -c "cd data/arcreel && source .venv/bin/activate && uvicorn server.app:app --host 0.0.0.0 --port 1241"
