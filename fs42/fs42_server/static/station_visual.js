(function () {
    const OPERATING_HOURS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5];
    const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
    const WEEKDAYS = DAYS.slice(0, 5);
    const WEEKEND = DAYS.slice(5);
    const VISUAL_TYPES = ['standard', 'loop', 'web'];
    const LEADING_KEYS = ['network_name', 'network_long_name', 'channel_number', 'network_type', 'hidden', 'parental_controls', 'visual_editor'];
    const BREAK_STRATEGIES = ['standard', 'center', 'end'];
    const DEFAULT_MEDIA = {
        off_air_video: 'runtime/off_air_pattern.mp4',
        sign_off_video: 'runtime/signoff.mp4',
        be_right_back_media: 'runtime/brb.png',
    };
    const LOCAL_SERVER = `http://localhost:${window.location.port || 4242}`;
    const WEB_PRESETS = [
        { label: 'Custom guide', url: `${LOCAL_SERVER}/static/customguide/customguide.html` },
        { label: 'Diagnostics', url: `${LOCAL_SERVER}/static/diagnostics.html` },
        { label: 'Pay-per-view', url: `${LOCAL_SERVER}/static/ppv/ppv.html` },
    ];
    const AUTOBUMP_STYLES = ['modern', 'retro', 'corporate', 'terminal'];
    const AUTOBUMP_STRATEGIES = [
        { value: 'both', label: 'Start and end of breaks' },
        { value: 'start', label: 'Start of breaks only' },
        { value: 'end', label: 'End of breaks only' },
    ];
    const TEXT_POSITIONS = ['left', 'right', 'center', 'top-left', 'top-right', 'top-center', 'bottom-left', 'bottom-right', 'bottom-center'];
    const BUMP_MUSIC = ['logo0.mp3', 'logo1.mp3', 'logo2.mp3', 'logo3.mp3', 'logo4.mp3', 'logo5.mp3', 'logo6.mp3'];
    const SLOT_KEYS = new Set([
        'tags', 'random_tags', 'continued', 'event', 'start_bump', 'end_bump', 'break_strategy',
        'schedule_increment', 'bump_dir', 'commercial_dir', 'sequence', 'sequence_start',
        'sequence_end', 'marathon', 'overrides',
    ]);

    const HELP = {
        stationName: 'The station\'s name, shown in the web console and used to identify it everywhere. Must be unique.',
        longName: 'Optional longer name, shown in the program guide instead of the network name.',
        channel: 'The number viewers tune to. Must be unique across stations.',
        type: 'Standard stations play scheduled shows; loop stations repeat a folder; web stations show a web page. Change the type in the JSON tab - each type uses different settings.',
        hidden: 'Hidden stations don\'t appear in the guide and are skipped when changing channels up or down.',
        parental: 'Viewers must enter the parental controls PIN before this station plays. The PIN is set as parental_controls_pin in main_config.json.',
        contentFolder: [
            'The folder holding this station\'s shows. Each folder inside it is a tag you can schedule - for example catalog/cartoon/saturday_morning is the tag saturday_morning.',
            'Relative to the FieldStation42 folder, or an absolute path like /mnt/media/shows.',
        ],
        commercialFolder: 'Commercials used to fill breaks. A folder inside the content folder, or an absolute path. Individual hours can use a different folder.',
        bumpFolder: [
            'Station bumps used in breaks. A folder inside the content folder, or an absolute path.',
            'Videos in its pre/ subfolder open a break, videos in post/ close one, and the rest fill gaps.',
        ],
        increment: [
            'In minutes. Shows start on multiples of this many minutes, and the time left before the next start is filled with commercials and bumps.',
            '30 works like traditional TV: a 22-minute show gets a 30-minute slot. 0 plays shows back to back.',
        ],
        breakStrategy: [
            'Where commercial breaks go in a show\'s slot:',
            'standard - spread through the show',
            'center - one break in the middle (good for movies)',
            'end - all breaks after the show',
        ],
        breakDuration: 'In seconds. The length of each commercial break. Default 120.',
        commercialFree: 'Fill the time between shows with bumps instead of commercials.',
        offAir: 'Plays during hours that have no rule, until the next hour. Required whenever an assigned day has an off-air hour. Default: runtime/off_air_pattern.mp4.',
        offAirCovered: 'Off-air hours are already covered by the off-air image set in the JSON tab.',
        offAirMode: [
            'What plays during off-air hours.',
            'Video: your off-air video, such as a test pattern.',
            'Autobump: a generated "Coming up on <station>" screen listing the next shows, with a countdown.',
        ],
        offAirAutobumpShared: 'Off-air hours use the autobump settings above.',
        autobumps: [
            'Autobumps are bump screens FieldStation42 makes for you: your title and details on a styled background, with music. Use them instead of, or as well as, bump videos.',
            'In each break, the opening autobump shows your title and details, and the closing one says "Coming up on <station>" and lists the next shows.',
        ],
        autobumpTitle: 'The big text on every autobump - usually the station name.',
        autobumpSubtitle: 'Smaller text under the title on the opening autobump. The closing one always says "Coming up on <station>".',
        autobumpStyle: 'The look of the autobump: modern, retro, corporate or terminal.',
        autobumpStrategy: [
            'Which bumps in each break are generated:',
            'Start and end - both.',
            'Start only - the closing bump comes from your bump folder instead.',
            'End only - the opening bump comes from your bump folder instead.',
        ],
        autobumpLength: 'In seconds. How long each autobump lasts. Empty uses the background video\'s length, or 7 seconds.',
        autobumpFill: 'Chance from 0 to 1 that a whole break becomes one "Coming up" autobump with a countdown, instead of commercials. 0 or empty never does.',
        autobumpDetail: 'An extra line on the opening autobump, like a channel number or slogan.',
        autobumpMusic: 'Music that plays under the autobump: logo0.mp3 to logo6.mp3 ship with FieldStation42, or add your own to fs42/fs42_server/static/bump/music, or use a full URL.',
        autobumpColor: 'A hex colour like #ffffff. Empty uses the style\'s colours.',
        autobumpBackground: 'URL of a background image.',
        autobumpVideo: 'Background video: a file name from fs42/fs42_server/static/bump/video, a path, or a URL.',
        autobumpLoops: 'How many times the background video plays when Length is empty.',
        autobumpVideoAudio: 'Play the background video\'s sound when no music is set.',
        autobumpTextPosition: 'Where the text sits on the screen.',
        autobumpTextTiming: 'In seconds.',
        autobumpCss: 'URL of a CSS file that overrides the autobump\'s look.',
        autobumpPreview: 'Opens the opening autobump in a new tab with these settings.',
        signOff: 'Plays once when the station goes off air at an hour marked sign-off, if it was on the air just before. Required if any hour is marked sign-off. Default: runtime/signoff.mp4.',
        brb: 'Fills the last few seconds of a break when no commercial or bump is short enough. Without it, viewers see the standby screen for those seconds. A video or an image. Default: runtime/brb.png.',
        shuffle: 'Off: videos play in alphabetical order and repeat. On: every video plays once in a random order, then the order is reshuffled.',
        webPage: 'Pick one of FieldStation42\'s built-in pages, or choose Custom URL and type any address. Picking a page replaces the URL; add options after a "?" in the URL, like ?theme=80s for the custom guide.',
        refresh: 'In seconds. Reloads the page this often. 0 or empty never reloads.',
        dayTemplates: [
            'A day template holds the rules for one kind of day - one rule per hour. Make templates here, then assign them to days of the week below.',
            'Each hour is a rule: when the scheduler is free during that hour, it picks content from the hour\'s tags. Content plays to the end, even into later hours, then the scheduler checks the clock again at the next schedule increment.',
            'Hours are listed from 06:00, the start of the broadcast day.',
        ],
        weekly: 'Choose which day template each day of the week uses. One template can be used on any number of days.',
        modeTags: 'When the scheduler is free during this hour, it picks a video from these tags. Videos play to the end, even past the hour.',
        modeContinued: 'Uses the tags of the nearest earlier hour that has tags. Only the tags carry over - bumps, break settings and sequences don\'t.',
        modeOffAir: 'If the scheduler lands in this hour, the station goes off air until the next hour and plays the off-air video. A show still running from an earlier hour plays through first.',
        signOffHour: 'Plays the sign-off video once before going off air, if the station was on the air just before.',
        tags: 'Tags are folders in the content folder. With more than one tag, the hour is split into equal parts in tag order, unless random is on.',
        randomTags: [
            'On: every pick in this hour uses a randomly chosen tag.',
            'Off: the hour is split into equal parts in tag order (with two tags, :00-:29 and :30-:59), and each pick uses the tag for the part of the hour it starts in.',
        ],
        startBump: 'A video, or a folder to pick a random video from, played before the first show picked in this hour. Inside the content folder, or an absolute path.',
        endBump: 'A video, or a folder to pick a random video from, played after every show picked in this hour. Inside the content folder, or an absolute path.',
        slotBreakStrategy: 'Overrides the station\'s break strategy for shows picked in this hour.',
        slotIncrement: 'In minutes. Overrides the station\'s schedule increment for shows picked in this hour.',
        slotCommercials: 'Use a different commercial folder for shows picked in this hour - for example kids\' commercials on Saturday morning.',
        slotBumps: 'Use a different bump folder for shows picked in this hour.',
        slotOverride: 'Applies a named group of settings from slot_overrides. Edit those groups in the JSON tab.',
        sequence: [
            'Plays a show\'s episodes in order (sorted by file path) and remembers where it left off, so each time this hour comes up the next episode plays.',
            'Hours with the same sequence name and tags share their place in the show.',
        ],
        sequenceStart: 'Where in the episode list to start, as a fraction: 0 is the first episode, 0.5 the middle. A negative value picks a random starting point.',
        sequenceEnd: 'Where in the episode list to stop, as a fraction: 1 is the last episode. After the end it starts over from the start value.',
        marathon: 'Sometimes replaces this hour with episodes back to back for several hours.',
        marathonChance: 'How likely the marathon is each time this hour comes up, from 0 (never) to 1 (always).',
        marathonHours: 'How many hours the marathon fills, starting at this hour.',
        marathonWhen: 'Optional date window, like October 15 - October 31. Outside it, the marathon never happens.',
    };

    let root = null;
    let conf = null;
    let notifyChange = () => {};
    let selectedTemplate = null;
    let selectedHour = null;
    let pendingTagMode = false;
    let slotClipboard = null;
    let contentFolders = { path: null, folders: undefined };
    let datalistCounter = 0;
    let originalKeyOrder = [];

    function el(tag, props = {}, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(props)) {
            if (value === undefined || value === null) continue;
            if (key === 'class') node.className = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else if (key === 'list' || key === 'role' || key.startsWith('data-') || key.startsWith('aria-')) node.setAttribute(key, value);
            else node[key] = value;
        }
        for (const child of children.flat()) {
            if (child === null || child === undefined || child === false) continue;
            node.append(child instanceof Node ? child : String(child));
        }
        return node;
    }

    function assign(target, key, value) {
        const empty = value === undefined || value === null || value === '' || value === false
            || (Array.isArray(value) && value.length === 0);
        if (empty) delete target[key];
        else target[key] = value;
    }

    function orderStationKeys(conf) {
        const trailing = ['day_templates', ...DAYS];
        const position = (k) => {
            const index = originalKeyOrder.indexOf(k);
            return index === -1 ? Infinity : index;
        };
        const middle = Object.keys(conf)
            .filter((k) => !LEADING_KEYS.includes(k) && !trailing.includes(k))
            .map((k, arrival) => ({ k, arrival }))
            .sort((a, b) => position(a.k) - position(b.k) || a.arrival - b.arrival)
            .map(({ k }) => k);
        middle.filter((k) => !originalKeyOrder.includes(k)).forEach((k) => originalKeyOrder.push(k));
        const ordered = [
            ...LEADING_KEYS.filter((k) => k in conf),
            ...middle,
            ...trailing.filter((k) => k in conf),
        ];
        const entries = ordered.map((k) => [k, conf[k]]);
        Object.keys(conf).forEach((k) => delete conf[k]);
        entries.forEach(([k, v]) => { conf[k] = v; });
    }

    function changed(redrawAfter = false) {
        orderStationKeys(conf);
        notifyChange();
        if (redrawAfter) redraw();
    }

    function supports(stationConfig) {
        const type = stationConfig?.station_conf?.network_type || 'standard';
        return VISUAL_TYPES.includes(type);
    }

    function render(container, stationConfig, onChange) {
        root = container;
        conf = stationConfig.station_conf;
        originalKeyOrder = Object.keys(conf);
        notifyChange = onChange;
        if (selectedTemplate && !(conf.day_templates || {})[selectedTemplate]) {
            selectedTemplate = null;
            selectedHour = null;
        }
        redraw();
    }

    function redraw() {
        if (!root) return;
        const type = conf.network_type || 'standard';
        const sections = [commonSection(type)];

        if (type === 'standard') {
            sections.push(standardSettingsSection(), autobumpSection(), mediaSection(), ...scheduleSections());
        } else if (type === 'loop') {
            sections.push(loopSection());
        } else if (type === 'web') {
            sections.push(webSection());
        } else {
            sections.push(el('div', { class: 'sv-note' },
                `The visual editor doesn't support "${type}" stations yet. Use the JSON tab.`));
        }
        root.replaceChildren(...sections);
        ensureContentFolders();
    }

    function helpTip(text) {
        const paragraphs = Array.isArray(text) ? text : [text];
        return el('span', {
            class: 'sv-help',
            tabIndex: 0,
            role: 'button',
            'aria-label': 'Help',
            onclick: (e) => {
                e.preventDefault();
                e.stopPropagation();
                e.currentTarget.focus();
            },
            onmouseenter: (e) => placeHelp(e.currentTarget),
            onfocus: (e) => placeHelp(e.currentTarget),
        }, '?', el('span', { class: 'sv-help-text', role: 'tooltip' }, paragraphs.map((p) => el('span', { class: 'sv-help-para' }, p))));
    }

    function placeHelp(icon) {
        const tipWidth = Math.min(352, window.innerWidth * 0.8);
        icon.classList.toggle('sv-help-flip', icon.getBoundingClientRect().left + tipWidth > window.innerWidth - 16);
    }

    function section(title, help, ...children) {
        return el('section', { class: 'sv-section' },
            el('h2', { class: 'sv-section-title' }, title, help ? helpTip(help) : null), ...children);
    }

    function field(label, control, help, required = false) {
        return el('label', { class: 'sv-field' },
            el('span', { class: 'sv-label' }, label,
                required ? el('span', { class: 'sv-required', title: 'Required' }, ' *') : null,
                help ? helpTip(help) : null),
            control);
    }

    function textInput(target, key, opts = {}) {
        return el('input', {
            type: 'text',
            class: 'sv-input',
            value: target[key] ?? '',
            placeholder: opts.placeholder,
            list: opts.list,
            required: !!opts.required,
            oninput: (e) => {
                assign(target, key, e.target.value.trim() === '' ? '' : e.target.value);
                if (opts.after) opts.after();
                changed();
            },
            onchange: opts.redrawOnCommit ? () => redraw() : undefined,
        });
    }

    function numberInput(target, key, opts = {}) {
        return el('input', {
            type: 'number',
            class: 'sv-input sv-input-number',
            value: target[key] ?? '',
            placeholder: opts.placeholder,
            step: opts.step ?? (opts.integer ? '1' : 'any'),
            required: !!opts.required,
            min: opts.min,
            max: opts.max,
            oninput: (e) => {
                const raw = e.target.value;
                if (raw === '') {
                    delete target[key];
                } else {
                    const parsed = opts.integer ? parseInt(raw, 10) : Number(raw);
                    if (Number.isNaN(parsed)) return;
                    target[key] = parsed;
                }
                changed();
            },
            onchange: opts.redrawOnCommit ? () => redraw() : undefined,
        });
    }

    function selectInput(target, key, options, opts = {}) {
        const values = options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o));
        if (target[key] !== undefined && !values.some((o) => o.value === target[key])) {
            values.push({ value: target[key], label: String(target[key]) });
        }
        const select = el('select', {
            class: 'sv-input',
            onchange: (e) => {
                assign(target, key, e.target.value);
                if (opts.after) opts.after(e.target.value);
                changed(opts.redrawOnCommit);
            },
        },
        opts.emptyLabel !== undefined ? el('option', { value: '' }, opts.emptyLabel) : null,
        values.map((o) => el('option', { value: o.value }, o.label)));
        select.value = target[key] ?? '';
        return select;
    }

    function checkbox(target, key, label, opts = {}) {
        return el('label', { class: 'sv-check' },
            el('input', {
                type: 'checkbox',
                checked: !!target[key],
                onchange: (e) => {
                    assign(target, key, e.target.checked);
                    changed(opts.redrawOnCommit);
                },
            }),
            el('span', {}, label),
            opts.help ? helpTip(opts.help) : null);
    }

    function folderDatalist(path, prefix = '') {
        const id = `sv-folders-${++datalistCounter}`;
        const list = el('datalist', { id });
        if (path) {
            loadFolders(path).then((folders) => {
                (folders || []).forEach((f) => list.append(el('option', { value: prefix + f })));
            });
        }
        return { id, list };
    }

    const folderRequests = {};

    function loadFolders(path) {
        if (!folderRequests[path]) {
            folderRequests[path] = window.fs42Api
                .get(`media/folders?path=${encodeURIComponent(path)}`)
                .then((data) => data.folders)
                .catch(() => null);
        }
        return folderRequests[path];
    }

    function redrawUnlessTyping() {
        const typing = root && root.contains(document.activeElement)
            && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName);
        if (!typing) redraw();
    }

    function ensureContentFolders() {
        const path = conf.content_dir;
        if (!path || contentFolders.path === path) return;
        contentFolders = { path, folders: undefined };
        loadFolders(path).then((folders) => {
            if (contentFolders.path !== path) return;
            contentFolders.folders = folders;
            redrawUnlessTyping();
        });
    }

    const folderExists = {};

    function checkFolder(path) {
        if (!(path in folderExists)) {
            folderExists[path] = undefined;
            loadFolders(path).then((folders) => {
                folderExists[path] = folders !== null;
                redrawUnlessTyping();
            });
        }
        return folderExists[path];
    }

    function parentDir(path) {
        if (!path) return 'catalog';
        const trimmed = path.replace(/\/+$/, '');
        const cut = trimmed.lastIndexOf('/');
        return cut > 0 ? trimmed.slice(0, cut) : 'catalog';
    }

    function contentDirField(target) {
        const parent = parentDir(target.content_dir);
        const { id, list } = folderDatalist(parent, `${parent}/`);
        return field('Content folder',
            el('span', {}, textInput(target, 'content_dir', { list: id, placeholder: 'catalog/my_channel', redrawOnCommit: true, required: true }), list),
            HELP.contentFolder, true);
    }

    function contentSubfolderField(target, key, label, hint, placeholder) {
        const { id, list } = folderDatalist(conf.content_dir);
        return field(label, el('span', {}, textInput(target, key, { list: id, placeholder }), list), hint);
    }

    function commonSection(type) {
        return section('Station', null,
            el('div', { class: 'sv-grid' },
                field('Network name', textInput(conf, 'network_name', { required: true }), HELP.stationName, true),
                field('Long name', textInput(conf, 'network_long_name', { placeholder: 'optional' }), HELP.longName),
                field('Channel number', numberInput(conf, 'channel_number', { integer: true, min: 0, required: true }), HELP.channel, true),
                field('Type', el('span', { class: 'sv-readonly' }, type), HELP.type)),
            el('div', { class: 'sv-row' },
                checkbox(conf, 'hidden', 'Hidden', { help: HELP.hidden }),
                checkbox(conf, 'parental_controls', 'Require parental PIN', { help: HELP.parental })));
    }

    function standardSettingsSection() {
        return section('Programming', null,
            el('div', { class: 'sv-grid' },
                contentDirField(conf),
                contentSubfolderField(conf, 'commercial_dir', 'Commercial folder', HELP.commercialFolder, 'commercial'),
                contentSubfolderField(conf, 'bump_dir', 'Bump folder', HELP.bumpFolder, 'bump'),
                field('Schedule increment', numberInput(conf, 'schedule_increment', { integer: true, step: '5', min: 0, placeholder: '30' }),
                    HELP.increment),
                field('Break strategy', selectInput(conf, 'break_strategy', BREAK_STRATEGIES, { emptyLabel: 'standard (default)' }), HELP.breakStrategy),
                field('Break duration', numberInput(conf, 'break_duration', { integer: true, min: 0, placeholder: '120' }), HELP.breakDuration)),
            el('div', { class: 'sv-row' },
                checkbox(conf, 'commercial_free', 'Commercial free', { help: HELP.commercialFree })));
    }

    function assignedSchedules(stationConf) {
        const templateMap = stationConf.day_templates || {};
        return DAYS
            .map((d) => (typeof stationConf[d] === 'string' ? templateMap[stationConf[d]] : stationConf[d]))
            .filter((schedule) => schedule && typeof schedule === 'object');
    }

    function hasOffAirHours(stationConf) {
        return assignedSchedules(stationConf).some((schedule) =>
            Array.from({ length: 24 }, (_, h) => schedule[String(h)])
                .some((slot) => !tagList(slot).length && !(slot && slot.continued)));
    }

    function usesSignOff(stationConf) {
        return assignedSchedules(stationConf).some((schedule) =>
            Object.values(schedule).some((slot) => slot && slot.event === 'signoff'));
    }

    function offAirCovered(stationConf) {
        return !!(stationConf.off_air_video || stationConf.off_air_image || stationConf.off_air_autobump);
    }

    function offAirAutobumpActive(stationConf) {
        return !!stationConf.off_air_autobump && !stationConf.off_air_video && !stationConf.off_air_image;
    }

    function missingMedia(stationConf) {
        if ((stationConf.network_type || 'standard') !== 'standard') return [];
        const missing = [];
        if (hasOffAirHours(stationConf) && !offAirCovered(stationConf)) {
            missing.push(['off_air_video', 'Off-air video', 'some hours are off air']);
        }
        if (usesSignOff(stationConf) && !stationConf.sign_off_video) {
            missing.push(['sign_off_video', 'Sign-off video', 'an hour is marked sign-off']);
        }
        if (stationConf.autobump && !stationConf.autobump.title) {
            missing.push(['autobump.title', 'Autobump title', 'autobumps are on']);
        }
        if (offAirAutobumpActive(stationConf) && !stationConf.autobump && !stationConf.off_air_autobump.title) {
            missing.push(['off_air_autobump.title', 'Off-air autobump title', 'off-air hours use an autobump']);
        }
        return missing;
    }

    let stashedAutobump = null;
    let stashedOffAirVideo = null;

    function defaultAutobumpTitle() {
        return conf.network_long_name || conf.network_name || '';
    }

    function autobumpPreviewUrl(ab) {
        const params = new URLSearchParams();
        const passThrough = ['title', 'subtitle', 'variation', 'detail1', 'detail2', 'detail3', 'bg_color', 'fg_color', 'bg',
            'bg_video_loop_count', 'text_position', 'text_delay', 'text_fade_in', 'text_fade_out', 'text_hide_before_end', 'css'];
        passThrough.forEach((key) => { if (ab[key] !== undefined && ab[key] !== '') params.set(key, ab[key]); });
        params.set('duration', String((ab.duration || 7) * 1000));
        if (ab.bg_music) params.set('bg_music', /^https?:/.test(ab.bg_music) ? ab.bg_music : `/static/bump/music/${ab.bg_music}`);
        if (ab.bg_video) params.set('bg_video', /^(https?:|\/)/.test(ab.bg_video) ? ab.bg_video : `/static/bump/video/${ab.bg_video}`);
        if (ab.bg_video_audio !== undefined) params.set('bg_video_audio', String(ab.bg_video_audio));
        return `/static/bump/bump.html?${params.toString()}`;
    }

    function musicDatalist() {
        const id = `sv-music-${++datalistCounter}`;
        return { id, list: el('datalist', { id }, BUMP_MUSIC.map((m) => el('option', { value: m }))) };
    }

    function autobumpSection() {
        const ab = conf.autobump;
        const toggle = el('label', { class: 'sv-check' },
            el('input', {
                type: 'checkbox',
                checked: !!ab,
                onchange: (e) => {
                    if (e.target.checked) {
                        conf.autobump = stashedAutobump || { title: defaultAutobumpTitle() };
                    } else {
                        stashedAutobump = conf.autobump;
                        delete conf.autobump;
                    }
                    changed(true);
                },
            }),
            el('span', {}, 'Generate bumps automatically'));

        if (!ab) return section('Autobumps', HELP.autobumps, el('div', { class: 'sv-row' }, toggle));

        const music = musicDatalist();
        return section('Autobumps', HELP.autobumps,
            el('div', { class: 'sv-row sv-autobump-toggle' }, toggle,
                el('button', {
                    class: 'pure-button sv-small',
                    title: 'Preview',
                    onclick: () => window.open(autobumpPreviewUrl(ab), '_blank'),
                }, 'Preview'),
                helpTip(HELP.autobumpPreview)),
            el('div', { class: 'sv-grid sv-autobump-grid' },
                field('Title', textInput(ab, 'title', { required: true }), HELP.autobumpTitle, true),
                field('Subtitle', textInput(ab, 'subtitle', { placeholder: 'optional' }), HELP.autobumpSubtitle),
                field('Style', selectInput(ab, 'variation', AUTOBUMP_STYLES, { emptyLabel: 'modern (default)' }), HELP.autobumpStyle),
                field('Use for', selectInput(ab, 'strategy', AUTOBUMP_STRATEGIES, { emptyLabel: 'Start and end (default)' }), HELP.autobumpStrategy),
                field('Detail line 1', textInput(ab, 'detail1'), HELP.autobumpDetail),
                field('Detail line 2', textInput(ab, 'detail2'), HELP.autobumpDetail),
                field('Detail line 3', textInput(ab, 'detail3'), HELP.autobumpDetail),
                field('Music', el('span', {}, textInput(ab, 'bg_music', { list: music.id, placeholder: 'none' }), music.list), HELP.autobumpMusic),
                field('Length', numberInput(ab, 'duration', { min: 1, placeholder: '7' }), HELP.autobumpLength),
                field('Whole-break chance', numberInput(ab, 'fill_break', { min: 0, max: 1, placeholder: '0' }), HELP.autobumpFill),
                field('Text colour', textInput(ab, 'fg_color', { placeholder: '#ffffff' }), HELP.autobumpColor),
                field('Background colour', textInput(ab, 'bg_color', { placeholder: '#000000' }), HELP.autobumpColor)),
            el('details', { class: 'sv-more' },
                el('summary', {}, 'More autobump options'),
                el('div', { class: 'sv-grid sv-autobump-grid' },
                    field('Background image', textInput(ab, 'bg', { placeholder: 'https://...' }), HELP.autobumpBackground),
                    field('Background video', textInput(ab, 'bg_video', { placeholder: 'file name, path or URL' }), HELP.autobumpVideo),
                    field('Video loops', numberInput(ab, 'bg_video_loop_count', { integer: true, min: 1, placeholder: '1' }), HELP.autobumpLoops),
                    field('Text position', selectInput(ab, 'text_position', TEXT_POSITIONS, { emptyLabel: 'style default' }), HELP.autobumpTextPosition),
                    field('Text delay', numberInput(ab, 'text_delay', { min: 0, placeholder: '0' }), [HELP.autobumpTextTiming, 'Wait before the text appears.']),
                    field('Text fade in', numberInput(ab, 'text_fade_in', { min: 0 }), [HELP.autobumpTextTiming, 'How long the text takes to fade in.']),
                    field('Text fade out', numberInput(ab, 'text_fade_out', { min: 0 }), [HELP.autobumpTextTiming, 'How long the text takes to fade out.']),
                    field('Hide text before end', numberInput(ab, 'text_hide_before_end', { min: 0 }), [HELP.autobumpTextTiming, 'How long before the autobump ends that the text is fully hidden.']),
                    field('Custom CSS', textInput(ab, 'css', { placeholder: 'https://...' }), HELP.autobumpCss)),
                el('div', { class: 'sv-row' }, checkbox(ab, 'bg_video_audio', 'Use video sound', { help: HELP.autobumpVideoAudio }))));
    }

    function setOffAirMode(mode) {
        if (mode === 'autobump') {
            if (conf.off_air_video) stashedOffAirVideo = conf.off_air_video;
            delete conf.off_air_video;
            if (!conf.off_air_autobump) {
                conf.off_air_autobump = { title: (conf.autobump && conf.autobump.title) || defaultAutobumpTitle() };
            }
        } else {
            delete conf.off_air_autobump;
            conf.off_air_video = stashedOffAirVideo || DEFAULT_MEDIA.off_air_video;
        }
        changed(true);
    }

    function offAirAutobumpFields() {
        if (conf.autobump) return el('p', { class: 'sv-note-plain' }, HELP.offAirAutobumpShared);
        const ab = conf.off_air_autobump;
        const music = musicDatalist();
        return el('div', { class: 'sv-grid sv-autobump-grid' },
            field('Off-air title', textInput(ab, 'title', { required: true }), HELP.autobumpTitle, true),
            field('Off-air style', selectInput(ab, 'variation', AUTOBUMP_STYLES, { emptyLabel: 'modern (default)' }), HELP.autobumpStyle),
            field('Off-air music', el('span', {}, textInput(ab, 'bg_music', { list: music.id, placeholder: 'none' }), music.list), HELP.autobumpMusic));
    }

    function mediaSection() {
        const offAirMode = offAirAutobumpActive(conf) ? 'autobump' : 'video';
        const offAirRequired = hasOffAirHours(conf) && !conf.off_air_image && offAirMode === 'video';
        const signOffRequired = usesSignOff(conf);

        const mediaField = (key, label, hint, required) => field(label,
            el('span', { class: 'sv-media-row' },
                textInput(conf, key, { placeholder: DEFAULT_MEDIA[key], required, redrawOnCommit: true }),
                conf[key] === DEFAULT_MEDIA[key] ? null : el('button', {
                    class: 'pure-button sv-small',
                    onclick: (e) => {
                        e.preventDefault();
                        conf[key] = DEFAULT_MEDIA[key];
                        changed(true);
                    },
                }, 'Use default')),
            hint, required);

        const offAirHelp = conf.off_air_image ? [HELP.offAir, HELP.offAirCovered] : HELP.offAir;
        const modeOption = (value, label) => el('label', { class: 'sv-check' },
            el('input', { type: 'radio', name: 'sv-offair-mode', checked: offAirMode === value, onchange: () => setOffAirMode(value) }),
            el('span', {}, label));

        return section('Off-air and filler media', null,
            el('div', { class: 'sv-row sv-offair-mode' },
                el('span', { class: 'sv-label' }, 'Off-air hours show', helpTip(HELP.offAirMode)),
                modeOption('video', 'Video'),
                modeOption('autobump', 'Autobump')),
            offAirMode === 'autobump' ? offAirAutobumpFields() : null,
            el('div', { class: 'sv-grid sv-media-grid' },
                offAirMode === 'video' ? mediaField('off_air_video', 'Off-air video', offAirHelp, offAirRequired) : null,
                mediaField('sign_off_video', 'Sign-off video', HELP.signOff, signOffRequired),
                mediaField('be_right_back_media', 'Be right back media', HELP.brb, false)));
    }

    function loopSection() {
        return section('Loop', null,
            el('div', { class: 'sv-grid' }, contentDirField(conf)),
            el('div', { class: 'sv-row' },
                checkbox(conf, 'shuffle_loop', 'Shuffle', { help: HELP.shuffle })));
    }

    function webSection() {
        const current = conf.web_url || '';
        const preset = WEB_PRESETS.find((p) => current.split('?')[0] === p.url);
        const urlInput = textInput(conf, 'web_url', { placeholder: 'http://...', redrawOnCommit: true });
        const presetSelect = el('select', {
            class: 'sv-input',
            onchange: (e) => {
                if (!e.target.value) return;
                conf.web_url = e.target.value;
                changed(true);
            },
        },
        el('option', { value: '' }, 'Custom URL'),
        WEB_PRESETS.map((p) => el('option', { value: p.url }, p.label)));
        presetSelect.value = preset ? preset.url : '';

        return section('Web page', null,
            el('div', { class: 'sv-grid' },
                field('Page', presetSelect, HELP.webPage),
                field('URL', urlInput),
                field('Refresh interval', numberInput(conf, 'refresh_interval', { min: 0, placeholder: '0' }), HELP.refresh)));
    }

    function templates() {
        return conf.day_templates || {};
    }

    function hasInlineDays() {
        return DAYS.some((d) => conf[d] !== null && typeof conf[d] === 'object');
    }

    function daysUsing(name) {
        return DAYS.filter((d) => conf[d] === name);
    }

    function templateReferences(name) {
        const refs = daysUsing(name).map(capitalize);
        for (const [range, value] of Object.entries(conf.date_overrides || {})) {
            if (value === name) refs.push(`date override "${range}"`);
        }
        for (const [range, week] of Object.entries(conf.week_overrides || {})) {
            if (!week || typeof week !== 'object') continue;
            for (const [day, value] of Object.entries(week)) {
                if (value === name) refs.push(`week override "${range}" (${day})`);
            }
        }
        return refs;
    }

    function renameReferences(oldName, newName) {
        DAYS.forEach((d) => { if (conf[d] === oldName) conf[d] = newName; });
        for (const range of Object.keys(conf.date_overrides || {})) {
            if (conf.date_overrides[range] === oldName) conf.date_overrides[range] = newName;
        }
        for (const week of Object.values(conf.week_overrides || {})) {
            if (!week || typeof week !== 'object') continue;
            for (const day of Object.keys(week)) {
                if (week[day] === oldName) week[day] = newName;
            }
        }
    }

    function renameKey(obj, oldKey, newKey) {
        const entries = Object.entries(obj).map(([k, v]) => [k === oldKey ? newKey : k, v]);
        Object.keys(obj).forEach((k) => delete obj[k]);
        entries.forEach(([k, v]) => { obj[k] = v; });
    }

    function capitalize(s) {
        return s.charAt(0).toUpperCase() + s.slice(1);
    }

    function askTemplateName(message, initial = '') {
        const name = prompt(message, initial);
        if (name === null) return null;
        const trimmed = name.trim();
        if (!trimmed) return null;
        if (templates()[trimmed]) {
            alert(`A template named "${trimmed}" already exists.`);
            return null;
        }
        return trimmed;
    }

    function scheduleSections() {
        const names = Object.keys(templates());
        if (names.length && (!selectedTemplate || !templates()[selectedTemplate])) {
            selectedTemplate = names[0];
            selectedHour = null;
        }
        return [dayTemplatesSection(names), hasInlineDays() ? inlineScheduleSection() : weeklyScheduleSection(names)];
    }

    function dayTemplatesSection(names) {
        if (names.length === 0) {
            return section('Day templates', HELP.dayTemplates,
                el('p', { class: 'sv-note' }, 'This station has no day templates yet. A day template holds the hourly rules for one kind of day.'),
                el('button', {
                    class: 'pure-button pure-button-primary',
                    onclick: () => {
                        conf.day_templates = { daily: {} };
                        DAYS.forEach((d) => { if (!conf[d]) conf[d] = 'daily'; });
                        selectedTemplate = 'daily';
                        changed(true);
                    },
                }, 'Create first template'));
        }

        return section('Day templates', HELP.dayTemplates,
            el('div', { class: 'sv-schedule' }, templateList(names), templateEditor()));
    }

    function weeklyScheduleSection(names) {
        if (names.length === 0) {
            return section('Weekly schedule', HELP.weekly,
                el('p', { class: 'sv-hint' }, 'Create a day template above, then assign it to days here.'));
        }

        const assignSelect = el('select', { class: 'sv-input sv-input-inline' },
            names.map((n) => el('option', { value: n }, n)));
        assignSelect.value = selectedTemplate;
        const assignTo = (days) => {
            days.forEach((d) => { conf[d] = assignSelect.value; });
            changed(true);
        };

        return section('Weekly schedule', HELP.weekly,
            el('div', { class: 'sv-week-days' },
                DAYS.map((day) => {
                    const select = el('select', {
                        class: 'sv-input',
                        onchange: (e) => {
                            assign(conf, day, e.target.value);
                            changed(true);
                        },
                    },
                    conf[day] ? null : el('option', { value: '' }, '(none)'),
                    names.map((n) => el('option', { value: n }, n)),
                    conf[day] && !names.includes(conf[day]) ? el('option', { value: conf[day] }, `${conf[day]} (missing)`) : null);
                    select.value = conf[day] || '';
                    return el('label', { class: 'sv-day' + (conf[day] ? '' : ' sv-day-missing') },
                        el('span', { class: 'sv-label' }, capitalize(day)), select);
                })),
            el('div', { class: 'sv-row sv-week-actions' },
                el('span', { class: 'sv-hint' }, 'Assign'),
                assignSelect,
                el('span', { class: 'sv-hint' }, 'to'),
                el('button', { class: 'pure-button sv-small', onclick: () => assignTo(WEEKDAYS) }, 'Weekdays'),
                el('button', { class: 'pure-button sv-small', onclick: () => assignTo(WEEKEND) }, 'Weekend'),
                el('button', { class: 'pure-button sv-small', onclick: () => assignTo(DAYS) }, 'Every day')));
    }

    function templateList(names) {
        const actions = {
            add() {
                const name = askTemplateName('New template name:');
                if (!name) return;
                conf.day_templates[name] = {};
                selectedTemplate = name;
                selectedHour = null;
                changed(true);
            },
            duplicate() {
                const name = askTemplateName(`Name for the copy of "${selectedTemplate}":`, `${selectedTemplate}_copy`);
                if (!name) return;
                conf.day_templates[name] = structuredClone(templates()[selectedTemplate]);
                selectedTemplate = name;
                changed(true);
            },
            rename() {
                const name = askTemplateName(`Rename "${selectedTemplate}" to:`, selectedTemplate);
                if (!name) return;
                renameKey(conf.day_templates, selectedTemplate, name);
                renameReferences(selectedTemplate, name);
                selectedTemplate = name;
                changed(true);
            },
            remove() {
                const refs = templateReferences(selectedTemplate);
                if (refs.length) {
                    alert(`"${selectedTemplate}" is still used by:\n\n${refs.join('\n')}\n\nAssign something else first.`);
                    return;
                }
                if (!confirm(`Delete template "${selectedTemplate}"?`)) return;
                delete conf.day_templates[selectedTemplate];
                selectedTemplate = null;
                selectedHour = null;
                changed(true);
            },
        };

        return el('div', { class: 'sv-templates' },
            el('ul', { class: 'sv-template-list' },
                names.map((name) => {
                    const used = daysUsing(name).map((d) => capitalize(d).slice(0, 3));
                    return el('li', {
                        class: 'sv-template' + (name === selectedTemplate ? ' sv-selected' : ''),
                        onclick: () => {
                            selectedTemplate = name;
                            selectedHour = null;
                            redraw();
                        },
                    },
                    el('span', { class: 'sv-template-name' }, name),
                    el('span', { class: 'sv-template-days' }, used.length ? used.join(' ') : 'unused'));
                })),
            el('div', { class: 'sv-template-actions' },
                el('button', { class: 'pure-button sv-small', onclick: actions.add }, 'New'),
                el('button', { class: 'pure-button sv-small', onclick: actions.duplicate }, 'Duplicate'),
                el('button', { class: 'pure-button sv-small', onclick: actions.rename }, 'Rename'),
                el('button', { class: 'pure-button sv-small sv-danger', onclick: actions.remove }, 'Delete')));
    }

    function tagList(slot) {
        if (!slot || slot.tags === undefined || slot.tags === null || slot.tags === '') return [];
        return Array.isArray(slot.tags) ? slot.tags : [slot.tags];
    }

    function setTags(slot, tags) {
        if (tags.length === 0) delete slot.tags;
        else slot.tags = tags.length === 1 ? tags[0] : tags;
        if (tags.length < 2) delete slot.random_tags;
    }

    function slotMode(slot, hourKey) {
        if (tagList(slot).length) return 'tags';
        if (slot && slot.continued) return 'continued';
        if (pendingTagMode && hourKey !== null && hourKey === selectedHour) return 'tags';
        return 'offair';
    }

    function describeSlot(slot) {
        const tags = tagList(slot);
        if (tags.length === 1) return `Pick from ${tags[0]}`;
        if (tags.length > 1) {
            return slot.random_tags
                ? `Pick randomly from: ${tags.join(', ')}`
                : `Split the hour: ${tags.join(' / ')}`;
        }
        if (slot && slot.continued) return 'Same tags as the hour above';
        if (slot && slot.event === 'signoff') return 'Sign-off, then off air';
        return 'Off air (no rule)';
    }

    function slotBadges(slot) {
        if (!slot) return [];
        const badges = [];
        if (slot.start_bump) badges.push('start bump');
        if (slot.end_bump) badges.push('end bump');
        if (slot.sequence) badges.push(`sequence: ${slot.sequence}`);
        if (slot.marathon) badges.push('marathon');
        if (slot.overrides) badges.push(`overrides: ${slot.overrides}`);
        if (slot.break_strategy) badges.push(`breaks: ${slot.break_strategy}`);
        if (slot.schedule_increment !== undefined) badges.push(`every ${slot.schedule_increment}m`);
        if (slot.bump_dir) badges.push('custom bumps');
        if (slot.commercial_dir) badges.push('custom commercials');
        const extra = Object.keys(slot).filter((k) => !SLOT_KEYS.has(k)).length;
        if (extra) badges.push(`${extra} more in JSON`);
        return badges;
    }

    function missingFolderTags(slot) {
        return tagList(slot).filter((tag) => {
            if (typeof tag !== 'string') return false;
            if (tag.startsWith('/')) return checkFolder(tag) === false;
            if (!conf.content_dir) return false;
            if (tag.includes('/')) return checkFolder(`${conf.content_dir}/${tag}`) === false;
            return Array.isArray(contentFolders.folders) && !contentFolders.folders.includes(tag);
        });
    }

    function hourWarnings(template, hourKey, templateName) {
        const slot = template[hourKey];
        const warnings = [];
        const missing = missingFolderTags(slot);
        if (missing.length) warnings.push(`No folder for: ${missing.join(', ')}`);
        if (slot && slot.continued && !tagList(slot).length && !hasTaggedHourAbove(template, hourKey)) {
            warnings.push(daysUsing(templateName).includes('monday')
                ? 'Nothing above to continue - this fails to load on Monday.'
                : 'Nothing above in this template - it continues the previous day\'s last tags.');
        }
        return warnings;
    }

    function hasTaggedHourAbove(template, hourKey) {
        for (const hour of OPERATING_HOURS) {
            if (String(hour) === hourKey) return false;
            if (tagList(template[String(hour)]).length) return true;
        }
        return false;
    }

    function hourLabel(hour) {
        return `${String(hour).padStart(2, '0')}:00`;
    }

    function templateEditor() {
        const template = templates()[selectedTemplate];
        const rows = OPERATING_HOURS.map((hour) => {
            const key = String(hour);
            const slot = template[key];
            const warnings = hourWarnings(template, key, selectedTemplate);
            const mode = slot ? slotMode(slot, key) : 'offair';
            return el('tr', {
                class: `sv-hour sv-mode-${mode}` + (key === selectedHour ? ' sv-selected' : ''),
                onclick: () => {
                    if (selectedHour !== key) pendingTagMode = false;
                    selectedHour = key;
                    redraw();
                },
            },
            el('td', { class: 'sv-hour-label' }, hourLabel(hour)),
            el('td', {},
                el('div', { class: 'sv-hour-summary' }, describeSlot(slot)),
                el('div', { class: 'sv-badges' },
                    slotBadges(slot).map((b) => el('span', { class: 'sv-badge' }, b)),
                    warnings.map((w) => el('span', { class: 'sv-badge sv-warning' }, w)))),
            el('td', { class: 'sv-hour-actions' }, hourActions(template, key)));
        });

        return el('div', { class: 'sv-template-editor' },
            el('div', { class: 'sv-hours-wrap' },
                el('div', { class: 'sv-label' }, `Hours in "${selectedTemplate}" (broadcast day starts at 06:00)`),
                el('table', { class: 'sv-hours' }, el('tbody', {}, rows))),
            selectedHour !== null ? slotPanel(template, selectedHour) : el('div', { class: 'sv-slot-panel sv-slot-empty' }, 'Select an hour to edit its rule.'));
    }

    function hourActions(template, key) {
        const stop = (fn) => (e) => { e.stopPropagation(); fn(); };
        return [
            el('button', {
                class: 'pure-button sv-tiny',
                title: 'Copy this hour',
                disabled: !template[key],
                onclick: stop(() => { slotClipboard = structuredClone(template[key]); redraw(); }),
            }, 'Copy'),
            el('button', {
                class: 'pure-button sv-tiny',
                title: 'Paste the copied hour here',
                disabled: !slotClipboard,
                onclick: stop(() => { template[key] = structuredClone(slotClipboard); changed(true); }),
            }, 'Paste'),
            el('button', {
                class: 'pure-button sv-tiny',
                title: 'Remove this hour\'s rule',
                disabled: !template[key],
                onclick: stop(() => { delete template[key]; pendingTagMode = false; changed(true); }),
            }, 'Clear'),
        ];
    }

    function slotFor(template, key) {
        if (!template[key]) template[key] = {};
        return template[key];
    }

    function dropIfEmpty(template, key) {
        if (template[key] && Object.keys(template[key]).length === 0) delete template[key];
    }

    function slotPanel(template, key) {
        const existing = template[key];
        const mode = existing ? slotMode(existing, key) : (pendingTagMode ? 'tags' : 'offair');

        const setMode = (next) => {
            const slot = slotFor(template, key);
            pendingTagMode = next === 'tags';
            if (next !== 'tags') {
                delete slot.tags;
                delete slot.random_tags;
            }
            if (next === 'continued') slot.continued = true;
            else delete slot.continued;
            if (next !== 'offair' && slot.event === 'signoff') delete slot.event;
            dropIfEmpty(template, key);
            changed(true);
        };

        const modeOption = (value, label, help) => el('label', { class: 'sv-check' },
            el('input', { type: 'radio', name: 'sv-slot-mode', checked: mode === value, onchange: () => setMode(value) }),
            el('span', {}, label),
            helpTip(help));

        const parts = [
            el('div', { class: 'sv-slot-title' }, `${hourLabel(Number(key))} in "${selectedTemplate}"`),
            el('div', { class: 'sv-modes' },
                modeOption('tags', 'Pick from tags', HELP.modeTags),
                modeOption('continued', 'Same tags as the hour above', HELP.modeContinued),
                modeOption('offair', 'Off air', HELP.modeOffAir)),
        ];

        if (mode === 'tags') {
            parts.push(tagEditor(template, key));
        } else if (mode === 'offair') {
            const slot = existing || {};
            parts.push(el('label', { class: 'sv-check' },
                el('input', {
                    type: 'checkbox',
                    checked: slot.event === 'signoff',
                    onchange: (e) => {
                        const target = slotFor(template, key);
                        assign(target, 'event', e.target.checked ? 'signoff' : '');
                        dropIfEmpty(template, key);
                        changed(true);
                    },
                }),
                el('span', {}, 'Play the sign-off video'),
                helpTip(HELP.signOffHour)));
        }

        if (mode !== 'offair' && existing) {
            parts.push(slotDetails(template, key));
        }

        const editableKeys = mode === 'offair' ? new Set(['event']) : SLOT_KEYS;
        const unknown = existing
            ? Object.keys(existing).filter((k) => !editableKeys.has(k)
                || (k === 'event' && (mode !== 'offair' || existing.event !== 'signoff')))
            : [];
        if (unknown.length) {
            parts.push(el('div', { class: 'sv-unknown' },
                el('div', { class: 'sv-label' }, 'Other settings (edit in JSON)'),
                unknown.map((k) => el('div', { class: 'sv-unknown-row' },
                    el('code', {}, k), ': ', el('code', {}, JSON.stringify(existing[k]))))));
        }

        return el('div', { class: 'sv-slot-panel' }, parts);
    }

    function breakFolderNames() {
        const names = new Set(['next']);
        const contentPrefix = conf.content_dir ? `${conf.content_dir.replace(/\/+$/, '')}/` : null;
        const visit = (node) => {
            if (!node || typeof node !== 'object') return;
            for (const [key, value] of Object.entries(node)) {
                if ((key === 'bump_dir' || key === 'commercial_dir') && typeof value === 'string') {
                    const name = value.replace(/\/+$/, '');
                    names.add(contentPrefix && name.startsWith(contentPrefix) ? name.slice(contentPrefix.length) : name);
                } else {
                    visit(value);
                }
            }
        };
        visit(conf);
        return names;
    }

    function tagChoices() {
        if (!Array.isArray(contentFolders.folders)) return contentFolders.folders;
        const notTags = breakFolderNames();
        return contentFolders.folders.filter((f) => !notTags.has(f));
    }

    function tagEditor(template, key) {
        const slot = template[key] || {};
        const tags = tagList(slot);
        const missing = missingFolderTags(slot);
        const choices = tagChoices();

        const addTag = (value) => {
            const trimmed = value.trim();
            if (!trimmed || tags.includes(trimmed)) return;
            setTags(slotFor(template, key), [...tags, trimmed]);
            pendingTagMode = false;
            changed(true);
        };

        const removeTag = (tag) => {
            setTags(slotFor(template, key), tags.filter((t) => t !== tag));
            pendingTagMode = true;
            dropIfEmpty(template, key);
            changed(true);
        };

        let available;
        if (!conf.content_dir) {
            available = el('span', { class: 'sv-hint' }, 'Set the content folder to see what it contains.');
        } else if (choices === undefined) {
            available = el('span', { class: 'sv-hint' }, `Loading folders in ${conf.content_dir}...`);
        } else if (choices === null) {
            available = el('span', { class: 'sv-hint sv-warning-text' }, `Couldn't read ${conf.content_dir} - check the content folder.`);
        } else {
            const unused = choices.filter((f) => !tags.includes(f));
            available = unused.length
                ? el('div', { class: 'sv-choice-list' },
                    unused.map((f) => el('button', { class: 'sv-choice', title: `Add ${f}`, onclick: () => addTag(f) }, `+ ${f}`)))
                : el('span', { class: 'sv-hint' }, choices.length ? 'All folders are selected.' : `No folders in ${conf.content_dir}.`);
        }

        const otherInput = el('input', {
            type: 'text',
            class: 'sv-input',
            placeholder: 'e.g. sitcoms/friends or /mnt/media/cartoons',
            onkeydown: (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addTag(e.target.value);
                }
            },
        });

        return el('div', { class: 'sv-tags' },
            el('div', { class: 'sv-label' }, 'Selected tags', helpTip(HELP.tags)),
            el('div', { class: 'sv-chips' },
                tags.length === 0 ? el('span', { class: 'sv-hint' }, 'None yet - pick folders below.') : null,
                tags.map((tag) => el('span', { class: 'sv-chip' + (missing.includes(tag) ? ' sv-warning' : '') },
                    tag,
                    el('button', { class: 'sv-chip-remove', title: 'Remove', onclick: () => removeTag(tag) }, '×')))),
            tags.length > 1 ? checkbox(slot, 'random_tags', 'Pick a random tag each time', { help: HELP.randomTags }) : null,
            el('div', { class: 'sv-label sv-choices-label' }, `Folders in ${conf.content_dir || 'the content folder'}`),
            available,
            el('details', { class: 'sv-other-tag' },
                el('summary', {}, 'Other tag (subfolder or absolute path)'),
                el('div', { class: 'sv-row' },
                    otherInput,
                    el('button', { class: 'pure-button sv-small', onclick: () => addTag(otherInput.value) }, 'Add'))));
    }

    function slotDetails(template, key) {
        const slot = template[key];
        const marathonOn = !!slot.marathon;
        const overrideNames = Object.keys(conf.slot_overrides || {});

        const marathonToggle = el('label', { class: 'sv-check' },
            el('input', {
                type: 'checkbox',
                checked: marathonOn,
                onchange: (e) => {
                    if (e.target.checked) slot.marathon = { chance: 0.1, count: 3 };
                    else delete slot.marathon;
                    changed(true);
                },
            }),
            el('span', {}, 'Marathon'),
            helpTip(HELP.marathon));

        return el('div', { class: 'sv-details' },
            el('div', { class: 'sv-grid' },
                field('Start bump', textInput(slot, 'start_bump', { placeholder: 'path in content folder, or absolute' }), HELP.startBump),
                field('End bump', textInput(slot, 'end_bump', { placeholder: 'path in content folder, or absolute' }), HELP.endBump),
                field('Break strategy', selectInput(slot, 'break_strategy', BREAK_STRATEGIES, { emptyLabel: 'station default', redrawOnCommit: true }), HELP.slotBreakStrategy),
                field('Schedule increment', numberInput(slot, 'schedule_increment', {
                    integer: true, step: '5', min: 0, placeholder: String(conf.schedule_increment ?? 30), redrawOnCommit: true,
                }), HELP.slotIncrement),
                contentSubfolderField(slot, 'commercial_dir', 'Commercial folder', HELP.slotCommercials, conf.commercial_dir || 'station default'),
                contentSubfolderField(slot, 'bump_dir', 'Bump folder', HELP.slotBumps, conf.bump_dir || 'station default'),
                overrideNames.length || slot.overrides
                    ? field('Slot override', selectInput(slot, 'overrides', overrideNames, { emptyLabel: 'none', redrawOnCommit: true }),
                        HELP.slotOverride)
                    : null),
            el('div', { class: 'sv-subsection' },
                el('div', { class: 'sv-label' }, 'Sequence', helpTip(HELP.sequence)),
                el('div', { class: 'sv-grid' },
                    field('Sequence name', textInput(slot, 'sequence', { placeholder: 'e.g. show-season1', redrawOnCommit: true })),
                    field('Start', numberInput(slot, 'sequence_start', { placeholder: '0', max: 1 }), HELP.sequenceStart),
                    field('End', numberInput(slot, 'sequence_end', { placeholder: '1', min: 0, max: 1 }), HELP.sequenceEnd))),
            el('div', { class: 'sv-subsection' },
                marathonToggle,
                marathonOn ? el('div', { class: 'sv-grid' },
                    field('Chance', numberInput(slot.marathon, 'chance', { min: 0, max: 1 }), HELP.marathonChance),
                    field('Hours', numberInput(slot.marathon, 'count', { integer: true, min: 1 }), HELP.marathonHours),
                    field('Only during', textInput(slot.marathon, 'hint', { placeholder: 'e.g. October 15 - October 31' }), HELP.marathonWhen)) : null));
    }

    function inlineScheduleSection() {
        const resolve = (day) => (typeof conf[day] === 'string' ? templates()[conf[day]] : conf[day]) || {};
        const header = el('tr', {}, el('th', {}, ''), DAYS.map((d) => el('th', {}, capitalize(d).slice(0, 3))));
        const rows = OPERATING_HOURS.map((hour) => el('tr', {},
            el('td', { class: 'sv-hour-label' }, hourLabel(hour)),
            DAYS.map((d) => {
                const slot = resolve(d)[String(hour)];
                return el('td', { class: `sv-mode-${slot ? slotMode(slot, null) : 'offair'}` }, slot ? describeSlot(slot) : '');
            })));

        return section('Weekly schedule', HELP.weekly,
            el('div', { class: 'sv-note' },
                'This station writes some days out directly instead of using day templates, so the weekly schedule is read-only here. ' +
                'To edit it visually, move each day into "day_templates" in the JSON tab and set the day to the template name.'),
            el('div', { class: 'sv-week-table-wrap' },
                el('table', { class: 'sv-week-table' }, el('thead', {}, header), el('tbody', {}, rows))));
    }

    window.fs42StationVisual = { render, supports, orderStationKeys, missingMedia };
})();
