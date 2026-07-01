#!/bin/bash
cd "$(dirname "$0")" && exec ./data/bin/cli-proxy-api -config ./cliproxy/config.yaml
