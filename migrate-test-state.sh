#!/usr/bin/env bash
set -Eeuo pipefail

readonly STAGING_ROOT="${FS42_STAGING_ROOT:-/mnt/user/appdata/fieldstation42-hometv}"
readonly TARGET_CONFS="${STAGING_ROOT}/confs"
readonly BACKUP_ROOT="${STAGING_ROOT}/backups"
readonly NETWORK_NAME="Toon Mix"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly VALIDATOR="${SCRIPT_DIR}/scripts/validate_hometv_config.py"
readonly SCHEMA="${SCRIPT_DIR}/fs42/station_config_schema.json"
readonly UNRAID_STAGING_ROOT="/mnt/user/appdata/fieldstation42-hometv"

usage() {
    printf 'Usage: %s --source /path/to/existing/FieldStation42-or-confs\n' "$0"
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

source_arg=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            [[ $# -ge 2 ]] || fail "--source requires a path."
            source_arg="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done
[[ -n "$source_arg" ]] || { usage; fail "An explicit source is required."; }
[[ -d "$source_arg" ]] || fail "Source does not exist: ${source_arg}"
if [[ "$STAGING_ROOT" != "$UNRAID_STAGING_ROOT" &&
      "${FS42_ALLOW_TEST_PATHS:-}" != "1" ]]; then
    fail "Refusing non-staging target: ${STAGING_ROOT}"
fi

source_confs="$source_arg"
[[ -d "${source_arg}/confs" ]] && source_confs="${source_arg}/confs"
[[ "$(realpath "$source_confs")" != "$(realpath -m "$TARGET_CONFS")" ]] ||
    fail "Source and staging configuration directories must be different."
case "$(realpath "$source_confs")/" in
    "$(realpath -m "$STAGING_ROOT")/"*) fail "Source must not be inside staging state." ;;
esac

command -v python3 >/dev/null ||
    fail "python3 is required for read-only JSON/schema validation."
mkdir -p "$TARGET_CONFS" "$BACKUP_ROOT"

mapfile -t matches < <(
    python3 "$VALIDATOR" \
        "$source_confs" --schema "$SCHEMA" --find-network "$NETWORK_NAME"
)
[[ ${#matches[@]} -gt 0 ]] || fail "No valid ${NETWORK_NAME} configuration was found."

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="${BACKUP_ROOT}/${timestamp}-before-toon-mix-migration"
mkdir -p "$backup_path"
if find "$TARGET_CONFS" -mindepth 1 -print -quit | grep -q .; then
    tar \
        --exclude='*.socket' \
        --exclude='*.db-wal' \
        --exclude='*.db-shm' \
        --exclude='*.db-journal' \
        -C "$TARGET_CONFS" -cpf "${backup_path}/confs.tar" .
fi

for filename in "${matches[@]}"; do
    [[ "$filename" != *"/"* && "$filename" == *.json ]] ||
        fail "Validator returned an unsafe filename: ${filename}"
    source_file="${source_confs}/${filename}"
    target_file="${TARGET_CONFS}/${filename}"
    if [[ -e "$target_file" ]]; then
        cp -a "$target_file" "${backup_path}/${filename}"
    fi
    cp -p "$source_file" "$target_file"
    printf 'Copied %s -> %s\n' "$source_file" "$target_file"
done

python3 "$VALIDATOR" "$TARGET_CONFS" --schema "$SCHEMA"
printf 'Migration complete. Source data was not modified.\n'
printf 'Backup: %s\n' "$backup_path"
