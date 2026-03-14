const params = new URLSearchParams(window.location.search);
const THEME = params.get('theme') || '80s';
const SLOT_COUNT = parseInt(params.get('slots')) || 3;
const HEADER_TEXT = params.get('header') || 'TV Guide';
const PAUSE_OVERRIDE = params.get('pause');

let stations = [];
let scrollInterval = null;
let musicPlaylist = [];
let currentMusicIndex = 0;
let bgPlayer = null;

function loadTheme(name) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'themes/' + name + '.css';
  link.addEventListener('error', function () {
    console.warn('theme "' + name + '" not found, falling back to 80s.');
    if (name !== '80s') loadTheme('80s');
  });
  document.head.insertBefore(link, document.head.firstChild);
}

function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function formatTime12(date) {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function formatDateForAPI(date) {
  const y = date.getFullYear();
  const mo = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const mi = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${y}-${mo}-${d}T${h}:${mi}:${s}`;
}

function getPauseDuration() {
  if (PAUSE_OVERRIDE) return parseFloat(PAUSE_OVERRIDE) * 1000;
  const match = getCSSVar('--scroll-pause').match(/([\d.]+)\s*s/);
  return match ? parseFloat(match[1]) * 1000 : 5000;
}

function getScrollSpeed() {
  const val = parseFloat(getCSSVar('--scroll-speed'));
  return (!isNaN(val) && val > 0) ? val : 0.8;
}

function computeSlotTimes() {
  const now = new Date();
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate(),
    now.getHours(), Math.floor(now.getMinutes() / 30) * 30, 0, 0);
  const slots = [];
  for (let i = 0; i < SLOT_COUNT; i++) {
    const start = new Date(base.getTime() + i * 30 * 60 * 1000);
    slots.push({ start, end: new Date(start.getTime() + 30 * 60 * 1000) });
  }
  return slots;
}

async function fetchStations() {
  const all = await window.fs42Common.fetchStationSummary();
  stations = all.filter(s => !s.hidden);
  stations.forEach(s => {
    s.has_schedule = s.schedule_summary &&
      s.schedule_summary.start !== 0 &&
      s.schedule_summary.end !== 0;
  });
}

async function fetchAllSchedules(slots) {
  if (!stations.length) return {};

  const overallStart = new Date(slots[0].start.getTime() - 3 * 60 * 60 * 1000);
  const overallEnd = slots[slots.length - 1].end;
  const schedules = {};

  for (const station of stations) {
    if (!station.has_schedule) {
      schedules[station.network_name] = [];
      continue;
    }
    try {
      const blocks = await window.fs42Common.fetchSchedule(
        station.network_name,
        formatDateForAPI(overallStart),
        formatDateForAPI(overallEnd)
      );
      schedules[station.network_name] = blocks || [];
    } catch (e) {
      console.error('error fetching schedule for', station.network_name, e);
      schedules[station.network_name] = [];
    }
  }
  return schedules;
}

function findBlockForSlot(blocks, slotStart) {
  for (const block of blocks) {
    const bStart = new Date(block.start_time);
    const bEnd = new Date(block.end_time);
    if (bStart <= slotStart && bEnd > slotStart) {
      return { block, continued: bStart < slotStart };
    }
  }
  return null;
}

function buildScrollStrip(slots, schedules) {
  const strip = document.createElement('div');
  strip.id = 'guide-scroll-strip';

  const channelAfter = getCSSVar('--channel-position').replace(/["']/g, '') === 'after';
  const offairText = getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'Offair';

  for (const slot of slots) {
    const heading = document.createElement('div');
    heading.className = 'time-slot-heading';
    heading.textContent = formatTime12(slot.start);
    strip.appendChild(heading);

    for (const station of stations) {
      const row = document.createElement('div');
      row.className = 'listing-row';
      if (channelAfter) row.classList.add('channel-after');

      const channelInfo = document.createElement('span');
      channelInfo.className = 'channel-info';

      const numSpan = document.createElement('span');
      numSpan.className = 'channel-number';
      numSpan.textContent = station.channel_number || '?';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'channel-name';
      nameSpan.textContent = station.network_long_name || station.network_name;

      channelInfo.appendChild(numSpan);
      channelInfo.appendChild(nameSpan);

      const titleSpan = document.createElement('span');
      titleSpan.className = 'show-title';

      const result = findBlockForSlot(schedules[station.network_name] || [], slot.start);
      if (result) {
        titleSpan.textContent = result.block.title || offairText;
        if (result.continued) row.classList.add('continued');
      } else {
        titleSpan.textContent = offairText;
      }

      row.appendChild(channelInfo);
      row.appendChild(titleSpan);
      strip.appendChild(row);
    }
  }

  return strip;
}

function stopScrolling() {
  if (scrollInterval) {
    clearInterval(scrollInterval);
    scrollInterval = null;
  }
}

async function buildGuide() {
  const slots = computeSlotTimes();
  const schedules = await fetchAllSchedules(slots);
  const listings = document.getElementById('guide-listings');
  listings.innerHTML = '';
  listings.scrollTop = 0;
  listings.appendChild(buildScrollStrip(slots, schedules));
}

function startScrolling() {
  stopScrolling();
  const listings = document.getElementById('guide-listings');
  const speed = getScrollSpeed();
  const pauseMs = getPauseDuration();

  listings.scrollTop = 0;

  setTimeout(function () {
    scrollInterval = setInterval(function () {
      const maxScroll = listings.scrollHeight - listings.clientHeight;
      if (maxScroll <= 0 || listings.scrollTop >= maxScroll) {
        stopScrolling();
        setTimeout(async function () { await buildGuide(); startScrolling(); }, pauseMs);
        return;
      }
      listings.scrollTop += speed;
    }, 50);
  }, pauseMs);
}

function startClock() {
  const el = document.getElementById('clock');
  const tick = () => { el.textContent = formatTime12(new Date()); };
  tick();
  setInterval(tick, 1000);
}

async function loadMusicPlaylist() {
  try {
    const resp = await fetch('music_playlist.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    musicPlaylist = data.music_files || [];
  } catch (e) {
    console.warn('no music playlist:', e.message);
  }
}

function playMusicTrack(index) {
  if (!bgPlayer || !musicPlaylist.length) return;
  currentMusicIndex = index % musicPlaylist.length;
  bgPlayer.src = musicPlaylist[currentMusicIndex];
  bgPlayer.play().catch(function () {
    // autoplay blocked - resume on first interaction
    document.addEventListener('click', () => bgPlayer.play(), { once: true });
  });
}

function setupMusic() {
  bgPlayer = document.getElementById('bgMusicPlayer');
  if (!bgPlayer || !musicPlaylist.length) return;

  const vol = parseFloat(getCSSVar('--music-volume'));
  bgPlayer.volume = isNaN(vol) ? 0.3 : vol;
  bgPlayer.addEventListener('ended', () => playMusicTrack(currentMusicIndex + 1));
  bgPlayer.addEventListener('error', () => playMusicTrack(currentMusicIndex + 1));
  playMusicTrack(0);
}

async function init() {
  loadTheme(THEME);

  const headerPos = getCSSVar('--header-position').replace(/["']/g, '');
  if (headerPos === 'bottom') document.getElementById('guide-wrapper').classList.add('header-bottom');

  document.getElementById('header-text').textContent = HEADER_TEXT;
  startClock();

  await fetchStations();
  await loadMusicPlaylist();
  await buildGuide();
  startScrolling();
  setupMusic();
}

document.addEventListener('DOMContentLoaded', init);