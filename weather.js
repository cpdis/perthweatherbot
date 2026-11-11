/* Small, dependency-free reader for both legacy and v2 weather reports. */
(function () {
    'use strict';
    const STALE_AFTER_HOURS = 18;
    const number = value => typeof value === 'number' && Number.isFinite(value);
    const text = value => typeof value === 'string' ? value.trim() : '';
    const observedAt = data => data.observed_at || data.forecast_data?.current_conditions?.timestamp;
    function parseInstant(value) {
        // Never let a visitor's timezone reinterpret a legacy local timestamp.
        if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? null : date;
    }
    function timeZone(value) {
        try { new Intl.DateTimeFormat('en', { timeZone: value }).format(); return value || 'UTC'; }
        catch (_) { return 'UTC'; }
    }
    function localTime(value, zone, options = {}) {
        const instant = parseInstant(value);
        if (!instant) return 'Time unavailable';
        return new Intl.DateTimeFormat('en-AU', { timeZone: timeZone(zone), ...options }).format(instant);
    }
    function generatedLabel(data) {
        const options = { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' };
        if (parseInstant(data.generated_at || data.timestamp)) return localTime(data.generated_at || data.timestamp, data.location?.timezone, options);
        const legacy = text(data.timestamp).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?$/);
        if (!legacy) return 'Time unavailable';
        const [, y, m, d, h, minute] = legacy;
        const wallClock = new Date(Date.UTC(+y, +m - 1, +d, +h, +minute));
        const label = new Intl.DateTimeFormat('en-AU', { ...options, timeZone: 'UTC', timeZoneName: undefined }).format(wallClock);
        return `${label} · ${text(data.location?.timezone).split('/').pop()?.replaceAll('_', ' ') || 'local'} time`;
    }
    function freshness(data, now = new Date()) {
        const observation = parseInstant(observedAt(data));
        const generation = parseInstant(data.generated_at);
        const ageSource = observation || generation;
        if (!ageSource) return { label: 'Update time unavailable', stale: true, message: 'This report has no reliable observation time. Please check the source before relying on it.' };
        const minutes = Math.floor((now - ageSource) / 60000);
        if (minutes < -5) return { label: 'Update time needs checking', stale: true, message: 'This report is dated in the future. Its freshness could not be verified.' };
        const hours = Math.floor(Math.max(0, minutes) / 60);
        const age = minutes < 1 ? 'just now' : minutes < 60 ? `${minutes}m ago` : hours < 48 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`;
        const stale = hours >= STALE_AFTER_HOURS;
        return { label: `${observation ? 'Weather observed' : 'Report generated'} ${age}`, stale, message: stale ? 'This weather report is getting old. The next scheduled update may be delayed.' : '' };
    }
    function upcomingForecast(data, now = new Date()) {
        const periods = Array.isArray(data.forecast_data?.forecast) ? data.forecast_data.forecast : [];
        const seen = new Set();
        return periods.filter(period => {
            if (!period || typeof period !== 'object') return false;
            const date = parseInstant(period.startTime);
            if (!date || date < now || date > new Date(+now + 24 * 3600000) || seen.has(+date)) return false;
            seen.add(+date);
            return true;
        }).sort((a, b) => parseInstant(a.startTime) - parseInstant(b.startTime)).slice(0, 8);
    }
    function recentHistory(entries, current) {
        if (!Array.isArray(entries)) return [];
        const name = current.location?.name || current.forecast_data?.location?.name;
        const currentKey = current.generated_at || current.timestamp;
        const seen = new Set([currentKey, current.timestamp].filter(Boolean));
        return entries.filter(entry => entry && entry.location?.name === name &&
            (!entry.location?.timezone || !current.location?.timezone || entry.location.timezone === current.location.timezone))
            .sort((a, b) => {
                const aTime = parseInstant(a.generated_at || a.timestamp) || parseInstant(a.observed_at || a.current_conditions?.timestamp);
                const bTime = parseInstant(b.generated_at || b.timestamp) || parseInstant(b.observed_at || b.current_conditions?.timestamp);
                return aTime && bTime ? bTime - aTime : String(b.generated_at || b.timestamp || '').localeCompare(String(a.generated_at || a.timestamp || ''));
            })
            .filter(entry => {
                const key = entry.generated_at || entry.timestamp;
                if (!key || seen.has(key)) return false;
                seen.add(key);
                return true;
            }).slice(0, 6);
    }
    function validReport(data) {
        return data && typeof data === 'object' && !Array.isArray(data) &&
            (text(data.weather_report) || text(data.report?.summary)) && data.forecast_data && typeof data.forecast_data === 'object';
    }
    const core = { parseInstant, localTime, generatedLabel, freshness, upcomingForecast, recentHistory, validReport };
    if (typeof module !== 'undefined' && module.exports) module.exports = core;
    if (typeof document === 'undefined') return;

    const $ = id => document.getElementById(id);
    const root = document.documentElement;
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const systemTheme = matchMedia('(prefers-color-scheme: dark)');
    const readPreference = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
    const savePreference = (key, value) => { try { localStorage.setItem(key, value); } catch (_) { /* Private browsing is fine. */ } };
    let currentData = null;
    let refreshError = '';
    let controller;
    let requestId = 0;
    let sceneSource = '';
    let sceneVisible = false;
    let manuallyPaused = readPreference('scene-motion') === 'paused';

    function setTheme(theme, persist = false) {
        root.dataset.theme = theme;
        $('theme-toggle').setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
        document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#151f1b' : '#f6f4ed';
        if (persist) savePreference('theme', theme);
    }
    function cycleTheme() { setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark', true); }
    function syncMotion() {
        const paused = manuallyPaused || reducedMotion.matches || document.hidden;
        root.dataset.motion = paused ? 'paused' : 'playing';
        $('motion-toggle').setAttribute('aria-pressed', String(paused));
        $('motion-toggle').setAttribute('aria-label', reducedMotion.matches ? 'Scene motion off: reduced motion preference' : paused ? 'Resume scene motion' : 'Pause scene motion');
        $('motion-toggle').title = reducedMotion.matches ? 'Motion is off because you prefer reduced motion' : paused ? 'Resume scene motion' : 'Pause scene motion';
        $('motion-toggle').querySelector('span').textContent = paused ? 'Still' : 'Pause';
        $('motion-toggle').disabled = reducedMotion.matches;
    }
    function setSceneOnly(enabled) {
        sceneVisible = enabled;
        root.dataset.sceneOnly = String(enabled);
        $('return-button').hidden = !enabled;
        $('scene-toggle').setAttribute('aria-pressed', String(enabled));
        (enabled ? $('return-button') : $('scene-toggle')).focus();
    }
    function element(tag, value, className) {
        const node = document.createElement(tag);
        if (value !== undefined) node.textContent = value;
        if (className) node.className = className;
        return node;
    }
    function updateFreshness() {
        if (!currentData) return;
        const state = freshness(currentData);
        $('freshness').textContent = state.label;
        root.dataset.stale = String(state.stale);
        const preview = currentData.preview === true ? 'Design preview · illustrative sample data, not a live forecast.' : '';
        $('notice').textContent = [preview, refreshError, state.message].filter(Boolean).join(' ');
        $('notice').hidden = !preview && !refreshError && !state.message;
    }
    function renderConditions(data) {
        const current = data.forecast_data.current_conditions || {};
        $('conditions').hidden = !Object.keys(current).length;
        $('temperature').textContent = number(current.temperature_c) ? `${Math.round(current.temperature_c)}°C` : '—°C';
        $('condition-description').textContent = text(current.description) || 'Conditions unavailable';
        const details = [];
        if (number(current.feels_like_c)) details.push(`Feels like ${Math.round(current.feels_like_c)}°C`);
        if (number(current.wind_speed_kmh)) details.push(`Wind ${Math.round(current.wind_speed_kmh)} km/h`);
        else if (number(current.wind_speed_mph)) details.push(`Wind ${Math.round(current.wind_speed_mph)} mph`);
        if (number(current.humidity)) details.push(`Humidity ${Math.round(current.humidity)}%`);
        $('condition-details').textContent = details.join(' · ');
        $('observation-time').textContent = `Observed ${localTime(observedAt(data), data.location?.timezone, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })} · OpenWeather`;
    }
    function renderNarrative(data) {
        const container = $('weather-report');
        container.replaceChildren();
        const report = data.report;
        if (report && text(report.summary)) {
            if (text(report.headline)) container.append(element('h2', report.headline));
            [report.summary, report.outlook].filter(text).forEach(value => container.append(element('p', value)));
            $('clothing').textContent = text(report.clothing);
            $('activity').textContent = text(report.activity);
            $('clothing').parentElement.hidden = !text(report.clothing);
            $('activity').parentElement.hidden = !text(report.activity);
            $('report-details').hidden = !text(report.clothing) && !text(report.activity);
        } else {
            text(data.weather_report).split(/\n\s*\n/).forEach(value => container.append(element('p', value)));
            $('report-details').hidden = true;
        }
        container.setAttribute('aria-busy', 'false');
    }
    function renderForecast(data) {
        const container = $('forecast-list');
        container.replaceChildren();
        const zone = data.location?.timezone;
        const periods = upcomingForecast(data);
        $('forecast-note').textContent = `Next 24 hours · 3-hour intervals · ${timeZone(zone).split('/').pop().replaceAll('_', ' ')} time`;
        if (!periods.length) { container.append(element('p', 'No upcoming forecast is available in this report. Refresh to check for an update.', 'forecast-empty')); return; }
        for (const period of periods) {
            const item = element('article', undefined, 'forecast-period');
            const day = element('span', localTime(period.startTime, zone, { weekday: 'short', day: 'numeric' }), 'forecast-day');
            const time = element('time', localTime(period.startTime, zone, { hour: 'numeric' }));
            time.dateTime = period.startTime;
            const temperature = element('span', number(period.temperature) ? `${Math.round(period.temperature)}°C` : '—°C', 'forecast-temp');
            const description = element('span', text(period.shortForecast) || 'Conditions unavailable', 'forecast-description');
            let probability = period.precipitation_probability_pct;
            if (!number(probability) && number(period.precipitation_probability)) probability = period.precipitation_probability * 100;
            const rain = element('span', number(probability) && probability >= 0 && probability <= 100 ? `${Math.round(probability)}% precip.` : 'Precip. —', 'forecast-rain');
            rain.title = 'Probability of precipitation during this 3-hour period';
            item.append(day, time, temperature, description, rain);
            container.append(item);
        }
    }
    function renderHistory(entries, data) {
        const container = $('history-list');
        container.replaceChildren();
        const history = recentHistory(entries, data);
        $('history-count').textContent = history.length ? `(${history.length})` : '';
        if (!history.length) { container.append(element('li', 'No earlier reports for this location yet.')); return; }
        for (const entry of history) {
            const item = element('li');
            const time = element('time', generatedLabel(entry));
            if (parseInstant(entry.generated_at || entry.timestamp)) time.dateTime = entry.generated_at || entry.timestamp;
            item.append(time, element('p', text(entry.headline) || text(entry.report?.headline) || text(entry.report_summary) || 'Earlier weather report'));
            const temperature = entry.current_conditions?.temperature_c;
            if (number(temperature)) item.append(element('span', `${Math.round(temperature)}°C at observation`, 'history-temp'));
            container.append(item);
        }
    }
    function loadScene(data, id) {
        const image = $('weather-image');
        const meta = data.image;
        if (meta?.status === 'unavailable') {
            image.classList.remove('is-loaded');
            sceneSource = '';
            $('scene-toggle').hidden = true;
            $('scene-caption').textContent = 'The scene is unavailable. The weather report is still here.';
            return;
        }
        const stamp = meta?.generated_at || data.generated_at || data.timestamp || observedAt(data) || '';
        const source = `weather_image.png?v=${encodeURIComponent(stamp)}`;
        $('scene-caption').textContent = meta?.status === 'previous' ? `AI-generated scene · earlier report${parseInstant(meta.generated_at) ? ' · ' + localTime(meta.generated_at, data.location?.timezone, {day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit'}) : ', date unknown'}` : meta?.status === 'ready' ? 'AI-generated scene · an impression, not a live view' : 'AI-generated scene · legacy artwork, date unverified';
        if (source === sceneSource) return;
        const pending = new Image();
        const timeout = setTimeout(() => pending.onerror?.(), 15000);
        pending.onload = () => {
            clearTimeout(timeout);
            if (id !== requestId) return;
            image.src = source;
            image.classList.add('is-loaded');
            sceneSource = source;
            $('scene-toggle').hidden = false;
        };
        pending.onerror = () => {
            clearTimeout(timeout);
            pending.onload = pending.onerror = null;
            if (id !== requestId) return;
            image.classList.remove('is-loaded');
            sceneSource = '';
            $('scene-toggle').hidden = true;
            $('scene-caption').textContent = 'The scene could not load. The weather report is still here.';
        };
        pending.src = source;
    }
    async function loadWeatherData() {
        const id = ++requestId;
        controller?.abort();
        controller = new AbortController();
        const signal = controller.signal;
        const timeout = setTimeout(() => controller?.signal === signal && controller.abort(), 15000);
        $('refresh-button').disabled = true;
        $('retry-button').hidden = true;
        if (!currentData) $('weather-report').setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(`weather_report.json?t=${Date.now()}`, { signal, cache: 'no-store' });
            if (!response.ok) throw new Error('Report unavailable');
            const data = await response.json();
            if (!validReport(data)) throw new Error('Invalid report');
            if (id !== requestId) return;
            const previousLocation = currentData?.location?.name;
            currentData = data;
            refreshError = '';
            const name = text(data.location?.name) || text(data.forecast_data.location?.name) || 'Your weather';
            $('location-title').textContent = name;
            document.title = `${name} Weather Vibes`;
            if (/^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(data.color_code || '')) root.style.setProperty('--weather-color', data.color_code);
            else root.style.removeProperty('--weather-color');
            $('local-date').textContent = localTime(observedAt(data) || data.generated_at, data.location?.timezone, { weekday: 'long', day: 'numeric', month: 'long' });
            $('timestamp').textContent = `Report generated ${generatedLabel(data)}. Updated on a schedule, not live.`;
            updateFreshness();
            renderConditions(data);
            renderNarrative(data);
            renderForecast(data);
            loadScene(data, id);
            if (previousLocation !== data.location?.name) $('history-section').open = false;
            // History is optional: its failure must not hide a good forecast.
            try {
                const response = await fetch(`weather_history.json?t=${Date.now()}`, { signal, cache: 'no-store' });
                if (!response.ok) throw new Error('History unavailable');
                const history = await response.json();
                if (!Array.isArray(history)) throw new Error('Invalid history');
                if (id === requestId) renderHistory(history, data);
            } catch (_) {
                if (id === requestId) { $('history-count').textContent = ''; $('history-list').replaceChildren(element('li', 'Recent reports could not load. Refresh to try again.')); }
            }
        } catch (_) {
            if (id !== requestId) return;
            if (currentData) {
                refreshError = 'Could not refresh. Showing the last report loaded on this page.';
                updateFreshness();
            } else {
                $('weather-report').replaceChildren(element('p', 'The weather report could not load. Please try again.'));
                $('freshness').textContent = 'Report unavailable';
                $('weather-report').setAttribute('aria-busy', 'false');
            }
            $('retry-button').hidden = false;
        } finally {
            clearTimeout(timeout);
            if (id === requestId) $('refresh-button').disabled = false;
        }
    }
    $('theme-toggle').addEventListener('click', cycleTheme);
    $('motion-toggle').addEventListener('click', () => { manuallyPaused = !manuallyPaused; savePreference('scene-motion', manuallyPaused ? 'paused' : 'playing'); syncMotion(); });
    $('refresh-button').addEventListener('click', loadWeatherData);
    $('retry-button').addEventListener('click', loadWeatherData);
    $('scene-toggle').addEventListener('click', () => setSceneOnly(true));
    $('return-button').addEventListener('click', () => setSceneOnly(false));
    document.addEventListener('keydown', event => {
        if (event.code === 'Escape' && sceneVisible) { setSceneOnly(false); return; }
        if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || event.repeat || event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
        if (event.code === 'KeyR') { event.preventDefault(); loadWeatherData(); }
        if (event.code === 'KeyT') { event.preventDefault(); cycleTheme(); }
    });
    document.addEventListener('visibilitychange', syncMotion);
    reducedMotion.addEventListener('change', syncMotion);
    systemTheme.addEventListener('change', event => { if (!readPreference('theme')) setTheme(event.matches ? 'dark' : 'light'); });
    setTheme(['dark', 'light'].includes(readPreference('theme')) ? readPreference('theme') : systemTheme.matches ? 'dark' : 'light');
    syncMotion();
    loadWeatherData();
    setInterval(() => { if (!document.hidden) loadWeatherData(); }, 10 * 60 * 1000);
    setInterval(() => { if (currentData && !document.hidden) { updateFreshness(); renderForecast(currentData); } }, 60 * 1000);
}());
