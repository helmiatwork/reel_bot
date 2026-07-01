#!/bin/bash
cd "$(dirname "$0")" && cd data/arcreel && source .venv/bin/activate && exec uvicorn server.app:app --host 0.0.0.0 --port 1241
