const params = new URLSearchParams(window.location.search);
const THEME = params.get('theme') || '80s';
const SLOT_COUNT = parseInt(params.get('slots')) || 3;
const HEADER_TEXT = params.get('header') || null;
const PAUSE_OVERRIDE = params.get('pause');
const MOCK = params.get('mock') === '1';
const MUSIC_PATH = params.get('music');
const VIDEOS = params.get('videos') !== 'false';
const MESSAGES_PATH = params.get('messages');

let stations = [];

// list-mode scroll state
let animFrame = null;
let scrollY = 0;
let pauseUntil = 0;

// grid-mode scroll state
let gridAnimFrame = null;
let gridScrollY = 0;
let gridPauseUntil = 0;

// music
let musicPlaylist = [];
let currentMusicIndex = 0;
let bgPlayer = null;

// video
let videoPlaylist = [];
let currentVideoIndex = 0;
let bgVideoPlayer = null;

// text carousel
let messages = [];
let messageCarouselTimer = null;


function loadTheme(name) {
  return new Promise(function (resolve) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'themes/' + name + '.css';
    link.addEventListener('load', resolve);
    link.addEventListener('error', function () {
      console.warn('theme "' + name + '" not found, falling back to 80s.');
      if (name !== '80s') {
        loadTheme('80s').then(resolve);
      } else {
        resolve();
      }
    });
    document.head.insertBefore(link, document.head.firstChild);
  });
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

// mock data for local scroll testing (?mock=1)
const MOCK_SHOWS = [
  'Late Night Movie', 'The Evening News', 'Sports Center', 'Nature Documentary',
  'Sitcom Reruns', 'Talk Show', 'Crime Drama', 'Cooking Hour', 'Saturday Morning Cartoons',
  'Local Weather Update', 'Classic Film', 'Music Videos', 'Game Show Marathon',
  'Science Fiction Theater', 'Western Double Feature', 'Home Shopping', 'News Magazine',
  'Children\'s Programming', 'Live Sports', 'Comedy Special'
];

function mockFetchStations() {
  stations = Array.from({ length: 24 }, function (_, i) {
    const num = i + 2;
    return {
      channel_number: num,
      network_name: 'ch' + num,
      network_long_name: 'Channel ' + num,
      has_schedule: true,
      schedule_summary: { start: 1, end: 1 }
    };
  });
}

function mockFetchAllSchedules(slots) {
  const schedules = {};
  const slotMs = 30 * 60 * 1000;
  for (const station of stations) {
    const blocks = [];
    let t = slots[0].start.getTime();
    const end = slots[slots.length - 1].end.getTime();
    while (t < end) {
      const duration = (Math.floor(Math.random() * 3) + 1) * slotMs;
      const title = MOCK_SHOWS[Math.floor(Math.random() * MOCK_SHOWS.length)];
      blocks.push({ start_time: new Date(t).toISOString(), end_time: new Date(t + duration).toISOString(), title });
      t += duration;
    }
    schedules[station.network_name] = blocks;
  }
  return schedules;
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


// ===== LIST MODE (80s) =====

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
      const name = station.network_long_name || station.network_name;
      nameSpan.textContent = name.length > 10 ? name.slice(0, 10) + '…' : name;

      channelInfo.appendChild(numSpan);
      channelInfo.appendChild(nameSpan);

      const titleSpan = document.createElement('span');
      titleSpan.className = 'show-title';

      const result = findBlockForSlot(schedules[station.network_name] || [], slot.start);
      if (result) {
        const t = result.block.title || offairText;
        titleSpan.textContent = t.length > 20 ? t.slice(0, 20) + '…' : t;
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
  if (animFrame) {
    cancelAnimationFrame(animFrame);
    animFrame = null;
  }
}

async function buildGuide() {
  const slots = computeSlotTimes();
  const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots);
  const listings = document.getElementById('guide-listings');
  listings.innerHTML = '';
  listings.appendChild(buildScrollStrip(slots, schedules));
}

function startScrolling() {
  stopScrolling();

  const listings = document.getElementById('guide-listings');
  const strip = document.getElementById('guide-scroll-strip');
  if (!strip) return;

  const pxPerMs = getScrollSpeed() / 50;
  const pauseMs = getPauseDuration();

  scrollY = 0;
  strip.style.transform = 'translateY(0)';
  pauseUntil = performance.now() + pauseMs;

  let lastTime = null;

  function tick(now) {
    if (now < pauseUntil) {
      animFrame = requestAnimationFrame(tick);
      return;
    }

    const maxScroll = strip.offsetHeight - listings.clientHeight;

    if (maxScroll <= 0) {
      setTimeout(async function () { await buildGuide(); startScrolling(); }, pauseMs);
      return;
    }

    if (lastTime !== null) {
      scrollY += pxPerMs * (now - lastTime);
    }
    lastTime = now;

    if (scrollY >= maxScroll) {
      strip.style.transform = `translateY(-${maxScroll}px)`;
      lastTime = null;
      setTimeout(async function () { await buildGuide(); startScrolling(); }, pauseMs);
      return;
    }

    strip.style.transform = `translateY(-${scrollY}px)`;
    animFrame = requestAnimationFrame(tick);
  }

  animFrame = requestAnimationFrame(tick);
}


// ===== GRID MODE (90s / 00s) =====

function buildGridDOM() {
  const listings = document.getElementById('guide-listings');
  listings.classList.add('grid-mode');
  listings.innerHTML = `
    <div id="top-panel">
      <div id="video-panel"><video id="bgVideoPlayer" preload="auto"></video></div>
      <div id="text-panel">
        <div id="text-message-title"></div>
        <div id="text-message-body"></div>
      </div>
    </div>
    <div id="grid-wrapper">
      <div id="grid-header"><div class="grid-channel-stub"><span id="clock"></span></div></div>
      <div id="grid-listings"></div>
    </div>
  `;

  const videoSide = getCSSVar('--video-side').replace(/["']/g, '') || 'left';
  if (videoSide === 'right') {
    document.getElementById('video-panel').style.order = '1';
    document.getElementById('text-panel').style.order = '0';
  }

  bgVideoPlayer = document.getElementById('bgVideoPlayer');
}

function updateGridHeader(slots) {
  const header = document.getElementById('grid-header');
  if (!header) return;
  // Remove old slot labels, keep the channel stub
  const stub = header.querySelector('.grid-channel-stub');
  header.innerHTML = '';
  if (stub) {
    header.appendChild(stub);
  } else {
    const newStub = document.createElement('div');
    newStub.className = 'grid-channel-stub';
    header.appendChild(newStub);
  }
  for (const slot of slots) {
    const slotEl = document.createElement('div');
    slotEl.className = 'grid-time-slot';
    slotEl.textContent = formatTime12(slot.start);
    header.appendChild(slotEl);
  }
}

function createGridProgramBlock(block, guideStartMs, guideEndMs, totalMs, now) {
  const bStart = new Date(block.start_time);
  const bEnd = new Date(block.end_time);

  if (bEnd.getTime() <= guideStartMs || bStart.getTime() >= guideEndMs) return null;

  const visStart = Math.max(bStart.getTime(), guideStartMs);
  const visEnd = Math.min(bEnd.getTime(), guideEndMs);

  const leftPct = (visStart - guideStartMs) / totalMs * 100;
  const widthPct = (visEnd - visStart) / totalMs * 100;

  const el = document.createElement('div');
  el.className = 'grid-program-block';
  if (bStart <= now && bEnd > now) el.classList.add('current');

  el.style.left = leftPct + '%';
  el.style.width = `calc(${widthPct}% - 2px)`;

  const titleSpan = document.createElement('span');
  titleSpan.className = 'program-title';
  titleSpan.textContent = block.title || 'Untitled';
  el.appendChild(titleSpan);

  return el;
}

function buildGridStrip(slots, schedules) {
  const strip = document.createElement('div');
  strip.id = 'grid-scroll-strip';

  const guideStartMs = slots[0].start.getTime();
  const guideEndMs = slots[slots.length - 1].end.getTime();
  const totalMs = guideEndMs - guideStartMs;
  const now = new Date();
  const offairText = getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'No Info';

  for (const station of stations) {
    const row = document.createElement('div');
    row.className = 'grid-row';

    const channelDiv = document.createElement('div');
    channelDiv.className = 'grid-channel';

    const numSpan = document.createElement('span');
    numSpan.className = 'channel-number';
    numSpan.textContent = station.channel_number || '?';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'channel-name';
    nameSpan.textContent = station.network_long_name || station.network_name;

    channelDiv.appendChild(numSpan);
    channelDiv.appendChild(nameSpan);
    row.appendChild(channelDiv);

    const programsDiv = document.createElement('div');
    programsDiv.className = 'grid-programs';

    const blocks = schedules[station.network_name] || [];

    if (!station.has_schedule || !blocks.length) {
      const noInfo = document.createElement('div');
      noInfo.className = 'grid-program-block';
      noInfo.style.left = '0';
      noInfo.style.width = '100%';
      const t = document.createElement('span');
      t.className = 'program-title';
      t.textContent = offairText;
      noInfo.appendChild(t);
      programsDiv.appendChild(noInfo);
    } else {
      for (const block of blocks) {
        const blockEl = createGridProgramBlock(block, guideStartMs, guideEndMs, totalMs, now);
        if (blockEl) programsDiv.appendChild(blockEl);
      }
    }

    row.appendChild(programsDiv);
    strip.appendChild(row);
  }

  return strip;
}

async function buildGrid() {
  const slots = computeSlotTimes();
  updateGridHeader(slots);
  const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots);
  const gridListings = document.getElementById('grid-listings');
  gridListings.innerHTML = '';
  gridListings.appendChild(buildGridStrip(slots, schedules));
}

function startGridScrolling() {
  if (gridAnimFrame) {
    cancelAnimationFrame(gridAnimFrame);
    gridAnimFrame = null;
  }

  const listings = document.getElementById('grid-listings');
  const strip = document.getElementById('grid-scroll-strip');
  if (!strip || !listings) return;

  const pxPerMs = getScrollSpeed() / 50;
  const pauseMs = getPauseDuration();

  gridScrollY = 0;
  strip.style.transform = 'translateY(0)';
  gridPauseUntil = performance.now() + pauseMs;

  let lastTime = null;

  function tick(now) {
    if (now < gridPauseUntil) {
      gridAnimFrame = requestAnimationFrame(tick);
      return;
    }

    const maxScroll = strip.offsetHeight - listings.clientHeight;

    if (maxScroll <= 0) {
      setTimeout(async function () { await buildGrid(); startGridScrolling(); }, pauseMs);
      return;
    }

    if (lastTime !== null) {
      gridScrollY += pxPerMs * (now - lastTime);
    }
    lastTime = now;

    if (gridScrollY >= maxScroll) {
      strip.style.transform = `translateY(-${maxScroll}px)`;
      lastTime = null;
      setTimeout(async function () { await buildGrid(); startGridScrolling(); }, pauseMs);
      return;
    }

    strip.style.transform = `translateY(-${gridScrollY}px)`;
    gridAnimFrame = requestAnimationFrame(tick);
  }

  gridAnimFrame = requestAnimationFrame(tick);
}

async function initGridMode() {
  document.getElementById('guide-header').style.display = 'none';
  const oldClock = document.getElementById('clock');
  if (oldClock) oldClock.remove();
  buildGridDOM();
  startClock();
  if (MOCK) mockFetchStations(); else await fetchStations();
  await Promise.all([
    loadMusicPlaylist(),
    loadVideoPlaylist(),
    loadMessages()
  ]);
  setupMusic();
  setupVideo();
  startTextCarousel();
  await buildGrid();
  startGridScrolling();
}


// ===== CLOCK =====

function startClock() {
  const el = document.getElementById('clock');
  const tick = () => { el.textContent = formatTime12(new Date()); };
  tick();
  setInterval(tick, 1000);
}


// ===== RANDOM PLAYBACK =====

function randomOtherIndex(playlist, current) {
  if (playlist.length <= 1) return 0;
  let next;
  do { next = Math.floor(Math.random() * playlist.length); } while (next === current);
  return next;
}


// ===== MUSIC =====

async function loadMusicPlaylist() {
  try {
    if (MUSIC_PATH) {
      const resp = await fetch('/media/list?path=' + encodeURIComponent(MUSIC_PATH));
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      musicPlaylist = data.files || [];
    } else {
      // Only fall back to the bundled json if the theme allows it
      const autoload = getCSSVar('--music-autoload').replace(/["']/g, '');
      if (autoload === 'false') return;
      const resp = await fetch('music_playlist.json');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      musicPlaylist = data.music_files || [];
    }
  } catch (e) {
    console.warn('no music playlist:', e.message);
  }
}

function playMusicTrack(index) {
  if (!bgPlayer || !musicPlaylist.length) return;
  currentMusicIndex = index % musicPlaylist.length;
  bgPlayer.src = musicPlaylist[currentMusicIndex];
  bgPlayer.play().catch(function () {
    document.addEventListener('click', () => bgPlayer.play(), { once: true });
  });
}

function setupMusic() {
  bgPlayer = document.getElementById('bgMusicPlayer');
  if (!bgPlayer || !musicPlaylist.length) return;

  const vol = parseFloat(getCSSVar('--music-volume'));
  bgPlayer.volume = isNaN(vol) ? 0.3 : vol;
  bgPlayer.addEventListener('ended', () => playMusicTrack(randomOtherIndex(musicPlaylist, currentMusicIndex)));
  bgPlayer.addEventListener('error', () => playMusicTrack(randomOtherIndex(musicPlaylist, currentMusicIndex)));
  playMusicTrack(Math.floor(Math.random() * musicPlaylist.length));
}


// ===== VIDEO =====

async function loadVideoPlaylist() {
  if (!VIDEOS) return;
  try {
    const resp = await fetch('/media/list_videos');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    videoPlaylist = data.files || [];
  } catch (e) {
    console.warn('no video playlist:', e.message);
  }
}

function playVideoTrack(index) {
  if (!bgVideoPlayer || !videoPlaylist.length) return;
  currentVideoIndex = index % videoPlaylist.length;
  bgVideoPlayer.src = videoPlaylist[currentVideoIndex];
  bgVideoPlayer.play().catch(function (e) {
    console.warn('video play failed:', e.message);
  });
}

function setupVideo() {
  bgVideoPlayer = document.getElementById('bgVideoPlayer');
  if (!bgVideoPlayer) return;

  if (!videoPlaylist.length) {
    const videoPanel = document.getElementById('video-panel');
    if (videoPanel) videoPanel.style.display = 'none';
    return;
  }

  const vol = parseFloat(getCSSVar('--video-volume'));
  bgVideoPlayer.volume = isNaN(vol) ? 0.8 : vol;

  let consecutiveErrors = 0;

  bgVideoPlayer.addEventListener('ended', function () {
    consecutiveErrors = 0;
    playVideoTrack(randomOtherIndex(videoPlaylist, currentVideoIndex));
  });

  bgVideoPlayer.addEventListener('error', function () {
    consecutiveErrors++;
    if (consecutiveErrors >= videoPlaylist.length) {
      console.warn('all video tracks failed to load, hiding video panel');
      const videoPanel = document.getElementById('video-panel');
      if (videoPanel) videoPanel.style.display = 'none';
      return;
    }
    setTimeout(() => playVideoTrack(randomOtherIndex(videoPlaylist, currentVideoIndex)), 1000);
  });

  playVideoTrack(Math.floor(Math.random() * videoPlaylist.length));
}


// ===== TEXT CAROUSEL =====

async function loadMessages() {
  if (!MESSAGES_PATH) return;
  try {
    const resp = await fetch('/media/json?path=' + encodeURIComponent(MESSAGES_PATH));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    messages = data.messages || [];
  } catch (e) {
    console.warn('no messages:', e.message);
  }
}

function showNextMessage(index) {
  const titleEl = document.getElementById('text-message-title');
  const bodyEl = document.getElementById('text-message-body');
  if (!titleEl || !bodyEl) return;

  const msg = messages[index % messages.length];

  titleEl.style.opacity = '0';
  bodyEl.style.opacity = '0';

  setTimeout(function () {
    titleEl.innerHTML = msg.title || '';
    bodyEl.textContent = msg.body || '';
    titleEl.style.opacity = '1';
    bodyEl.style.opacity = '1';
  }, 400);

  const defaultDuration = parseFloat(getCSSVar('--text-carousel-speed')) || 10;
  const duration = ((msg.duration || defaultDuration) * 1000) + 400;
  messageCarouselTimer = setTimeout(function () {
    showNextMessage(index + 1);
  }, duration);
}

function startTextCarousel() {
  const titleEl = document.getElementById('text-message-title');
  const bodyEl = document.getElementById('text-message-body');
  if (!titleEl || !bodyEl) return;

  if (!messages.length) {
    titleEl.textContent = 'FieldStation42';
    bodyEl.textContent = '';
    return;
  }

  showNextMessage(0);
}


// ===== INIT =====

async function init() {
  await loadTheme(THEME);

  const headerPos = getCSSVar('--header-position').replace(/["']/g, '');
  if (headerPos === 'bottom') document.getElementById('guide-wrapper').classList.add('header-bottom');

  const themeHeader = getCSSVar('--header-text').replace(/["']/g, '');
  document.getElementById('header-text').textContent = HEADER_TEXT || themeHeader || 'TV Guide';

  const layoutMode = getCSSVar('--layout-mode').replace(/["']/g, '') || 'list';

  if (layoutMode === 'grid') {
    await initGridMode();
  } else {
    startClock();
    if (MOCK) mockFetchStations(); else await fetchStations();
    await loadMusicPlaylist();
    await buildGuide();
    startScrolling();
    setupMusic();
  }
}

document.addEventListener('DOMContentLoaded', init);
