(() => {
	'use strict';

	const params = new URLSearchParams(window.location.search);
	const channelNumber = Number.parseInt(params.get('channel'), 10);
	const resolution = params.get('resolution');
	const app = document.getElementById('app');
	if (resolution === '480i') {
		app.classList.add('resolution-480i');
	}
	if (resolution === '1080i') {
		app.classList.add('resolution-1080i');
	}

	const stationTitle = document.getElementById('station-title');
	const channelLabel = document.getElementById('channel-number');
	const railsElement = document.getElementById('rails');
	const hero = document.getElementById('hero');
	const heroArt = document.getElementById('hero-art');
	const heroKicker = document.getElementById('hero-kicker');
	const heroTitle = document.getElementById('hero-title');
	const heroMeta = document.getElementById('hero-meta');
	const heroDescription = document.getElementById('hero-description');
	const heroAction = document.getElementById('hero-action');
	const message = document.getElementById('message');
	const loadingStationName = document.getElementById('loading-station-name');
	const modal = document.getElementById('details-modal');
	if (resolution === '480i') modal.classList.add('resolution-480i');
	if (resolution === '1080i') modal.classList.add('resolution-1080i');
	const detailsClose = document.getElementById('details-close');
	const detailsPoster = document.getElementById('details-poster');
	const detailsType = document.getElementById('details-type');
	const detailsShowName = document.getElementById('details-show-name');
	const detailsTitle = document.getElementById('details-title');
	const detailsMeta = document.getElementById('details-meta');
	const detailsDescription = document.getElementById('details-description');
	const detailsPlay = document.getElementById('details-play');
	const detailsHelp = document.getElementById('details-help');
	const detailsEpisodeSidebar = document.getElementById('details-episode-sidebar');
	const detailsSeasonTitle = document.getElementById('details-season-title');
	const detailsSeasonEpisodes = document.getElementById('details-season-episodes');
	const seasonTabs = document.getElementById('season-tabs');
	const episodeList = document.getElementById('episode-list');
	const libraryNavItems = Array.from(document.querySelectorAll('[data-library-filter]'));
	const libraryToolbar = document.getElementById('library-toolbar');
	const movieSearch = document.getElementById('movie-search');

	let allRows = [];
	let rows = [];
	let tmdbMovieGenres = [];
	let rowIndex = 0;
	let itemIndexes = [];
	let libraryFilter = 'all';
	let movieSearchQuery = '';
	let tmdbGenresLoading = false;
	let libraryNavActive = false;
	let libraryNavIndex = 0;
	let selecting = false;
	let openShow = null;
	let detailItem = null;
	let seasonIndex = 0;
	let episodeIndex = 0;

	function escapeHtml(value) {
		return String(value ?? '')
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;')
			.replaceAll('"', '&quot;')
			.replaceAll("'", '&#039;');
	}

	function metadataParts(item) {
		const parts = [];
		if (item.type === 'episode') {
			if (item.show_title) parts.push(escapeHtml(item.show_title));
			parts.push(`Season ${escapeHtml(item.season ?? 0)} · Episode ${escapeHtml(item.episode ?? 0)}`);
		}
		if (item.year || item.info) parts.push(escapeHtml(item.year || item.info));
		if (item.content_rating) parts.push(`<span class="rating">${escapeHtml(item.content_rating)}</span>`);
		const tmdbRating = Number(item.tmdb_rating);
		if (Number.isFinite(tmdbRating) && tmdbRating > 0) parts.push(`TMDB ★ ${tmdbRating.toFixed(1)}`);
		if (item.type === 'show') {
			const count = (item.seasons || []).reduce((sum, season) => sum + season.episodes.length, 0);
			parts.push(`${item.seasons?.length || 0} season${item.seasons?.length === 1 ? '' : 's'}`);
			parts.push(`${count} episode${count === 1 ? '' : 's'}`);
		}
		if (item.genres?.length) parts.push(item.genres.slice(0, 3).map(escapeHtml).join(' · '));
		return parts;
	}

	function currentItem() {
		return rows[rowIndex]?.items[itemIndexes[rowIndex] || 0] || null;
	}

	function setImage(element, url, alt = '') {
		if (url) {
			element.src = url;
			element.alt = alt;
		} else {
			element.removeAttribute('src');
			element.alt = '';
		}
	}

	function updateHero() {
		const row = rows[rowIndex];
		const item = currentItem();
		if (!row || !item) return;
		heroKicker.textContent = item.type === 'show' ? 'Series' : 'Film';
		heroTitle.textContent = item.title;
		heroMeta.innerHTML = metadataParts(item).join('<span>•</span>');
		heroDescription.textContent = item.description || `Browse ${row.title}`;
		heroAction.textContent = item.type === 'show' ? '▶ Browse episodes' : 'View details';
		setImage(heroArt, item.image_url, '');
	}

	function renderCard(item, targetRow, targetItem) {
		const cardDisplayTitle = item.tmdb_title || item.title;
		const card = document.createElement('article');
		card.className = 'media-card';
		card.dataset.row = targetRow;
		card.dataset.item = targetItem;
		card.setAttribute('role', 'option');
		card.setAttribute('aria-label', cardDisplayTitle);
		if (item.image_url) {
			const image = document.createElement('img');
			image.src = item.image_url;
			image.alt = '';
			image.loading = 'lazy';
			image.addEventListener('error', () => image.remove());
			card.appendChild(image);
		} else {
			const fallback = document.createElement('div');
			fallback.className = 'fallback';
			fallback.textContent = cardDisplayTitle;
			card.appendChild(fallback);
		}
		const label = document.createElement('div');
		label.className = 'card-label';
		const cardTitle = document.createElement('span');
		cardTitle.className = 'card-title';
		cardTitle.textContent = cardDisplayTitle;
		label.appendChild(cardTitle);
		const tmdbRating = Number(item.tmdb_rating);
		if (Number.isFinite(tmdbRating) && tmdbRating > 0) {
			const rating = document.createElement('span');
			rating.className = 'card-tmdb';
			rating.textContent = `TMDB ★ ${tmdbRating.toFixed(1)}`;
			label.appendChild(rating);
		}
		card.appendChild(label);
		card.addEventListener('click', () => {
			rowIndex = targetRow;
			itemIndexes[targetRow] = targetItem;
			renderSelection();
			activateSelection();
		});
		return card;
	}

	function refreshCardAt(item, targetRow, targetItem) {
		const card = document.querySelector(
			`.media-card[data-row="${targetRow}"][data-item="${targetItem}"]`,
		);
		if (!item || !card) return;

		const cardDisplayTitle = item.tmdb_title || item.title;
		card.setAttribute('aria-label', cardDisplayTitle);
		const title = card.querySelector('.card-title');
		if (title) title.textContent = cardDisplayTitle;

		let rating = card.querySelector('.card-tmdb');
		const tmdbRating = Number(item.tmdb_rating);
		if (Number.isFinite(tmdbRating) && tmdbRating > 0) {
			if (!rating) {
				rating = document.createElement('span');
				rating.className = 'card-tmdb';
				card.querySelector('.card-label')?.appendChild(rating);
			}
			rating.textContent = `TMDB ★ ${tmdbRating.toFixed(1)}`;
		} else {
			rating?.remove();
		}

		if (item.image_url && !card.querySelector('img')) {
			const image = document.createElement('img');
			image.src = item.image_url;
			image.alt = '';
			image.loading = 'lazy';
			image.addEventListener('error', () => image.remove());
			card.querySelector('.fallback')?.remove();
			card.insertBefore(image, card.querySelector('.card-label'));
		}
	}

	function refreshCard(item) {
		rows.forEach((row, targetRow) => {
			row.items.forEach((candidate, targetItem) => {
				if (candidate === item) refreshCardAt(item, targetRow, targetItem);
			});
		});
	}

	async function enrichMovieFromTmdb(item) {
		try {
			const response = await window.fs42Api.get(
				`media-browser/${channelNumber}/tmdb?title=${encodeURIComponent(item.tmdb_query || item.title)}`,
			);
			const movie = response.movie;
			if (!movie) return;
			item.tmdb_id = movie.tmdb_id;
			item.tmdb_title = movie.title;
			item.tmdb_rating = movie.vote_average;
			if (!item.genres?.length && movie.genres?.length) item.genres = movie.genres;
			if (!item.image_url) item.image_url = movie.poster_url;
			if (!item.description) item.description = movie.overview || '';
			if (!item.year && movie.release_date)
				item.year = movie.release_date.slice(0, 4);
			if (!item.info) item.info = item.year || '';
			refreshCard(item);
			if (currentItem() === item) updateHero();
		} catch (error) {
			console.warn(`TMDB lookup failed for ${item.title}:`, error);
		}
	}

	async function enrichMoviesFromTmdb() {
		tmdbGenresLoading = true;
		if (libraryFilter === 'all') renderTmdbGenreSkeletonRails();
		const movieItems = new Set();
		allRows.forEach((row) => {
			if (row.kind !== 'movies' || row.genreRail) return;
			row.items.forEach((item) => movieItems.add(item));
		});
		const queue = Array.from(movieItems);
		let nextIndex = 0;
		const worker = async () => {
			while (nextIndex < queue.length) {
				await enrichMovieFromTmdb(queue[nextIndex++]);
			}
		};
		await Promise.all(
			Array.from({ length: Math.min(4, queue.length) }, () => worker()),
		);
		tmdbGenresLoading = false;
		allRows = addMovieGenreRows(allRows.filter((row) => !row.genreRail));
		if (libraryFilter === 'all') selectLibrary('all');
	}

	function renderSkeletonRails() {
		railsElement.replaceChildren();
		railsElement.classList.add('skeleton-rails');
		for (let row = 0; row < 3; row += 1) {
			const rail = document.createElement('section');
			rail.className = 'rail skeleton-rail';
			rail.setAttribute('aria-hidden', 'true');
			const title = document.createElement('div');
			title.className = 'skeleton-line';
			const strip = document.createElement('div');
			strip.className = 'card-strip';
			for (let card = 0; card < 7; card += 1) {
				const placeholder = document.createElement('div');
				placeholder.className = 'skeleton-card';
				strip.appendChild(placeholder);
			}
			rail.append(title, strip);
			railsElement.appendChild(rail);
		}
	}

	function renderTmdbGenreSkeletonRails() {
		document.querySelectorAll('.tmdb-genre-skeleton').forEach((rail) => rail.remove());
		if (!tmdbGenresLoading || libraryFilter !== 'all') return;
		const existingGenres = new Set(
			allRows
				.filter((row) => row.genreRail)
				.map((row) => row.title.toLocaleLowerCase()),
		);
		const firstShowIndex = rows.findIndex((row) => row.kind === 'shows');
		const anchor = firstShowIndex >= 0
			? railsElement.querySelector(`.rail[data-row="${firstShowIndex}"]`)
			: null;
		tmdbMovieGenres
			.filter((genre) => !existingGenres.has(genre.toLocaleLowerCase()))
			.forEach((genre) => {
				const rail = document.createElement('section');
				rail.className = 'rail tmdb-genre-skeleton';
				rail.setAttribute('aria-hidden', 'true');
				const title = document.createElement('h2');
				title.textContent = genre;
				const strip = document.createElement('div');
				strip.className = 'card-strip';
				for (let card = 0; card < 7; card += 1) {
					const placeholder = document.createElement('div');
					placeholder.className = 'skeleton-card';
					strip.appendChild(placeholder);
				}
				rail.append(title, strip);
				railsElement.insertBefore(rail, anchor);
			});
	}

	function renderRows() {
		railsElement.replaceChildren();
		railsElement.classList.remove('skeleton-rails');
		rows.forEach((row, targetRow) => {
			const rail = document.createElement('section');
			rail.className = 'rail';
			rail.dataset.row = targetRow;
			const title = document.createElement('h2');
			title.textContent = row.title;
			const strip = document.createElement('div');
			strip.className = 'card-strip';
			strip.setAttribute('role', 'listbox');
			row.items.forEach((item, targetItem) => strip.appendChild(renderCard(item, targetRow, targetItem)));
			rail.append(title, strip);
			railsElement.appendChild(rail);
		});
	}

	function renderLibraryNavigation() {
		libraryNavItems.forEach((item, index) => {
			const selected = item.dataset.libraryFilter === libraryFilter;
			item.classList.toggle('active', selected);
			item.classList.toggle('focused', libraryNavActive && index === libraryNavIndex);
			item.setAttribute('aria-pressed', String(selected));
		});
	}

	function addMovieGenreRows(sourceRows) {
		const genreMap = new Map();
		sourceRows
			.filter((row) => row.kind === 'movies')
			.forEach((row) => {
				row.items.forEach((item) => {
					(item.genres || []).forEach((rawGenre) => {
						String(rawGenre)
							.split(',')
							.map((genre) => genre.trim())
							.filter(Boolean)
							.forEach((genre) => {
								const key = genre.toLocaleLowerCase();
								if (!genreMap.has(key)) genreMap.set(key, { title: genre, items: new Set() });
								genreMap.get(key).items.add(item);
							});
					});
				});
			});
		const genreRows = Array.from(genreMap.entries())
			.map(([key, genre]) => ({
				id: `genre-${key.replace(/[^a-z0-9]+/g, '-')}`,
				kind: 'movies',
				genreRail: true,
				title: genre.title,
				items: Array.from(genre.items).sort((left, right) => left.title.localeCompare(right.title)),
			}))
			.sort((left, right) => left.title.localeCompare(right.title));
		if (!genreRows.length) return sourceRows;
		let insertAt = sourceRows.length;
		for (let index = sourceRows.length - 1; index >= 0; index -= 1) {
			if (sourceRows[index].kind === 'movies') {
				insertAt = index + 1;
				break;
			}
		}
		return [...sourceRows.slice(0, insertAt), ...genreRows, ...sourceRows.slice(insertAt)];
	}

	function selectLibrary(filter) {
		libraryFilter = filter;
		app.classList.toggle('library-grid-view', filter !== 'all');
		app.classList.toggle('movie-grid-view', filter === 'movies');
		libraryToolbar.hidden = filter !== 'movies';
		rows = allRows
			.filter((row) => filter === 'all' || (row.kind === filter && !row.genreRail))
			.map((row) => {
				if (filter !== 'movies' || !movieSearchQuery) return row;
				return {
					...row,
					items: row.items.filter((item) =>
						`${item.title} ${item.tmdb_title || ''}`.toLocaleLowerCase().includes(movieSearchQuery),
					),
				};
			})
			.filter((row) => row.items.length);
		rowIndex = 0;
		itemIndexes = rows.map(() => 0);
		renderLibraryNavigation();
		renderRows();
		if (filter === 'all' && tmdbGenresLoading) renderTmdbGenreSkeletonRails();
		message.hidden = true;
		if (rows.length) {
			renderSelection();
		} else {
			const empty = document.createElement('div');
			empty.className = 'grid-empty';
			empty.textContent = filter === 'movies' ? 'No movies found.' : 'No TV shows found.';
			railsElement.appendChild(empty);
			heroKicker.textContent = 'Library';
			heroTitle.textContent = filter === 'movies' ? 'No movies found' : 'No TV shows found';
			heroMeta.replaceChildren();
			heroDescription.textContent = 'Choose another library section.';
			heroAction.textContent = '';
			heroAction.hidden = true;
			setImage(heroArt, '');
		}
	}

	function moveLibraryNavigation(step) {
		libraryNavIndex = (libraryNavIndex + step + libraryNavItems.length) % libraryNavItems.length;
		renderLibraryNavigation();
	}

	function activateLibraryNavigation() {
		const item = libraryNavItems[libraryNavIndex];
		if (!item) return;
		libraryNavActive = false;
		selectLibrary(item.dataset.libraryFilter);
	}

	libraryNavItems.forEach((item, index) => {
		item.addEventListener('click', () => {
			libraryNavIndex = index;
			libraryNavActive = false;
			selectLibrary(item.dataset.libraryFilter);
		});
	});

	movieSearch.addEventListener('input', () => {
		movieSearchQuery = movieSearch.value.trim().toLocaleLowerCase();
		selectLibrary('movies');
	});

	function typeIntoMovieSearch(key) {
		const value = movieSearch.value;
		const start = movieSearch.selectionStart ?? value.length;
		const end = movieSearch.selectionEnd ?? start;
		let nextValue = value;
		let nextPosition = start;
		if (key === 'Backspace') {
			if (start !== end) nextValue = value.slice(0, start) + value.slice(end);
			else if (start > 0) {
				nextValue = value.slice(0, start - 1) + value.slice(end);
				nextPosition = start - 1;
			}
		} else if (key === 'Delete') {
			nextValue = value.slice(0, start) + value.slice(start === end ? end + 1 : end);
		} else {
			nextValue = value.slice(0, start) + key + value.slice(end);
			nextPosition = start + key.length;
		}
		movieSearch.focus({ preventScroll: true });
		movieSearch.value = nextValue;
		movieSearch.setSelectionRange(nextPosition, nextPosition);
		movieSearch.dispatchEvent(new Event('input', { bubbles: true }));
	}

	function renderSelection() {
		libraryNavActive = false;
		renderLibraryNavigation();
		heroAction.hidden = false;
		document.querySelectorAll('.media-card').forEach((card) => {
			const selected = Number(card.dataset.row) === rowIndex && Number(card.dataset.item) === (itemIndexes[rowIndex] || 0);
			card.classList.toggle('selected', selected);
			card.setAttribute('aria-selected', String(selected));
			if (selected) card.scrollIntoView({ block: 'nearest', inline: 'nearest' });
		});
		if (libraryFilter === 'all')
			document.querySelector(`.rail[data-row="${rowIndex}"]`)?.scrollIntoView({ block: 'nearest' });
		updateHero();
	}

	function moveRow(step) {
		if (!rows.length) return;
		rowIndex = (rowIndex + step + rows.length) % rows.length;
		renderSelection();
	}

	function moveItem(step) {
		const row = rows[rowIndex];
		if (!row?.items.length) return;
		itemIndexes[rowIndex] = ((itemIndexes[rowIndex] || 0) + step + row.items.length) % row.items.length;
		renderSelection();
	}

	function moveGridSelection(step) {
		const selected = document.querySelector('.media-card.selected');
		if (!selected) return false;
		const selectedRect = selected.getBoundingClientRect();
		const selectedX = selectedRect.left + selectedRect.width / 2;
		const selectedY = selectedRect.top + selectedRect.height / 2;
		const candidates = Array.from(document.querySelectorAll('.media-card'))
			.map((card) => {
				const rect = card.getBoundingClientRect();
				return {
					card,
					x: rect.left + rect.width / 2,
					y: rect.top + rect.height / 2,
				};
			})
			.filter((entry) => step < 0 ? entry.y < selectedY - 1 : entry.y > selectedY + 1)
			.sort((left, right) => {
				const leftScore = Math.abs(left.y - selectedY) * 10 + Math.abs(left.x - selectedX);
				const rightScore = Math.abs(right.y - selectedY) * 10 + Math.abs(right.x - selectedX);
				return leftScore - rightScore;
			});
		if (!candidates.length) return false;
		const target = candidates[0].card;
		rowIndex = Number(target.dataset.row);
		itemIndexes[rowIndex] = Number(target.dataset.item);
		renderSelection();
		return true;
	}

	async function playItem(item) {
		if (!item?.video_path || selecting) return;
		selecting = true;
		message.classList.remove('loading');
		message.textContent = `Starting ${item.title}…`;
		message.classList.remove('error');
		message.hidden = false;
		try {
			await window.fs42Api.post(`ppv/${channelNumber}/play_file`, { file_path: item.video_path });
		} catch (error) {
			message.textContent = `Could not play ${item.title}: ${error.detail || error.message || 'Unknown error'}`;
			message.classList.add('error');
			selecting = false;
		}
	}

	let episodeRuntimeObserver;

	async function showEpisodeRuntime(info, episode) {
		if (!episode.runtime_url) return;
		episode.runtimeRequest ??= fetch(episode.runtime_url)
			.then((response) => response.ok ? response.json() : null)
			.catch(() => null);
		const runtime = await episode.runtimeRequest;
		if (Number.isInteger(runtime?.minutes) && runtime.minutes > 0) {
			info.textContent += ` • ${runtime.minutes} min`;
		} else {
			delete episode.runtimeRequest;
		}
	}

	function renderShowDetails() {
		if (!openShow) return;
		detailItem = null;
		modal.classList.remove('item-detail-open', 'episode-detail-open');
		detailsType.textContent = 'SERIES';
		detailsShowName.hidden = true;
		detailsMeta.hidden = false;
		detailsPoster.onerror = null;
		detailsPlay.hidden = true;
		detailsEpisodeSidebar.hidden = true;
		seasonTabs.hidden = false;
		episodeList.hidden = false;
		detailsHelp.hidden = false;
		detailsHelp.textContent = '← → season · ↑ ↓ episode · OK details · Back close';
		const seasons = openShow.seasons || [];
		seasonIndex = Math.max(0, Math.min(seasonIndex, seasons.length - 1));
		const season = seasons[seasonIndex];
		episodeIndex = Math.max(0, Math.min(episodeIndex, Math.max(0, (season?.episodes.length || 1) - 1)));

		detailsTitle.textContent = openShow.title;
		detailsMeta.innerHTML = metadataParts(openShow).join('<span>•</span>');
		detailsDescription.textContent = openShow.description || '';
		detailsDescription.hidden = !detailsDescription.textContent.trim();
		setImage(detailsPoster, openShow.image_url, `${openShow.title} poster`);
		seasonTabs.replaceChildren();
		seasons.forEach((entry, index) => {
			const button = document.createElement('button');
			button.type = 'button';
			button.className = `season-tab${index === seasonIndex ? ' selected' : ''}`;
			button.textContent = entry.title;
			button.addEventListener('click', () => {
				seasonIndex = index;
				episodeIndex = 0;
				renderShowDetails();
			});
			seasonTabs.appendChild(button);
		});

		episodeRuntimeObserver?.disconnect();
		const runtimes = new Map();
		episodeRuntimeObserver = new IntersectionObserver((entries, observer) => {
			for (const { target, isIntersecting } of entries) {
				if (!isIntersecting) continue;
				observer.unobserve(target);
				showEpisodeRuntime(target, runtimes.get(target));
				runtimes.delete(target);
			}
		}, { root: episodeList });
		episodeList.replaceChildren();
		(season?.episodes || []).forEach((episode, index) => {
			const row = document.createElement('div');
			row.className = `episode${index === episodeIndex ? ' selected' : ''}`;
			row.setAttribute('role', 'option');
			row.setAttribute('aria-selected', String(index === episodeIndex));
			row.innerHTML = '<div><div class="episode-title"></div><div class="episode-info"></div></div><div>▶</div>';
			row.querySelector('.episode-title').textContent = `${episode.episode || index + 1}. ${episode.title}`;
			const info = row.querySelector('.episode-info');
			const seasonCode = String(episode.season ?? season?.season ?? 0).padStart(2, '0');
			const episodeCode = String(episode.episode || index + 1).padStart(2, '0');
			info.textContent = `S${seasonCode}E${episodeCode}`;
			if (episode.runtime_url) {
				runtimes.set(info, episode);
				episodeRuntimeObserver.observe(info);
			}
			row.addEventListener('click', () => {
				episodeIndex = index;
				openItemDetails(episode);
			});
			episodeList.appendChild(row);
		});
		episodeList.querySelector('.episode.selected')?.scrollIntoView({ block: 'nearest' });
		seasonTabs.querySelector('.season-tab.selected')?.scrollIntoView({ inline: 'nearest' });
	}

	function renderEpisodeSidebar() {
		const season = openShow?.seasons?.[seasonIndex];
		const episodes = season?.episodes || [];
		detailsSeasonTitle.textContent = season?.title || `Season ${detailItem?.season ?? ''}`;
		detailsSeasonEpisodes.replaceChildren();
		episodes.forEach((episode, index) => {
			const button = document.createElement('button');
			button.type = 'button';
			button.className = `details-season-episode${index === episodeIndex ? ' selected' : ''}`;
			button.innerHTML = '<span class="details-season-episode-number"></span><span class="details-season-episode-title"></span>';
			button.querySelector('.details-season-episode-number').textContent = episode.episode || index + 1;
			button.querySelector('.details-season-episode-title').textContent = episode.title;
			button.addEventListener('click', () => {
				episodeIndex = index;
				openItemDetails(episode);
			});
			detailsSeasonEpisodes.appendChild(button);
		});
		detailsSeasonEpisodes.querySelector('.selected')?.scrollIntoView({ block: 'nearest' });
	}

	function openShowDetails(show) {
		openShow = show;
		detailItem = null;
		seasonIndex = 0;
		episodeIndex = 0;
		modal.hidden = false;
		renderShowDetails();
	}

	function setEpisodeImage(item, tvmazeImage) {
		const images = [tvmazeImage, item.screenshot_url, item.image_url].filter(Boolean);
		function showNextImage() {
			const image = images.shift();
			detailsPoster.onerror = images.length ? showNextImage : null;
			setImage(detailsPoster, image, `${item.title} screenshot`);
		}
		showNextImage();
	}

	async function loadEpisodeMetadata(item) {
		const query = item.tvmaze_query || item.show_title;
		let metadata;
		if (query && Number.isInteger(item.episode) && item.episode > 0) {
			const params = new URLSearchParams({ show: query, season: item.season ?? 0, number: item.episode });
			try {
				metadata = await window.fs42Api.get(`media-browser/${channelNumber}/episode-metadata?${params}`);
			} catch (_) {
				// Local metadata and artwork remain available when TVmaze has no match.
			}
		}
		if (detailItem !== item || modal.hidden) return;
		setEpisodeImage(item, metadata?.image_url);
	}

	function openItemDetails(item) {
		if (!item) return;
		detailItem = item;
		modal.classList.add('item-detail-open');
		const isEpisode = item.type === 'episode' && Boolean(openShow);
		modal.classList.toggle('episode-detail-open', isEpisode);
		modal.hidden = false;
		detailsShowName.hidden = !isEpisode;
		detailsShowName.textContent = isEpisode ? item.show_title || openShow.title : '';
		detailsType.textContent = isEpisode
			? `SEASON ${item.season ?? 0} · EPISODE ${item.episode || episodeIndex + 1}`
			: 'FILM';
		detailsTitle.textContent = item.tmdb_title || item.title;
		detailsMeta.innerHTML = metadataParts(item).join('<span>•</span>');
		detailsMeta.hidden = isEpisode;
		detailsDescription.hidden = true;
		detailsPoster.onerror = null;
		setImage(detailsPoster, item.image_url, `${item.title} ${isEpisode ? 'artwork' : 'poster'}`);
		if (isEpisode) loadEpisodeMetadata(item);
		detailsPlay.hidden = false;
		detailsEpisodeSidebar.hidden = !isEpisode;
		if (isEpisode) {
			const episodes = openShow.seasons?.[seasonIndex]?.episodes || [];
			const selectedIndex = episodes.indexOf(item);
			if (selectedIndex >= 0) episodeIndex = selectedIndex;
			renderEpisodeSidebar();
		}
		seasonTabs.hidden = true;
		episodeList.hidden = true;
		detailsHelp.hidden = false;
		detailsHelp.textContent = isEpisode
			? '↑ ↓ episode · OK play · Back episodes'
			: 'OK play · Back close';
		detailsPlay.focus({ preventScroll: true });
	}

	function closeDetails() {
		if (detailItem && openShow) {
			detailItem = null;
			renderShowDetails();
			return;
		}
		modal.hidden = true;
		modal.classList.remove('item-detail-open', 'episode-detail-open');
		detailItem = null;
		openShow = null;
	}

	function moveSeason(step) {
		if (!openShow?.seasons?.length) return;
		seasonIndex = (seasonIndex + step + openShow.seasons.length) % openShow.seasons.length;
		episodeIndex = 0;
		renderShowDetails();
	}

	function moveEpisode(step) {
		const episodes = openShow?.seasons?.[seasonIndex]?.episodes || [];
		if (!episodes.length) return;
		episodeIndex = (episodeIndex + step + episodes.length) % episodes.length;
		renderShowDetails();
	}

	function moveDetailEpisode(step) {
		const episodes = openShow?.seasons?.[seasonIndex]?.episodes || [];
		if (!episodes.length) return;
		episodeIndex = (episodeIndex + step + episodes.length) % episodes.length;
		openItemDetails(episodes[episodeIndex]);
	}

	function activateSelection() {
		const item = currentItem();
		if (item?.type === 'show') openShowDetails(item);
		else openItemDetails(item);
	}

	function activateEpisode() {
		openItemDetails(openShow?.seasons?.[seasonIndex]?.episodes?.[episodeIndex]);
	}

	document.addEventListener('keydown', (event) => {
		const isSearchKey = event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
		if (
			libraryFilter === 'movies' &&
			!openShow &&
			!detailItem &&
			event.target !== movieSearch &&
			(isSearchKey || event.key === 'Backspace' || event.key === 'Delete')
		) {
			event.preventDefault();
			libraryNavActive = false;
			typeIntoMovieSearch(event.key);
			return;
		}
		if (!['PageUp', 'PageDown', 'NavLeft', 'NavRight', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape'].includes(event.key)) return;
		if (
			event.target === movieSearch &&
			!['PageUp', 'PageDown', 'NavLeft', 'NavRight', 'Enter', 'Escape'].includes(event.key)
		) return;
		event.preventDefault();
		const key = ({ ArrowUp: 'PageUp', ArrowDown: 'PageDown', ArrowLeft: 'NavLeft', ArrowRight: 'NavRight' })[event.key] || event.key;
		if (detailItem) {
			if (key === 'Escape') closeDetails();
			else if (detailItem.type === 'episode' && key === 'PageUp') moveDetailEpisode(-1);
			else if (detailItem.type === 'episode' && key === 'PageDown') moveDetailEpisode(1);
			else if (key === 'Enter') playItem(detailItem);
			return;
		}
		if (key === 'Escape' && !openShow && libraryFilter !== 'all') {
			libraryNavActive = false;
			libraryNavIndex = 0;
			selectLibrary('all');
			return;
		}
		if (libraryNavActive) {
			if (key === 'NavLeft') moveLibraryNavigation(-1);
			else if (key === 'NavRight') moveLibraryNavigation(1);
			else if (key === 'Enter') activateLibraryNavigation();
			else if (key === 'PageDown' || key === 'Escape') {
				libraryNavActive = false;
				if (rows.length) renderSelection();
				else renderLibraryNavigation();
			}
			return;
		}
		if (openShow) {
			if (key === 'Escape') closeDetails();
			else if (key === 'NavLeft') moveSeason(-1);
			else if (key === 'NavRight') moveSeason(1);
			else if (key === 'PageUp') moveEpisode(-1);
			else if (key === 'PageDown') moveEpisode(1);
			else if (key === 'Enter') activateEpisode();
			return;
		}
		if (libraryFilter !== 'all' && key === 'PageUp') {
			if (!moveGridSelection(-1)) {
				libraryNavActive = true;
				libraryNavIndex = Math.max(0, libraryNavItems.findIndex((item) => item.dataset.libraryFilter === libraryFilter));
				renderLibraryNavigation();
			}
		} else if (libraryFilter !== 'all' && key === 'PageDown') {
			moveGridSelection(1);
		} else if (key === 'PageUp' && rowIndex === 0) {
			libraryNavActive = true;
			libraryNavIndex = Math.max(0, libraryNavItems.findIndex((item) => item.dataset.libraryFilter === libraryFilter));
			renderLibraryNavigation();
		} else if (key === 'PageUp') moveRow(-1);
		else if (key === 'PageDown') moveRow(1);
		else if (key === 'NavLeft') moveItem(-1);
		else if (key === 'NavRight') moveItem(1);
		else if (key === 'Enter') activateSelection();
	});

	heroAction.addEventListener('click', activateSelection);
	detailsClose.addEventListener('click', closeDetails);
	detailsPlay.addEventListener('click', () => playItem(detailItem));
	hero.addEventListener('dblclick', activateSelection);

	async function loadStationName() {
		loadingStationName.textContent = '';
		if (!Number.isInteger(channelNumber)) return;
		try {
			const response = await window.fs42Api.get('stations');
			const entry = (response.stations || []).find((candidate) => {
				const station = candidate.station_conf || candidate;
				return Number(station.channel_number) === channelNumber;
			});
			const station = entry?.station_conf || entry;
			if (station?.network_name) loadingStationName.textContent = station.network_name;
		} catch (error) {
			console.warn(`Could not load the name for channel ${channelNumber}:`, error);
		}
	}

	async function loadCatalog() {
		renderSkeletonRails();
		if (!Number.isInteger(channelNumber)) {
			railsElement.replaceChildren();
			message.classList.remove('loading');
			message.textContent = 'No channel number provided. Add ?channel=XX to the URL.';
			message.classList.add('error');
			return;
		}
		channelLabel.textContent = `CH ${channelNumber}`;
		loadStationName();
		try {
			const response = await window.fs42Api.get(`media-browser/${channelNumber}`);
			stationTitle.textContent = response.network_name || `Channel ${channelNumber}`;
			document.title = `${stationTitle.textContent} · Media Browser`;
			tmdbMovieGenres = Array.isArray(response.tmdb_movie_genres)
				? response.tmdb_movie_genres.filter((genre) => typeof genre === 'string' && genre.trim())
				: [];
			allRows = addMovieGenreRows((response.rows || []).filter((row) => row.items?.length));
			if (!allRows.length) throw new Error('No movies or shows were found in the configured libraries.');
			selectLibrary('all');
			app.setAttribute('aria-busy', 'false');
			message.classList.remove('loading');
			message.hidden = true;
			enrichMoviesFromTmdb();
		} catch (error) {
			railsElement.replaceChildren();
			railsElement.classList.remove('skeleton-rails');
			message.classList.remove('loading');
			message.textContent = error.detail || error.message || 'Could not load the media library.';
			message.classList.add('error');
		}
	}

	loadCatalog();
})();
