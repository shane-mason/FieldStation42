(() => {
  const video = document.querySelector("#video");
  const channelSelect = document.querySelector("#channels");
  const message = document.querySelector("#message");
  const progress = document.querySelector("#progress span");
  let channels = [], sessionId = null, hls = null, nowInfo = null;
  let recoveryTimer = null, controlsTimer = null, heartbeat = null, boundaryTimer = null;
  let isTuning = false, startupBuffering = false, tuneAbort = null;
  const STARTUP_TIMEOUT_SECONDS =
    Number(window.HOMETV_STARTUP_TIMEOUT_SECONDS || 30);

  const showControls = () => {
    document.body.classList.add("active");
    clearTimeout(controlsTimer);
    controlsTimer = setTimeout(() => document.body.classList.remove("active"), 4000);
  };

  async function api(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${response.status})`);
    }
    return response.status === 204 ? null : response.json();
  }

  async function stopSession() {
    clearInterval(heartbeat);
    clearTimeout(boundaryTimer);
    if (hls) { hls.destroy(); hls = null; }
    startupBuffering = false;
    video.pause();
    video.removeAttribute("src");
    if (sessionId) {
      const old = sessionId; sessionId = null;
      await fetch(
        `/api/watch/sessions/${old}`,
        {method: "DELETE", keepalive: true}
      ).catch(() => {});
    }
  }

  function bufferedAhead() {
    const current = video.currentTime;
    for (let index = 0; index < video.buffered.length; index += 1) {
      const start = video.buffered.start(index);
      const end = video.buffered.end(index);
      if (start <= current + 0.5 && end > current) return end - current;
    }
    return 0;
  }

  function waitForInitialBuffer(channelName, target, signal, getFailure) {
    startupBuffering = true;
    video.pause();
    const started = performance.now();
    return new Promise((resolve, reject) => {
      const check = () => {
        if (signal.aborted) {
          startupBuffering = false;
          reject(new DOMException("Tuning cancelled", "AbortError"));
          return;
        }
        const failure = getFailure();
        if (failure) {
          startupBuffering = false;
          reject(failure);
          return;
        }
        const available = bufferedAhead();
        message.textContent =
          `Buffering ${channelName}: ${available.toFixed(1)} / ${target.toFixed(1)} seconds`;
        if (available >= target) {
          startupBuffering = false;
          resolve();
          return;
        }
        if (performance.now() - started >= STARTUP_TIMEOUT_SECONDS * 1000) {
          startupBuffering = false;
          reject(new Error(`Startup buffering timed out after ${STARTUP_TIMEOUT_SECONDS} seconds`));
          return;
        }
        setTimeout(check, 200);
      };
      check();
    });
  }

  async function attach(url, channelName, bufferSeconds, signal) {
    let streamFailure = null;
    // Chromium may report "maybe" for native HLS while failing to decode an
    // MPEG-TS playlist. Prefer HLS.js wherever Media Source is available and
    // reserve native HLS for Safari and other browsers without MSE support.
    if (window.Hls && Hls.isSupported()) {
      hls = new Hls({liveSyncDurationCount: 3, maxLiveSyncPlaybackRate: 1.25});
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) {
          streamFailure = new Error(
            `HLS startup failed: ${data.details || data.type}`
          );
          console.error("Fatal HLS playback error", {
            type: data.type,
            details: data.details,
            error: data.error?.message || String(data.error || "")
          });
          recover();
        }
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url;
      video.load();
    } else {
      throw new Error("This browser has no HLS playback support");
    }
    await waitForInitialBuffer(
      channelName,
      bufferSeconds,
      signal,
      () => streamFailure
    );
    await video.play();
  }

  async function tune(channel) {
    if (tuneAbort) tuneAbort.abort();
    tuneAbort = new AbortController();
    const signal = tuneAbort.signal;
    isTuning = true;
    clearTimeout(recoveryTimer);
    message.textContent = "Tuning…";
    await stopSession();
    try {
      const result = await api("/api/watch/sessions", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({channel: String(channel), profile: "auto"}),
        signal
      });
      sessionId = result.session_id;
      nowInfo = result.now;
      renderNow();
      await attach(
        result.playlist_url,
        nowInfo.channel_name,
        Number(result.initial_buffer_seconds),
        signal
      );
      const boundaryDelay = Date.parse(nowInfo.item_end) - Date.now() + 250;
      boundaryTimer = setTimeout(
        () => tune(channelSelect.value),
        Math.max(250, boundaryDelay)
      );
      heartbeat = setInterval(() => {
        if (sessionId) fetch(`/api/watch/sessions/${sessionId}/heartbeat`, {method: "POST"});
      }, 20000);
      message.textContent = "";
      localStorage.setItem("fs42-channel", String(channel));
    } catch (error) {
      if (error.name === "AbortError") return;
      console.error("HomeTV startup failed", error);
      message.textContent = error.message;
      isTuning = false;
      recover(true);
      return;
    }
    isTuning = false;
  }

  function recover(force = false) {
    if (isTuning || startupBuffering || (!sessionId && !force)) return;
    if (recoveryTimer) return;
    message.textContent = "Playback interrupted — reconnecting…";
    recoveryTimer = setTimeout(() => {
      recoveryTimer = null;
      if (channelSelect.value) tune(channelSelect.value);
    }, 3000);
  }

  function renderNow() {
    if (!nowInfo) return;
    document.querySelector("#channel-number").textContent = nowInfo.channel_number;
    document.querySelector("#channel-name").textContent = nowInfo.channel_name;
    document.querySelector("#program-title").textContent = nowInfo.program_title;
  }

  async function refreshNow() {
    if (!channelSelect.value) return;
    try {
      const previousEnd = nowInfo?.end;
      nowInfo = await api(`/api/watch/channels/${encodeURIComponent(channelSelect.value)}/now`);
      renderNow();
      if (previousEnd && previousEnd !== nowInfo.end) tune(channelSelect.value);
    } catch (_) {}
  }

  function adjacent(delta) {
    const index = Math.max(0, channels.findIndex(c => c.channel_number === channelSelect.value));
    const next = channels[(index + delta + channels.length) % channels.length];
    if (next) { channelSelect.value = next.channel_number; tune(next.channel_number); }
  }

  async function start() {
    try {
      channels = (await api("/api/watch/channels")).channels;
      channelSelect.innerHTML = channels.map(c =>
        `<option value="${c.channel_number}">${c.channel_number} — ${c.channel_name}</option>`
      ).join("");
      const saved = localStorage.getItem("fs42-channel");
      if (saved && channels.some(c => c.channel_number === saved)) channelSelect.value = saved;
      if (!channelSelect.value && channels[0]) channelSelect.value = channels[0].channel_number;
      if (!channelSelect.value) throw new Error("No scheduled channels are configured");
      await tune(channelSelect.value);
    } catch (error) {
      message.textContent = error.message;
      setTimeout(start, 5000);
    }
  }

  channelSelect.addEventListener("change", () => tune(channelSelect.value));
  document.querySelector("#previous").onclick = () => adjacent(-1);
  document.querySelector("#next").onclick = () => adjacent(1);
  document.querySelector("#mute").onclick = () => {
    video.muted = !video.muted;
    document.querySelector("#mute").textContent = video.muted ? "🔇" : "🔊";
  };
  document.querySelector("#volume").oninput = event => video.volume = event.target.value;
  document.querySelector("#fullscreen").onclick = () => document.querySelector("#viewer").requestFullscreen();
  document.querySelector("#guide-button").onclick = () => document.querySelector("#guide").hidden = false;
  document.querySelector("#guide-close").onclick = () => document.querySelector("#guide").hidden = true;
  document.addEventListener("mousemove", showControls);
  document.addEventListener("click", showControls);
  document.addEventListener("keydown", event => {
    showControls();
    if (event.key === "ArrowUp" || event.key === "ArrowRight") adjacent(1);
    if (event.key === "ArrowDown" || event.key === "ArrowLeft") adjacent(-1);
    if (event.key.toLowerCase() === "m") document.querySelector("#mute").click();
    if (event.key.toLowerCase() === "f") document.querySelector("#fullscreen").click();
    if (event.key.toLowerCase() === "g") document.querySelector("#guide-button").click();
  });
  video.addEventListener("error", () => {
    console.error("Video element error", {
      code: video.error?.code,
      message: video.error?.message
    });
    recover();
  });
  video.addEventListener("waiting", recover);
  video.addEventListener("stalled", recover);
  window.addEventListener("beforeunload", stopSession);
  setInterval(() => {
    if (nowInfo) {
      const elapsed = (Date.now() - Date.parse(nowInfo.server_time)) / 1000 + nowInfo.elapsed;
      progress.style.width = `${Math.min(100, 100 * elapsed / nowInfo.duration)}%`;
    }
  }, 1000);
  setInterval(refreshNow, 15000);
  showControls();
  start();
})();
