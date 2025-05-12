let entryBuffer = "";
let entryTimer = null;

function sendCommand(cmd) {
  fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: cmd, channel: -1 })
  }).then(res => res.json())
    .then(data => {
      console.log("Sent:", cmd, data);
      updateStatusDisplay(data.current);
    });
}

function appendDigit(n) {
  if (entryBuffer.length >= 2) entryBuffer = "";
  entryBuffer += n.toString();
  document.getElementById("entry").innerText = entryBuffer;

  if (entryTimer) clearTimeout(entryTimer);
  entryTimer = setTimeout(() => sendDirect(false), 1500);
}

function clearEntry() {
  entryBuffer = "";
  document.getElementById("entry").innerText = "_";
  if (entryTimer) clearTimeout(entryTimer);
}

function sendDirect(force) {
    const chan = parseInt(entryBuffer, 10);
    if (!isNaN(chan)) {
    fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "direct", channel: chan })
    }).then(() => {
        console.log("Sent direct", chan);
        updateStatus();
    });
    }
    if (force || entryBuffer.length > 0) clearEntry();
}

function updateStatusDisplay(data) {    
    if (data.channel != null && data.channel >= 1) {
    document.getElementById("current-channel").innerText = data.channel.toString().padStart(2, "0");
    } else {
    document.getElementById("current-channel").innerText = "--";
    }

    document.getElementById("network-name").innerText = data.name || "";
}

function updateStatus() {
    fetch("/api/status").then(r => r.json()).then(updateStatusDisplay);
}

setInterval(updateStatus, 2000);
updateStatus();
