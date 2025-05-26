echo "Installing Fieldstation 42 in Docker..."

ENV_FILE=".env"
MODE="docker"

echo Finding python installation...
python=python3

if type "python3" > /dev/null; then
    echo "Found python3 - using that"
    python=python3
elif type "python" > /dev/null; then
    echo "Found python - using that"
    python=python
else
    echo ERROR :: Couldn\'t find python or python3 on the path
    echo Please install python and try again
    exit -1
fi

pip install -e .

# Create or update .env file
echo "Setting FIELDSTATION_MODE=$MODE"
if [ -f "$ENV_FILE" ]; then
  if grep -q "^FIELDSTATION_MODE=" "$ENV_FILE"; then
    sed -i "s/^FIELDSTATION_MODE=.*/FIELDSTATION_MODE=$MODE/" "$ENV_FILE"
  else
    echo "FIELDSTATION_MODE=$MODE" >> "$ENV_FILE"
  fi
else
  echo "FIELDSTATION_MODE=$MODE" > "$ENV_FILE"
fi

# Detect if WSL
if grep -qi microsoft /proc/version; then
  ENV_FILE="docker/.env.wsl"
  echo "Detected WSL — using $ENV_FILE"
else
  ENV_FILE="docker/.env.linux"
  echo "Detected native Linux — using $ENV_FILE"
fi

# Start Docker Compose with the correct env file
docker compose --env-file "$ENV_FILE" up --build -d

if [ $? -ne 0 ]; then
  echo "[ERROR] Docker Compose failed to start."
  exit 1
fi

echo "Docker containers are now running."

echo "You can now run:"
echo "  fs42 station_42 --args"
