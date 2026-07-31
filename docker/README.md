# Running FS42 as a Docker Container

This uses a docker-compose file with mounts for catalog, runtime, and confs so the data persists across containers.

## Status

This is a brand new feature and experimental. Please test, and if you find issues, post a ticket on GitHub.

## Instructions
### Required:
Linux or WSL environment
- If you're using Windows, you will need to both run docker in WSL, as well as run any executables inside the container (field_player.py or station_42.py) from a WSL environment.
	- This is because WSLg is needed for forwarding the GUI components.

Docker

### Installation
- Repo must be cloned and you must be in the root

Create a file named `.env` in the root of the project.

```sh
# EXTRA_MOUNT is only needed if you have a separate directory where your symlinks are pointing to. If you don't have one, just delete this variable.
EXTRA_MOUNT=/mnt/d/Media/TV:/mnt/d/Media/TV

# This should be set to "docker"
RUN_MODE=docker

# This should be set to "wsl" if you are using WSL, and "linux" if you are using linux.
OS_ENV=wsl
```

Build the container:

```sh
make docker-build
```

To start the container:
```sh
make docker-up
```

We have wrapper commands to open field_player and station_42 in docker:

```sh
make station_42
```

```sh
make field_player
```

Those commands will bring the container up and down on the fly (which should be fine since the data is mounted and thus persistent) but if you want to keep it up, you can type `make docker-up` and it will bring the container up.

To bring the container down:
```sh
make docker-down
```

When there is a change to fieldstation42, you will likely need to rerun the build command to get the changes in your container.

The "catalog", "confs", and "runtime" folders are all mounted so that their data will persist across runs of this container.

For symlinks:
- You will need to mount the folder that your symlinks point to.
- In your `.env` file, ensure EXTRA_MOUNT is set.
	- Ex: You have all your media under /home/user/Media
		- You will add this like:
		- `EXTRA_MOUNT=/home/user/Media:/home/user/Media`

### Advanced Usage

If your environment differs from the defaults for either WSL or Linux, you can put any of the environment variables that the Makefile uses in your `.env` file, and it will use it by default (ensure you've re-sourced it)
- That includes the catalog, runtime, and confs locations.
- Look inside the Makefile to the environment variables you can use.

#### Aliases

It can be helpful to run fs42 from anywhere on your file system. For this, you can add something like this to your `.bashrc` to do so:

```sh
FS42_LOCATION="/home/user/repos/FieldStation42"

station_42() {
    make -C $FS42_LOCATION station_42 "$@"
}

field_player() {
    make -C $FS42_LOCATION field_player "$@"
}
```

This way, you can run `station_42` or `field_player` anywhere to launch them. (the location for FS42_LOCATION would likely need to change on your machine)
# Headless Home TV / Unraid

The production Home TV deployment uses `Dockerfile.hometv` and
`docker-compose.hometv.yml`. These intentionally contain no MPV, X11, local
display, PulseAudio, or host audio mounts. The older Compose configuration
below remains available for legacy local MPV playback.

Copy the environment template and edit its host paths:

```bash
cp docker/hometv.env.example docker/.env
docker compose --env-file docker/.env \
  -f docker/docker-compose.hometv.yml up -d --build
```

The media share is mounted read-only at `/media`. Configure channel content
paths using that container path. Configuration, catalog data, runtime SQLite
and HLS cache, and logs have distinct persistent mounts. Do not point these at
live data while testing a development image; copy the directories first.

Open:

- Management console: `http://UNRAID-IP:4242/`
- Watch page: `http://UNRAID-IP:4242/watch`
- Remote: `http://UNRAID-IP:4242/remote`
- Health check: `http://UNRAID-IP:4242/health`

Useful environment settings include `FS42_PORT`,
`FS42_HLS_IDLE_SECONDS`, and `FS42_HLS_MAX_SESSIONS`. Container logs are
available through `docker compose logs`; application logs also persist in the
configured logs directory.

## Isolated Unraid staging deployment

The staging deployment is deliberately separate from an existing
FieldStation42 installation:

- Repository: `/mnt/user/appdata/fieldstation42-hometv/app`
- Configuration: `/mnt/user/appdata/fieldstation42-hometv/confs`
- Catalog: `/mnt/user/appdata/fieldstation42-hometv/catalog`
- Runtime/database/HLS/logs: `/mnt/user/appdata/fieldstation42-hometv/runtime`
- Media: `/mnt/user/Media`, mounted read-only
- Container: `fieldstation42-hometv`
- Host port: `4243` (container port `4242`)

It uses normal bridge networking and has no X11, PulseAudio, or host-audio
mounts.

From the staging repository on Unraid:

```bash
cd /mnt/user/appdata/fieldstation42-hometv/app
sudo ./migrate-test-state.sh \
  --source /mnt/user/appdata/YOUR-EXISTING-FIELDSTATION42
sudo ./deploy-unraid.sh
```

The migration command takes an explicit source so it cannot guess and copy
from the wrong installation. It searches validated station JSON for the exact
network name `Toon Mix`, copies only matching JSON files, and does not read or
copy runtime databases, socket files, or SQLite journal/WAL files. Existing
staging configuration is backed up first. Source configuration is never
modified.

`deploy-unraid.sh`:

1. verifies it is running from the required repository;
2. refuses to replace a container not labeled as this staging deployment;
3. validates the Compose model and builds the staging image;
4. validates all staged JSON against the FieldStation42 station schema;
5. gracefully stops only a prior staging container, if present;
6. backs up staging configuration, catalog, and runtime while excluding
   sockets and active SQLite journal files;
7. assigns the staging directories to the image's unprivileged UID `4242`;
8. starts only the staging Compose project and waits for its health check.

After success it prints:

- `http://UNRAID-IP:4243/`
- `http://UNRAID-IP:4243/watch`

Set `FS42_UNRAID_HOST` when the server's preferred LAN address is not the first
address returned by `hostname -I`.

## Legacy local-player container
