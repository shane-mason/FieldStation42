#!/usr/bin/env bash
set -Eeuo pipefail

readonly STAGING_ROOT="/mnt/user/appdata/fieldstation42-hometv"
readonly APP_PATH="${STAGING_ROOT}/app"
readonly CONFS_PATH="${STAGING_ROOT}/confs"
readonly CATALOG_PATH="${STAGING_ROOT}/catalog"
readonly RUNTIME_PATH="${STAGING_ROOT}/runtime"
readonly BACKUP_ROOT="${STAGING_ROOT}/backups"
readonly COMPOSE_FILE="${APP_PATH}/docker/docker-compose.unraid-staging.yml"
readonly IMAGE="fieldstation42-hometv:staging"
readonly CONTAINER="fieldstation42-hometv"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ "$(id -u)" -eq 0 ]] || fail "Run this script as root on Unraid."
command -v docker >/dev/null || fail "Docker is required."
docker compose version >/dev/null 2>&1 || fail "The Docker Compose plugin is required."
[[ -d /mnt/user/Media ]] || fail "Media directory not found: /mnt/user/Media"
[[ -f "${APP_PATH}/LICENSE" ]] || fail "FieldStation42 repository not found at ${APP_PATH}"
[[ -f "$COMPOSE_FILE" ]] || fail "Staging Compose file not found: ${COMPOSE_FILE}"
[[ "$(realpath "$PWD")" == "$(realpath "$APP_PATH")" ]] ||
    fail "Run this script from ${APP_PATH}"

for path in "$CONFS_PATH" "$CATALOG_PATH" "$RUNTIME_PATH" "$BACKUP_ROOT"; do
    mkdir -p "$path"
done
mkdir -p "${RUNTIME_PATH}/logs"

staging_was_running=false
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
    owner="$(docker inspect --format '{{ index .Config.Labels "com.fieldstation42.deployment" }}' "$CONTAINER")"
    [[ "$owner" == "unraid-staging" ]] ||
        fail "Container ${CONTAINER} already exists and is not owned by this staging deployment."
    [[ "$(docker inspect --format '{{.State.Running}}' "$CONTAINER")" == "true" ]] &&
        staging_was_running=true
fi

export FS42_APP_PATH="$APP_PATH"
docker compose -f "$COMPOSE_FILE" config --quiet
docker compose -f "$COMPOSE_FILE" build

docker run --rm \
    --entrypoint python \
    -v "${CONFS_PATH}:/validation/confs:ro" \
    "$IMAGE" \
    /app/scripts/validate_hometv_config.py /validation/confs

if $staging_was_running; then
    docker stop "$CONTAINER" >/dev/null
    trap 'printf "Deployment failed; restarting the previous staging container.\n" >&2; docker start "$CONTAINER" >/dev/null || true' ERR
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="${BACKUP_ROOT}/${timestamp}"
mkdir -p "$backup_path"
for name in confs catalog runtime; do
    source_path="${STAGING_ROOT}/${name}"
    if find "$source_path" -mindepth 1 -print -quit | grep -q .; then
        tar \
            --exclude='*.socket' \
            --exclude='*.db-wal' \
            --exclude='*.db-shm' \
            --exclude='*.db-journal' \
            -C "$STAGING_ROOT" -cpf "${backup_path}/${name}.tar" "$name"
    fi
done
printf 'Staging backup created: %s\n' "$backup_path"

chown -R 4242:4242 "$CONFS_PATH" "$CATALOG_PATH" "$RUNTIME_PATH"
trap - ERR
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

container_id="$(docker compose -f "$COMPOSE_FILE" ps -q fieldstation42-hometv)"
[[ -n "$container_id" ]] || fail "Compose did not create the staging container."
for _ in $(seq 1 40); do
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
    case "$health" in
        healthy) break ;;
        unhealthy|exited|dead)
            docker compose -f "$COMPOSE_FILE" logs --tail=100
            fail "Staging container entered state: ${health}"
            ;;
    esac
    sleep 2
done
[[ "${health:-}" == "healthy" ]] || fail "Timed out waiting for a healthy staging container."

host_ip="${FS42_UNRAID_HOST:-$(hostname -I | awk '{print $1}')}"
host_ip="${host_ip:-UNRAID-IP}"
printf '\nDeployment healthy.\n'
printf 'Management: http://%s:4243/\n' "$host_ip"
printf 'Watch:      http://%s:4243/watch\n' "$host_ip"
