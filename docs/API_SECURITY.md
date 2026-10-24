# API Security (api_key)

FieldStation42 runs a web server (port 4242 by default) for the web console and for scripts that control the player.
Without protection, anyone who can reach that port can use every endpoint, including the ones that list folders on disk and change station configuration.

Setting an `api_key` adds a first line of defense against scanners and unwanted calls on your network.

> **FieldStation42 should never be exposed to the open internet.** Don't port-forward 4242. The key is sent unencrypted over your network, so this is basic protection, not real security.

## Turning it on or off

The key lives in `confs/main_config.json`:

```json
{
  "api_key": "pick-something-long-and-random"
}
```

- **On:** `api_key` is set to a non-empty value.
- **Off:** no `api_key`, or `"api_key": ""`. Everything works as it did before this feature, and the server logs a warning at startup.
- **Restart FieldStation42** after changing the key. `main_config.json` is only read at startup.
- Any string works, but a short key is easy to guess and the server warns about keys under 12 characters. To generate a good one:

  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(16))"
  ```

### New installs

The installer turns security on for a new install. It writes a random key to `confs/main_config.json` and prints it at the end. To opt out, remove `api_key` from that file and restart.

### Existing installs

Nothing changes until you opt in. Either:
- add `api_key` to `confs/main_config.json` yourself and restart, or
- rerun `bash install.sh` and answer **yes** to "Enable API security?". The installer rewrites `main_config.json` with the new key. Your other settings are kept, but its formatting may change.

Before turning it on, update any scripts or integrations that call the API (see below).

### Docker

When the container starts, it checks the mounted `confs/` folder. A new, empty config folder gets a random key, and the key is printed in the container logs (`docker logs fieldstation42`). An existing config folder is left alone; opt in by adding `api_key` to `main_config.json`.

## The web console

With security on, the web console asks for the key once per browser or device and then remembers it for a year. Changing the key logs every device out.

For a bookmark, a phone home-screen shortcut or a QR code, this URL logs in with one tap:

```
http://<your-fs42-box>:4242/login?api_key=YOUR_KEY
```

A browser in kiosk mode that shows a page directly, such as a custom guide on a second screen, can add the key to that page's URL:

```
http://<your-fs42-box>:4242/static/customguide/customguide.html?api_key=YOUR_KEY
```

## Scripts and integrations

Every request must carry the key, in any one of these three ways:

| Method | Example |
|--------|---------|
| URL parameter | `http://fs42:4242/player/channels/up?api_key=YOUR_KEY` |
| `X-API-Key` header | `X-API-Key: YOUR_KEY` |
| Bearer token | `Authorization: Bearer YOUR_KEY` |

Requests without a valid key get `401 {"detail": "api key required"}`.

```bash
curl -H "X-API-Key: YOUR_KEY" http://fs42:4242/player/status
curl "http://fs42:4242/player/channels/up?api_key=YOUR_KEY"
```

Home Assistant `rest_command`:

```yaml
rest_command:
  fs42_channel_up:
    url: "http://fs42:4242/player/channels/up"
    method: get
    headers:
      X-API-Key: !secret fs42_api_key
```

Keys in URL parameters are masked (`api_key=***`) in FieldStation42's access log, but other tools along the way may log them. Prefer a header where you can.

## FieldStation42's own components

These pick up the key automatically, with nothing to configure:
- The web renderer, which handles web channels, the custom guide, autobumps, PPV and diagnostics. It sends the key only to the local FieldStation42 server, never to third-party sites in a web channel.
- `fs42/pi/remote_controller.py` reads the key from `confs/main_config.json`. If it runs on another machine, set `FS42_API_KEY`.

One caveat: a web channel whose `web_url` points at the box's own LAN address (e.g. `http://192.168.1.20:4242/...`) won't get the key. Use `http://localhost:4242/...` for pages served by FieldStation42 itself.

## Managing the server (requires a key)

The **Manage** page in the web console (formerly About) can restart FieldStation42, stop it, and update it from git. These controls only work when `api_key` is set. Without a key, the `/manage` actions are refused with a `403`, whether you use the page or call the API.

- **Restart** restarts every running `fs42*` systemd user service. It needs FieldStation42 to be [running as a service](../install/systemd/README.md). When it's started from a terminal, Restart is disabled.
- **Stop** stops those services, or the player if it isn't running as a service. The web console stops with it, and can't start FieldStation42 again.
- **Check for Updates** fetches from git and lists the new commits on your branch.
- **Update Now** runs `git pull --ff-only`. It never merges, stashes, or resets. If git can't fast-forward, for example because you have local edits to files the update changes, or your branch has its own commits, nothing is changed. The page shows what git said. Nothing restarts automatically after an update, so restart when you're ready. If `requirements.txt` changed, run `bash install.sh` first.

Update is not available in Docker. To update a container, rebuild the image.

## Other changes

`/media/json` no longer serves `confs/main_config.json`, whether security is on or off, because that file holds the key and other secrets. Other JSON files are served as before.

## Lost your key?

Open `confs/main_config.json` on the FieldStation42 machine and read the `api_key` value.
