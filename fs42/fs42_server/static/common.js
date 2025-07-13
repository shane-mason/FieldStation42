// common.js

function toggleMenu() {
    var menu = document.getElementById('mainMenu');
    menu.classList.toggle('pure-menu-active');
}

window.addEventListener('resize', function () {
    if (window.innerWidth >= 768) {
        var menu = document.getElementById('mainMenu');
        if (menu) menu.classList.remove('pure-menu-active');
    }
});

// Fetch and display summary from /summary API
async function fetchStationSummary() {
    try {
        const resp = await window.fs42Api.get('summary');
        return resp.summary_data || [];
    } catch (e) {
        return [];
    }
}

// Fetch catalog for a station
async function fetchCatalog(networkId) {
    try {
        const resp = await window.fs42Api.get(`catalogs/${networkId}`);
        return resp.catalog_entries || [];

    } catch (e) {
        return [];
    }
}

// Render summary table (used in index.html)
function renderSummaryTable(stations) {
    if (!stations.length) return '<p>No stations found.</p>';
    let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
    html += '<thead><tr><th>Network</th><th>Catalog Entries</th><th>Total Duration</th><th>Schedule Start</th><th>Schedule End</th></tr></thead><tbody>';
    for (const station of stations) {
        const name = station.network_name || 'N/A';
        const entryCount = station.catalog_summary?.entry_count ?? 'N/A';
        let totalDuration = station.catalog_summary?.total_duration ?? 'N/A';
        if (typeof totalDuration === 'number') {
            totalDuration = (totalDuration / 3600).toFixed(2) + ' hrs';
        }
        const sched = station.schedule_summary || {};
        let start = sched.start ?? 'N/A';
        let end = sched.end ?? 'N/A';
        if (typeof start === 'string' && start.length > 10) start = start.replace('T', ' ');
        if (typeof end === 'string' && end.length > 10) end = end.replace('T', ' ');
        html += `<tr>
            <td data-label='Network'><strong>${name}</strong></td>
            <td data-label='Catalog Entries'>${entryCount}</td>
            <td data-label='Total Duration'>${totalDuration}</td>
            <td data-label='Schedule Start'>${start}</td>
            <td data-label='Schedule End'>${end}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    return html;
}

// Render catalog table
function renderCatalogTable(entries) {
    if (!entries.length) return '<p>No catalog entries found.</p>';
    let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
    html += '<thead><tr><th>Title</th><th>Path</th><th>Duration</th><th>Count</th><th>Hints</th></tr></thead><tbody>';
    for (const entry of entries) {
        let hints = Array.isArray(entry.hints) ? entry.hints.map(h => JSON.stringify(h)).join(', ') : '';
        let fullPath = entry.path || '';
        let shortPath = fullPath.length > 100 ? fullPath.slice(-100) : fullPath;
        html += `<tr>
            <td data-label='Title'>${entry.title}</td>
            <td data-label='Path'><span title="${fullPath}">${shortPath}</span></td>
            <td data-label='Duration'>${Number(entry.duration).toFixed(2)}</td>
            <td data-label='Count'>${entry.count}</td>
            <td data-label='Hints'>${hints}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    return html;
}

// Fetch schedule summary for extents
async function fetchScheduleSummary(networkId) {
    try {
        const resp = await window.fs42Api.get(`summary/schedules/${networkId}`);
        return resp;
    } catch (e) {
        return null;
    }
}

// Fetch schedule blocks for a station and date range
async function fetchSchedule(networkId, start, end) {
    try {
        let url = `schedules/${networkId}`;
        const params = [];
        if (start) params.push(`start=${encodeURIComponent(start)}`);
        if (end) params.push(`end=${encodeURIComponent(end)}`);
        if (params.length) url += `?${params.join('&')}`;
        const resp = await window.fs42Api.get(url);
        return resp.schedule_blocks || [];
    } catch (e) {
        return [];
    }
}

// Render schedule table
function renderScheduleTable(blocks) {
    if (!blocks.length) return '<p>No schedule blocks found.</p>';
    let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
    html += '<thead><tr><th>Start Time</th><th>End Time</th><th>Title</th></tr></thead><tbody>';
    for (const block of blocks) {
        // Format date/time for human readability
        let start = block.start_time ? formatDateTime(block.start_time) : '';
        let end = block.end_time ? formatDateTime(block.end_time) : '';
        html += `<tr>
            <td data-label='Start Time'>${start}</td>
            <td data-label='End Time'>${end}</td>
            <td data-label='Title'>${block.title || ''}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    return html;
}

function formatDateTime(dtStr) {
    // Accepts ISO string, returns 'YYYY-MM-DD HH:MM' format
    if (!dtStr) return '';
    const d = new Date(dtStr);
    if (isNaN(d.getTime())) return dtStr;
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd} ${hh}:${min}`;
}

window.fs42Common = {
    toggleMenu,
    fetchStationSummary,
    fetchCatalog,
    renderSummaryTable,
    renderCatalogTable,
    fetchScheduleSummary,
    fetchSchedule,
    renderScheduleTable
};
