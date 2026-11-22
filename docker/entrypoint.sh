#!/bin/bash
# confs/ is a mounted volume, so the api key can only be set up once the container is running
cd /app
python3 -m fs42.api_key_setup --non-interactive
exec "$@"
