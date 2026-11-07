const params = new URLSearchParams(window.location.search);
const THEME = params.get('theme') || '80s';
const SLOT_COUNT = parseInt(params.get('slots')) || 3;
const HEADER_TEXT = params.get('header') || null;
const PAUSE_OVERRIDE = params.get('pause');
const MOCK = params.get('mock') === '1';
const USE_META = params.get('use_meta') !== '0';
const SHOW_DESCRIPTION = ['1', 'true'].includes((params.get('show_description') || '').toLowerCase());
const MUSIC_PATH = params.get('music');
const VIDEOS = params.get('videos') !== 'false';
const MESSAGES_PATH = params.get('messages');
const LOOP = params.get('loop') !== '0';
let RANDOM_START = params.get('random_start') === '1';
const INTERACTIVE = params.get('interactive') === '1';
const AUTOSCROLL = params.get('autoscroll') !== '0';
const MAX_HOURS = parseFloat(params.get('max_hours')) || 24;
const IDLE_MS = (parseFloat(params.get('idle')) || 30) * 1000;
const SLOT_MS = 30 * 60 * 1000;

let stations = [];

// list-mode scroll state
let animFrame = null;
let scrollY = 0;
let pauseUntil = 0;

// grid-mode scroll state
let gridAnimFrame = null;
let gridScrollY = 0;
let gridPauseUntil = 0;
let gridRebuildTimer = null;
let currentSlots = null;

// interactive navigation state
let navigating = false;
let timeOffset = 0;
let selRow = 0;
let selFocusMs = 0;
let idleTimer = null;
let keyChain = Promise.resolve();

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
let messageFadeTimer = null;


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
    document.head.appendChild(link);
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
  return (!isNaN(val) && val > 0) ? val : 1.1;
}

function currentHalfHour() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(),
    now.getHours(), Math.floor(now.getMinutes() / 30) * 30, 0, 0);
}

function computeSlotTimes(offsetSlots = 0) {
  const base = currentHalfHour().getTime() + offsetSlots * SLOT_MS;
  const slots = [];
  for (let i = 0; i < SLOT_COUNT; i++) {
    const start = new Date(base + i * SLOT_MS);
    slots.push({ start, end: new Date(start.getTime() + SLOT_MS) });
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
      has_schedule: true
    };
  });
}

let mockSchedules = null;

function mockFetchAllSchedules(slots) {
  const end = slots[slots.length - 1].end.getTime();
  if (mockSchedules && mockSchedules.end >= end) return mockSchedules.data;

  const data = {};
  const horizon = Math.max(end, currentHalfHour().getTime() + (MAX_HOURS + 2) * 3600 * 1000);
  for (const station of stations) {
    const blocks = [];
    let t = currentHalfHour().getTime() - SLOT_MS;
    let episode = 1;
    while (t < horizon) {
      const duration = (Math.floor(Math.random() * 3) + 1) * SLOT_MS;
      const title = MOCK_SHOWS[Math.floor(Math.random() * MOCK_SHOWS.length)];
      const meta = Math.random() < 0.6
        ? { type: 'episode', title: 'Episode ' + episode++, plot: 'A mock plot for ' + title + '. Things happen, and then other things happen.' }
        : { type: 'movie', plot: 'A mock description of ' + title + '.' };
      blocks.push({ start_time: new Date(t).toISOString(), end_time: new Date(t + duration).toISOString(), title, meta });
      t += duration;
    }
    data[station.network_name] = blocks;
  }
  mockSchedules = { end: horizon, data };
  return data;
}

async function fetchStations() {
  const all = await window.fs42Common.fetchChannels();
  stations = all.filter(s => !s.hidden);
}

async function fetchAllSchedules(slots, includeMeta) {
  if (!stations.length) return {};

  const overallStart = slots[0].start;
  const overallEnd = slots[slots.length - 1].end;

  try {
    return await window.fs42Common.fetchGuideSchedules(
      formatDateForAPI(overallStart),
      formatDateForAPI(overallEnd),
      includeMeta
    );
  } catch (e) {
    console.error('error fetching schedules', e);
    return {};
  }
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
      const name = station.network_name;
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

    if (lastTime !== null) scrollY += pxPerMs * (now - lastTime);
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
  el._block = block;
  el._start = bStart.getTime();
  el._end = bEnd.getTime();

  el.style.left = leftPct + '%';
  el.style.width = `calc(${widthPct}% - 2px)`;

  const titleSpan = document.createElement('span');
  titleSpan.className = 'program-title';
  titleSpan.textContent = block.title || 'Untitled';
  el.appendChild(titleSpan);

  const meta = USE_META && block.meta;
  let desc = meta && meta.plot;
  let isEpisodeTitle = false;
  if (meta && meta.type === 'episode' && !SHOW_DESCRIPTION && meta.title) {
    desc = meta.title;
    isEpisodeTitle = true;
  }
  if (desc) {
    const descSpan = document.createElement('span');
    descSpan.className = isEpisodeTitle ? 'program-desc is-episode-title' : 'program-desc';
    descSpan.textContent = desc;
    el.appendChild(descSpan);
  }

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
    nameSpan.textContent = station.network_name;

    channelDiv.appendChild(numSpan);
    channelDiv.appendChild(nameSpan);
    row.appendChild(channelDiv);

    const programsDiv = document.createElement('div');
    programsDiv.className = 'grid-programs';

    const blocks = schedules[station.network_name] || [];

    if (station.has_schedule) {
      for (const block of blocks) {
        const blockEl = createGridProgramBlock(block, guideStartMs, guideEndMs, totalMs, now);
        if (blockEl) programsDiv.appendChild(blockEl);
      }
    }

    if (!programsDiv.children.length) {
      const noInfo = document.createElement('div');
      noInfo.className = 'grid-program-block';
      noInfo.style.left = '0';
      noInfo.style.width = '100%';
      noInfo._block = null;
      noInfo._start = guideStartMs;
      noInfo._end = guideEndMs;
      const t = document.createElement('span');
      t.className = 'program-title';
      t.textContent = station.network_long_name || offairText;
      noInfo.appendChild(t);
      programsDiv.appendChild(noInfo);
    }

    row.appendChild(programsDiv);
    strip.appendChild(row);
  }

  return strip;
}

async function buildGrid() {
  const slots = computeSlotTimes(timeOffset);
  const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots, USE_META);
  updateGridHeader(slots);
  const gridListings = document.getElementById('grid-listings');
  gridListings.innerHTML = '';
  gridListings.appendChild(buildGridStrip(slots, schedules));
  currentSlots = slots;
}

function scheduleGridRebuild(delayMs) {
  clearTimeout(gridRebuildTimer);
  gridRebuildTimer = setTimeout(async function () {
    if (navigating) return;
    await buildGrid();
    startGridScrolling();
  }, delayMs);
}

function startGridScrolling() {
  if (gridAnimFrame) {
    cancelAnimationFrame(gridAnimFrame);
    gridAnimFrame = null;
  }
  if (navigating) return;
  if (!AUTOSCROLL) {
    setGridScroll(0);
    return;
  }

  const listings = document.getElementById('grid-listings');
  const strip = document.getElementById('grid-scroll-strip');
  if (!strip || !listings) return;

  const pxPerMs = getScrollSpeed() / 50;
  const pauseMs = getPauseDuration();

  // Clean up any previous clone
  const existingClone = document.getElementById('grid-scroll-strip-clone');
  if (existingClone) existingClone.remove();

  let clone;
  const originalHeight = strip.scrollHeight;

  // Loop guide if true.
  if (LOOP) {
    clone = strip.cloneNode(true);
    clone.id = 'grid-scroll-strip-clone';
    clone.setAttribute('aria-hidden', 'true');
    strip.parentElement.appendChild(clone);
    clone.style.transform = `translateY(${originalHeight}px)`;
  }
      // Random channel start
      if (RANDOM_START) {
        gridScrollY = Math.random() * originalHeight;
        RANDOM_START = false;
      } else if (!LOOP) {
        gridScrollY = 0;
      }
        
  strip.style.transform = 'translateY(0)';
  gridPauseUntil = LOOP ? 0 : performance.now() + pauseMs;

  let lastTime = null;

  function tick(now) {
    if (navigating) return;
    if (now < gridPauseUntil) {
      gridAnimFrame = requestAnimationFrame(tick);
      return;
    }

    // Loop guide if true.
    if (LOOP) {
      if (lastTime !== null) gridScrollY += pxPerMs * (now - lastTime);
      lastTime = now;

      if (gridScrollY >= originalHeight) {
        gridScrollY -= originalHeight;
        if (gridAnimFrame) {
          cancelAnimationFrame(gridAnimFrame);
          gridAnimFrame = null;
        }
        buildGrid().then(function () { if (!navigating) startGridScrolling(); });
        return;
      }

      strip.style.transform = `translateY(-${gridScrollY}px)`;
      clone.style.transform = `translateY(${originalHeight - gridScrollY}px)`;
      gridAnimFrame = requestAnimationFrame(tick);

    } else {
      const maxScroll = strip.offsetHeight - listings.clientHeight;

      if (maxScroll <= 0) {
        scheduleGridRebuild(pauseMs);
        return;
      }

      if (lastTime !== null) gridScrollY += pxPerMs * (now - lastTime);
      lastTime = now;

      if (gridScrollY >= maxScroll) {
        strip.style.transform = `translateY(-${maxScroll}px)`;
        lastTime = null;
        scheduleGridRebuild(pauseMs);
        return;
      }

      strip.style.transform = `translateY(-${gridScrollY}px)`;
      gridAnimFrame = requestAnimationFrame(tick);
    }
  }

  gridAnimFrame = requestAnimationFrame(tick);
}

async function initGridMode() {
  document.getElementById('guide-header').style.display = 'none';
  const oldClock = document.getElementById('clock');
  if (oldClock) oldClock.remove();
  buildGridDOM();
  startClock();


  const mediaLoaded = Promise.all([
    loadMusicPlaylist(),
    loadVideoPlaylist(),
    loadMessages()
  ]);

  if (MOCK) mockFetchStations(); else await fetchStations();
  await buildGrid();
  startGridScrolling();
  if (INTERACTIVE) setupInteractive();
  if (INTERACTIVE || !AUTOSCROLL) setInterval(refreshIfSlotChanged, 30 * 1000);

  await mediaLoaded;
  setupMusic();
  setupVideo();
  startTextCarousel();
}


// ===== INTERACTIVE GRID =====

function setGridScroll(y) {
  const listings = document.getElementById('grid-listings');
  const strip = document.getElementById('grid-scroll-strip');
  if (!listings || !strip) return;
  const maxScroll = Math.max(0, strip.offsetHeight - listings.clientHeight);
  gridScrollY = Math.min(Math.max(0, y), maxScroll);
  strip.style.transform = `translateY(-${gridScrollY}px)`;
}

function gridRows() {
  const strip = document.getElementById('grid-scroll-strip');
  return strip ? Array.from(strip.children) : [];
}

function rowCells(rowIdx) {
  const row = gridRows()[rowIdx];
  if (!row) return [];
  return Array.from(row.querySelectorAll('.grid-program-block')).sort((a, b) => a._start - b._start);
}

function cellAt(rowIdx, t) {
  const cells = rowCells(rowIdx);
  return cells.find(c => c._start <= t && c._end > t)
    || cells.find(c => c._start >= t)
    || cells[cells.length - 1]
    || null;
}

function windowBounds() {
  return {
    start: currentSlots[0].start.getTime(),
    end: currentSlots[currentSlots.length - 1].end.getTime(),
  };
}

function selectedCell() {
  return document.querySelector('#grid-scroll-strip .grid-program-block.selected');
}

function selectCell(rowIdx, cell) {
  const prev = selectedCell();
  if (prev) prev.classList.remove('selected');
  selRow = rowIdx;
  if (!cell) return;
  cell.classList.add('selected');
  ensureRowVisible(rowIdx);
  showProgramInfo(stations[rowIdx], cell);
}

function ensureRowVisible(rowIdx) {
  const row = gridRows()[rowIdx];
  const listings = document.getElementById('grid-listings');
  if (!row || !listings) return;
  const top = row.offsetTop;
  const bottom = top + row.offsetHeight;
  if (top < gridScrollY) setGridScroll(top);
  else if (bottom > gridScrollY + listings.clientHeight) setGridScroll(bottom - listings.clientHeight);
  else setGridScroll(gridScrollY);
}

function showProgramInfo(station, cell) {
  const titleEl = document.getElementById('text-message-title');
  const bodyEl = document.getElementById('text-message-body');
  if (!titleEl || !bodyEl) return;

  const block = cell._block;
  const channelLine = (station.channel_number || '?') + ' ' + station.network_name;
  const lines = [];

  if (block) {
    titleEl.textContent = block.title || 'Untitled';
    lines.push(channelLine + '  ·  ' + formatTime12(new Date(cell._start)) + ' – ' + formatTime12(new Date(cell._end)));
    const meta = USE_META && block.meta;
    if (meta && meta.type === 'episode' && meta.title) lines.push(meta.title);
    if (meta && meta.plot) lines.push(meta.plot);
  } else {
    titleEl.textContent = station.network_long_name || station.network_name;
    lines.push(channelLine);
  }

  bodyEl.textContent = lines.join('\n');
  clampToFit(bodyEl);
  titleEl.style.opacity = '1';
  bodyEl.style.opacity = '1';
}

function topVisibleRow() {
  const rows = gridRows();
  const idx = rows.findIndex(r => r.offsetTop >= gridScrollY - 1);
  return idx === -1 ? Math.max(0, rows.length - 1) : idx;
}

function takeControl() {
  navigating = true;
  clearTimeout(gridRebuildTimer);
  if (gridAnimFrame) {
    cancelAnimationFrame(gridAnimFrame);
    gridAnimFrame = null;
  }
  clearTimeout(messageCarouselTimer);
  clearTimeout(messageFadeTimer);

  const strip = document.getElementById('grid-scroll-strip');
  const clone = document.getElementById('grid-scroll-strip-clone');
  if (clone) {
    if (strip && strip.offsetHeight) gridScrollY = gridScrollY % strip.offsetHeight;
    clone.remove();
  }
  document.getElementById('grid-listings').classList.add('navigating');

  const row = topVisibleRow();
  setGridScroll(gridRows()[row] ? gridRows()[row].offsetTop : 0);
  const cell = cellAt(row, Date.now());
  selFocusMs = cell ? Math.max(cell._start, windowBounds().start) : windowBounds().start;
  selectCell(row, cell);
}

function releaseControl() {
  navigating = false;
  const prev = selectedCell();
  if (prev) prev.classList.remove('selected');
  document.getElementById('grid-listings').classList.remove('navigating');
  timeOffset = 0;
  buildGrid().then(function () {
    if (navigating) return;
    startGridScrolling();
    startTextCarousel();
  });
}

function resetIdleTimer() {
  clearTimeout(idleTimer);
  if (!AUTOSCROLL) return;
  idleTimer = setTimeout(function () {
    keyChain = keyChain.then(releaseControl);
  }, IDLE_MS);
}

async function shiftWindow(delta) {
  const next = Math.min(Math.max(0, timeOffset + delta), Math.round(MAX_HOURS * 2));
  if (next === timeOffset) return false;
  timeOffset = next;
  await buildGrid();
  return true;
}

function moveRow(delta) {
  const target = selRow + delta;
  if (target < 0 || target >= stations.length) return;
  selectCell(target, cellAt(target, selFocusMs));
}

async function moveRight() {
  const cur = selectedCell();
  if (!cur) return;
  const win = windowBounds();
  const cells = rowCells(selRow);
  const next = cells[cells.indexOf(cur) + 1];

  if (next && next._start < win.end) {
    selFocusMs = next._start;
    selectCell(selRow, next);
    return;
  }

  const curStart = cur._start;
  const target = next ? next._start : cur._end;
  if (!await shiftWindow(1)) return;
  const nwin = windowBounds();
  selectAfterShift(target < nwin.end ? target : curStart);
}

async function moveLeft() {
  const cur = selectedCell();
  if (!cur) return;
  const win = windowBounds();
  const cells = rowCells(selRow);
  const prev = cells[cells.indexOf(cur) - 1];

  if (cur._start >= win.start && prev && prev._end > win.start) {
    selFocusMs = Math.max(prev._start, win.start);
    selectCell(selRow, prev);
    return;
  }

  const target = cur._start < win.start ? cur._start : cur._start - 1;
  if (!await shiftWindow(-1)) return;
  selectAfterShift(target);
}

function selectAfterShift(t) {
  const start = windowBounds().start;
  const cell = cellAt(selRow, Math.max(t, start));
  selFocusMs = cell ? Math.max(cell._start, start) : start;
  selectCell(selRow, cell);
}

async function tuneSelected() {
  const station = stations[selRow];
  if (!station) return;
  if (MOCK) {
    console.log('mock: would tune to channel', station.channel_number);
    return;
  }
  try {
    await window.fs42Api.get('player/channels/' + station.channel_number);
  } catch (e) {
    console.error('tune failed', e);
  }
}

async function handleNavKey(key) {
  if (!navigating) {
    takeControl();
    resetIdleTimer();
    return;
  }
  resetIdleTimer();
  switch (key) {
    case 'PageUp': moveRow(-1); break;
    case 'PageDown': moveRow(1); break;
    case 'NavLeft': await moveLeft(); break;
    case 'NavRight': await moveRight(); break;
    case 'Enter': await tuneSelected(); break;
  }
}

async function refreshIfSlotChanged() {
  if (!currentSlots) return;
  if (!navigating && AUTOSCROLL) return;
  if (computeSlotTimes(timeOffset)[0].start.getTime() === currentSlots[0].start.getTime()) return;
  keyChain = keyChain.then(async function () {
    await buildGrid();
    if (navigating) selectCell(selRow, cellAt(selRow, Math.max(selFocusMs, windowBounds().start)));
    else setGridScroll(gridScrollY);
  });
}

function setupInteractive() {
  const keys = new Set(['PageUp', 'PageDown', 'NavLeft', 'NavRight', 'Enter']);
  document.addEventListener('keydown', function (e) {
    // only keys injected through /player/web/key (remote_controller.py or the web remote)
    if (e.isTrusted || !keys.has(e.key)) return;
    e.preventDefault();
    keyChain = keyChain.then(() => handleNavKey(e.key)).catch(err => console.error(err));
  });
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

function clampToFit(el) {
  el.style.webkitLineClamp = '';
  if (el.scrollHeight <= el.clientHeight) return;
  const lineHeight = parseFloat(getComputedStyle(el).lineHeight);
  el.style.webkitLineClamp = String(Math.max(1, Math.floor(el.clientHeight / lineHeight)));
}

function showNextMessage(index) {
  const titleEl = document.getElementById('text-message-title');
  const bodyEl = document.getElementById('text-message-body');
  if (!titleEl || !bodyEl) return;

  const msg = messages[index % messages.length];

  titleEl.style.opacity = '0';
  bodyEl.style.opacity = '0';

  messageFadeTimer = setTimeout(function () {
    titleEl.innerHTML = msg.title || '';
    bodyEl.textContent = msg.body || '';
    clampToFit(bodyEl);
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
    const musicLoaded = loadMusicPlaylist();
    if (MOCK) mockFetchStations(); else await fetchStations();
    await buildGuide();
    startScrolling();
    await musicLoaded;
    setupMusic();
  }
}

document.addEventListener('DOMContentLoaded', init);
