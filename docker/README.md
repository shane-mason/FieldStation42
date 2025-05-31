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
