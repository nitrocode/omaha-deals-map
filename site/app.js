const JS_DAY = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const STORAGE_KEY = "omaha-deals-filters-v1";
const FAVORITES_KEY = "omaha-deals-favorites-v1";
const HOME_KEY = "omaha-deals-home-v1";
const VIEW_KEY = "omaha-deals-view-v1";

// Driving-time heuristic. Real road distance is roughly 1.3x straight-line in
// city grids; average urban driving (including stops) ~25 mph. Override-able if
// we ever wire a real routing API.
const ROAD_FACTOR = 1.3;
const AVG_MPH = 25;

const KIND_COLOR = {
    happy_hour: "#2c5aa0",
    special: "#3aa758",
    voucher: "#e0892a",
};
const KIND_PRIORITY = ["happy_hour", "special", "voucher"];

const DEFAULT_FILTERS = {
    kinds: ["happy_hour"],
    nowOnly: false,
    atHour: null,
    favoritesOnly: false,
    cuisines: [],
    radiusMi: null,  // null = no limit; otherwise miles from home
    priceTiers: [],  // empty = any; otherwise subset of ["$", "$$", "$$$", "$$$$"]
    neighborhood: null,  // null = any; otherwise a string match
    needsReviewOnly: false,  // show only venues flagged as needs_review
    reverseOnly: false,      // show only venues with a reverse (late-night) HH window
};

// Days. A venue's first_seen_at within this window gets a 🆕 badge.
const NEW_BADGE_WINDOW_DAYS = 7;

const state = {
    data: null,
    today: JS_DAY[new Date().getDay()],
    selectedDay: JS_DAY[new Date().getDay()],
    kinds: new Set(DEFAULT_FILTERS.kinds),
    nowOnly: DEFAULT_FILTERS.nowOnly,
    atHour: DEFAULT_FILTERS.atHour,
    favoritesOnly: DEFAULT_FILTERS.favoritesOnly,
    cuisines: new Set(DEFAULT_FILTERS.cuisines),
    radiusMi: DEFAULT_FILTERS.radiusMi,
    priceTiers: new Set(DEFAULT_FILTERS.priceTiers),
    neighborhood: DEFAULT_FILTERS.neighborhood,
    needsReviewOnly: DEFAULT_FILTERS.needsReviewOnly,
    reverseOnly: DEFAULT_FILTERS.reverseOnly,
    favorites: new Set(),
    markers: [],
    selectedMarker: null,
    cluster: null,
    map: null,
    userLocation: null,    // [lat, lng] or null
    userMarker: null,
    home: null,            // { lat, lng, label } or null
    homeMarker: null,
    radiusCircle: null,    // L.circle showing the radius constraint, or null
    pickingHomeOnMap: false,
    lastMarkerClickAt: 0,  // epoch ms; used to suppress the map-click that
                           // Leaflet fires alongside a marker click
    view: "map",           // "map" | "list" (mobile-only; ignored when split-pane shows both)
    selectedId: null,      // restaurant.id of the currently-selected venue, if any
};

// ---------- persistence ----------

function loadPersistedFilters() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const f = JSON.parse(raw);
        if (Array.isArray(f.kinds)) state.kinds = new Set(f.kinds);
        if (typeof f.nowOnly === "boolean") state.nowOnly = f.nowOnly;
        if (f.atHour === null || typeof f.atHour === "number") state.atHour = f.atHour;
        if (typeof f.favoritesOnly === "boolean") state.favoritesOnly = f.favoritesOnly;
        if (Array.isArray(f.cuisines)) state.cuisines = new Set(f.cuisines);
        if (f.radiusMi === null || typeof f.radiusMi === "number") state.radiusMi = f.radiusMi;
        if (Array.isArray(f.priceTiers)) state.priceTiers = new Set(f.priceTiers);
        if (typeof f.neighborhood === "string" || f.neighborhood === null) {
            state.neighborhood = f.neighborhood;
        }
        if (typeof f.needsReviewOnly === "boolean") state.needsReviewOnly = f.needsReviewOnly;
        if (typeof f.reverseOnly === "boolean") state.reverseOnly = f.reverseOnly;
    } catch (e) { /* ignore corrupt storage */ }
}

function persistFilters() {
    const f = {
        kinds: [...state.kinds],
        nowOnly: state.nowOnly,
        atHour: state.atHour,
        favoritesOnly: state.favoritesOnly,
        cuisines: [...state.cuisines],
        radiusMi: state.radiusMi,
        priceTiers: [...state.priceTiers],
        neighborhood: state.neighborhood,
        needsReviewOnly: state.needsReviewOnly,
        reverseOnly: state.reverseOnly,
    };
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(f)); } catch (e) { /* ignore */ }
}

function loadFavorites() {
    try {
        const raw = localStorage.getItem(FAVORITES_KEY);
        if (raw) state.favorites = new Set(JSON.parse(raw));
    } catch (e) { /* ignore */ }
}

function persistFavorites() {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites])); }
    catch (e) { /* ignore */ }
}

function loadHome() {
    try {
        const raw = localStorage.getItem(HOME_KEY);
        if (!raw) return;
        const h = JSON.parse(raw);
        if (typeof h?.lat === "number" && typeof h?.lng === "number") {
            state.home = { lat: h.lat, lng: h.lng, label: h.label || "" };
        }
    } catch (e) { /* ignore */ }
}

function loadView() {
    try {
        const v = localStorage.getItem(VIEW_KEY);
        if (v === "map" || v === "list") state.view = v;
    } catch (e) { /* ignore */ }
}

function persistView() {
    try { localStorage.setItem(VIEW_KEY, state.view); } catch (e) { /* ignore */ }
}

function persistHome() {
    try {
        if (state.home) localStorage.setItem(HOME_KEY, JSON.stringify(state.home));
        else localStorage.removeItem(HOME_KEY);
    } catch (e) { /* ignore */ }
}

// ---------- data loading + map setup ----------

async function loadData() {
    const r = await fetch("data.json", { cache: "no-cache" });
    if (!r.ok) throw new Error(`data.json: HTTP ${r.status}`);
    return r.json();
}

function initMap() {
    state.map = L.map("map", { center: [41.2565, -95.9345], zoom: 12 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
    }).addTo(state.map);
    state.cluster = L.markerClusterGroup({
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
        disableClusteringAtZoom: 17,
        maxClusterRadius: 45,
    });
    state.map.addLayer(state.cluster);
}

// ---------- time/format helpers ----------

function formatTime12(hhmm) {
    if (!hhmm) return "";
    const [hStr, mStr] = hhmm.split(":");
    let h = Number(hStr);
    const m = mStr ?? "00";
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12;
    if (h === 0) h = 12;
    return `${h}:${m} ${ampm}`;
}

function escapeHtml(s) {
    return String(s).replace(/[<>&"]/g, c =>
        ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;" }[c]));
}

function fmtMoney(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(2) : "?";
}

function haversineMiles(a, b) {
    const toRad = d => d * Math.PI / 180;
    const R = 3958.8; // miles
    const dLat = toRad(b[0] - a[0]);
    const dLng = toRad(b[1] - a[1]);
    const x = Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
}

function driveTimeMinutes(miles) {
    return (miles * ROAD_FACTOR) / AVG_MPH * 60;
}

// Walking pace: ~3 mph on flat city blocks. No road-factor correction because
// pedestrians cross diagonally and cut through, which roughly cancels out the
// detour penalty cars suffer.
const WALK_MPH = 3;
function walkTimeMinutes(miles) {
    return (miles / WALK_MPH) * 60;
}

function formatMiles(miles) {
    return miles < 10 ? miles.toFixed(1) + " mi" : Math.round(miles) + " mi";
}

function formatDriveTime(min) {
    if (min < 1) return "< 1 min";
    if (min < 60) return Math.round(min) + " min";
    const h = Math.floor(min / 60);
    const m = Math.round(min - h * 60);
    return m ? `${h}h ${m}min` : `${h}h`;
}

function showBanner(text) {
    const b = document.getElementById("banner");
    b.textContent = text;
    b.classList.remove("hidden");
}

function hideBanner() {
    document.getElementById("banner").classList.add("hidden");
}

// ---------- filtering ----------

function windowContainsMinute(w, minuteOfDay) {
    const [sh, sm] = w.start.split(":").map(Number);
    const [eh, em] = (w.end || "23:59").split(":").map(Number);
    return minuteOfDay >= sh * 60 + sm && minuteOfDay <= eh * 60 + em;
}

function isActiveNow(w) {
    const now = new Date();
    if (JS_DAY[now.getDay()] !== w.day) return false;
    const cur = now.getHours() * 60 + now.getMinutes();
    return windowContainsMinute(w, cur);
}

function isFavorite(r) {
    return state.favorites.has(r.id) || (r.personal?.tags || []).includes("favorite");
}

function toggleFavorite(r) {
    if (state.favorites.has(r.id)) state.favorites.delete(r.id);
    else state.favorites.add(r.id);
    persistFavorites();
    // Re-render list + markers so all surfaces of the favorite state stay
    // in sync (badge in list, fill on heart, marker if favoritesOnly is on).
    render();
    // Refresh the venue sheet too if it's open and showing this venue.
    if (state.selectedId === r.id) showVenue(r);
}

function shouldShowNewBadges() {
    // First time the tracker ran, every venue got stamped within the same
    // build, so 🆕 would mean nothing. Suppress badges entirely when more
    // than half the dataset shares the earliest first_seen_at. As new
    // venues land in later scrapes their timestamps diverge and badges
    // become meaningful again.
    if (state._showNewCache !== undefined) return state._showNewCache;
    const rs = state.data?.restaurants || [];
    if (!rs.length) { state._showNewCache = false; return false; }
    let earliest = Infinity;
    const stamps = [];
    for (const r of rs) {
        if (!r.first_seen_at) continue;
        const t = new Date(r.first_seen_at).getTime();
        if (!isNaN(t)) {
            stamps.push(t);
            if (t < earliest) earliest = t;
        }
    }
    if (!stamps.length) { state._showNewCache = false; return false; }
    const tolerance = 60 * 60 * 1000;  // an hour
    const initial = stamps.filter(t => Math.abs(t - earliest) <= tolerance).length;
    state._showNewCache = initial / stamps.length < 0.5;
    return state._showNewCache;
}

function isNewBadge(r) {
    if (!r.first_seen_at) return false;
    if (!shouldShowNewBadges()) return false;
    const seen = new Date(r.first_seen_at).getTime();
    if (isNaN(seen)) return false;
    const ageDays = (Date.now() - seen) / (1000 * 60 * 60 * 24);
    return ageDays >= 0 && ageDays < NEW_BADGE_WINDOW_DAYS;
}

function hasReverseHH(r) {
    return (r.deals || []).some(d =>
        (d.windows || []).some(w => w.type === "reverse_hh"));
}

function matchesFilters(r) {
    if (state.favoritesOnly && !isFavorite(r)) return false;
    if (state.needsReviewOnly && !r.needs_review) return false;
    if (state.reverseOnly && !hasReverseHH(r)) return false;
    if (state.cuisines.size > 0) {
        const cs = r.cuisine || [];
        if (!cs.some(c => state.cuisines.has(c))) return false;
    }
    if (state.radiusMi != null && state.home && r.lat != null && r.lng != null) {
        const mi = haversineMiles([state.home.lat, state.home.lng], [r.lat, r.lng]);
        if (mi > state.radiusMi) return false;
    } else if (state.radiusMi != null && state.home && (r.lat == null || r.lng == null)) {
        // No coords means we can't measure; hide rather than show ambiguously when
        // the user has explicitly constrained by distance.
        return false;
    }
    if (state.priceTiers.size > 0) {
        // Skip venues that haven't been classified yet; "$" through "$$$$"
        // can't both be a real filter AND match the absence of data.
        if (!r.price_tier || !state.priceTiers.has(r.price_tier)) return false;
    }
    if (state.neighborhood && r.neighborhood !== state.neighborhood) {
        return false;
    }
    return r.deals.some(d => {
        if (!state.kinds.has(d.kind)) return false;
        if (d.kind === "happy_hour") {
            const wins = (d.windows || []).filter(w => w.day === state.selectedDay);
            if (wins.length === 0) return false;
            if (state.nowOnly && !wins.some(isActiveNow)) return false;
            if (state.atHour !== null) {
                if (!wins.some(w => windowContainsMinute(w, state.atHour * 60))) return false;
            }
        }
        return true;
    });
}

function primaryKindForRestaurant(r) {
    // Pick the highest-priority kind that's both (a) on the restaurant AND (b) in the
    // active kind filter. Falls back to first kind on restaurant if none match the filter.
    const kindsOnR = new Set(r.deals.map(d => d.kind));
    for (const k of KIND_PRIORITY) {
        if (kindsOnR.has(k) && state.kinds.has(k)) return k;
    }
    for (const k of KIND_PRIORITY) {
        if (kindsOnR.has(k)) return k;
    }
    return "happy_hour";
}

// ---------- marker rendering ----------

function markerStyle(kind, selected) {
    const color = selected ? "#d9534f" : (KIND_COLOR[kind] || KIND_COLOR.happy_hour);
    return {
        radius: selected ? 11 : 7,
        weight: selected ? 3 : 1,
        color: selected ? "#fff" : color,
        fillColor: color,
        fillOpacity: 0.9,
    };
}

function selectMarker(marker, kind) {
    if (state.selectedMarker && state.selectedMarker !== marker) {
        const prevKind = state.selectedMarker._kind;
        state.selectedMarker.setStyle(markerStyle(prevKind, false));
    }
    marker.setStyle(markerStyle(kind, true));
    marker.bringToFront();
    state.selectedMarker = marker;
}

function clearMarkers() {
    state.cluster.clearLayers();
    state.markers = [];
    state.selectedMarker = null;
}

function updateDayCounts() {
    // Restaurants per day = unique restaurants with a happy_hour window on that day.
    // (Specials and vouchers aren't day-bound, so this count is happy-hour-centric.)
    const counts = Object.fromEntries(JS_DAY.map(d => [d, 0]));
    if (!state.data) return;
    for (const r of state.data.restaurants) {
        const days = new Set();
        for (const d of r.deals) {
            if (d.kind === "happy_hour") {
                for (const w of (d.windows || [])) days.add(w.day);
            }
        }
        for (const d of days) counts[d]++;
    }
    document.querySelectorAll(".day-tabs button").forEach(btn => {
        const c = counts[btn.dataset.day] || 0;
        btn.querySelector(".day-count").textContent = c ? `(${c})` : "";
        btn.classList.toggle("today", btn.dataset.day === state.today);
        btn.classList.toggle("active", btn.dataset.day === state.selectedDay);
    });
}

function render() {
    if (!state.map || !state.data) return;
    clearMarkers();
    const matched = [];
    for (const r of state.data.restaurants) {
        if (!matchesFilters(r)) continue;
        matched.push(r);
    }
    let visibleMarkers = 0;
    for (const r of matched) {
        if (r.lat == null || r.lng == null) continue;
        const kind = primaryKindForRestaurant(r);
        const marker = L.circleMarker([r.lat, r.lng], markerStyle(kind, false));
        marker._kind = kind;
        marker._venueId = r.id;
        // escapeHtml on every interpolated field: r.name + the deal summary
        // both come from third-party scrape sources via deals.json, and
        // bindTooltip renders strings as HTML (OWASP A03 sink).
        const dealMeta = listRowMetaLine(r);
        const tooltipHtml = dealMeta
            ? `<strong>${escapeHtml(r.name)}</strong><br>${escapeHtml(dealMeta)}`
            : `<strong>${escapeHtml(r.name)}</strong>`;
        marker.bindTooltip(tooltipHtml, { direction: "top", offset: [0, -4] });
        marker.on("click", () => {
            // Stamp the time so the map's click handler can ignore the
            // companion event Leaflet fires alongside marker clicks.
            state.lastMarkerClickAt = Date.now();
            openVenue(r, { fromList: false });
        });
        state.cluster.addLayer(marker);
        state.markers.push(marker);
        if (state.selectedId === r.id) selectMarker(marker, kind);
        visibleMarkers++;
    }
    renderList(matched);
    document.getElementById("empty-overlay").classList.toggle("hidden", matched.length > 0);
    updateDayCounts();
}

// ---------- list view ----------

function happyHourSummaryForDay(r) {
    // One short line: the first happy-hour window on the selected day, formatted 12h.
    for (const d of r.deals) {
        if (d.kind !== "happy_hour") continue;
        for (const w of (d.windows || [])) {
            if (w.day !== state.selectedDay) continue;
            const start = formatTime12(w.start);
            const end = w.end ? "-" + formatTime12(w.end) : "";
            const tag = w.type === "reverse_hh" ? " (rev)" : "";
            return `HH ${start}${end}${tag}`;
        }
    }
    return null;
}

function listRowMetaLine(r) {
    // Prefer the happy-hour window for the selected day; otherwise show the
    // kinds-on-this-venue as fallback so a special/voucher-only venue isn't blank.
    const hh = happyHourSummaryForDay(r);
    const dealPart = hh
        ? hh
        : ([...new Set(r.deals.map(d => d.kind))]
            .filter(k => k !== "happy_hour")
            .join(", "));
    // Append price + neighborhood as low-key trailing context, only when set.
    const tags = [];
    if (r.price_tier) tags.push(r.price_tier);
    if (r.neighborhood) tags.push(r.neighborhood);
    const tagPart = tags.length ? " · " + tags.join(" · ") : "";
    return (dealPart || "") + tagPart;
}

function distanceAnchor() {
    // Prefer the user's home (stable, persisted). Fall back to their current
    // location (browser geolocation, may not be set). Returning null means we
    // have no anchor and the list should fall back to alphabetical sort.
    if (state.home) return [state.home.lat, state.home.lng];
    if (state.userLocation) return state.userLocation;
    return null;
}

function compareForList(a, b) {
    // Default sort is by distance from whichever anchor we have (home OR
    // current location). No-coord venues sink to the bottom so they don't
    // clutter the "nearest" view. Alphabetical only when we have no anchor.
    const anchor = distanceAnchor();
    if (anchor) {
        const da = (a.lat != null && a.lng != null)
            ? haversineMiles(anchor, [a.lat, a.lng]) : Infinity;
        const db = (b.lat != null && b.lng != null)
            ? haversineMiles(anchor, [b.lat, b.lng]) : Infinity;
        if (da !== db) return da - db;
    }
    return (a.name || "").localeCompare(b.name || "");
}

function renderList(matched) {
    const root = document.getElementById("list-rows");
    if (!root) return;
    root.innerHTML = "";
    const sorted = [...matched].sort(compareForList);
    const frag = document.createDocumentFragment();
    for (const r of sorted) {
        const li = document.createElement("li");
        li.className = "venue-row";
        if (state.selectedId === r.id) li.classList.add("selected");
        li.dataset.venueId = r.id;
        li.tabIndex = 0;
        const kind = primaryKindForRestaurant(r);
        const anchor = distanceAnchor();
        const distHtml = (anchor && r.lat != null && r.lng != null)
            ? `<span class="v-distance">${formatMiles(haversineMiles(anchor, [r.lat, r.lng]))}</span>`
            : "";
        const nogeoHtml = (r.lat == null || r.lng == null)
            ? `<span class="v-nogeo" title="No location yet, won't show on map">no location</span>`
            : "";
        // Small 📷 next to the name when we have a photo, so users can scan
        // the list and see which venues will show an image when tapped.
        const photoIcon = (r.photo && r.photo.url)
            ? `<span class="v-photo-icon" title="Photo available">📷</span>`
            : "";
        const badges = [];
        if ((r.source_count || 0) >= 2) {
            badges.push('<span class="v-badge v-badge-popular" title="Listed in 2+ sources">popular</span>');
        }
        if (isNewBadge(r)) {
            badges.push('<span class="v-badge v-badge-new" title="Added in the last week">🆕</span>');
        }
        if (hasReverseHH(r)) {
            badges.push('<span class="v-badge v-badge-reverse" title="Late-night / reverse happy hour">late night</span>');
        }
        if (r.needs_review) {
            const reasonText = reviewReasonsText(r) || "Address or hours need confirming";
            badges.push(`<span class="v-badge v-badge-review" title="${escapeHtml(reasonText)}">needs review</span>`);
        }
        const fav = isFavorite(r);
        const heartChar = fav ? "♥" : "♡";
        const heartLabel = fav ? "Unfavorite" : "Favorite";
        const heartButton = `<button type="button" class="v-fav-btn${fav ? " active" : ""}" `
            + `aria-pressed="${fav}" aria-label="${heartLabel}" title="${heartLabel}">${heartChar}</button>`;
        li.innerHTML = `
            ${heartButton}
            <span class="v-pip kind-${kind}"></span>
            <span class="v-name">${escapeHtml(r.name)}${photoIcon}${nogeoHtml} ${badges.join(" ")}</span>
            ${distHtml}
            <span class="v-meta">${escapeHtml(listRowMetaLine(r))}</span>
        `;
        li.querySelector(".v-fav-btn").addEventListener("click", e => {
            // Stop the click from bubbling to the row (which opens the
            // venue sheet) - heart taps are a separate gesture.
            e.stopPropagation();
            toggleFavorite(r);
        });
        li.addEventListener("click", () => openVenue(r, { fromList: true }));
        li.addEventListener("keydown", e => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openVenue(r, { fromList: true });
            }
        });
        frag.appendChild(li);
    }
    root.appendChild(frag);
}

function openVenue(r, opts = {}) {
    state.selectedId = r.id;
    // Highlight the marker if there is one (no-coord venues still open the sheet).
    const marker = state.markers.find(m => m._venueId === r.id);
    if (marker) {
        selectMarker(marker, marker._kind);
        // If we came from the list (esp. on mobile when switching views), nudge
        // the map toward the venue so it's visible once user flips to map view.
        if (opts.fromList && state.map && r.lat != null && r.lng != null) {
            state.map.setView([r.lat, r.lng], Math.max(state.map.getZoom(), 14));
        }
    }
    // Update list-row highlight without a full re-render.
    document.querySelectorAll(".venue-row.selected").forEach(el => el.classList.remove("selected"));
    const row = document.querySelector(`.venue-row[data-venue-id="${cssEscape(r.id)}"]`);
    if (row) {
        row.classList.add("selected");
        row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    showVenue(r);
}

function cssEscape(s) {
    // Slugs are kebab-case alphanumeric, but escape defensively so a malformed
    // id can't break the querySelector.
    return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function setView(v) {
    if (v !== "map" && v !== "list") return;
    state.view = v;
    document.body.dataset.view = v;
    document.querySelectorAll("#view-toggle button").forEach(btn => {
        btn.setAttribute("aria-selected", btn.dataset.view === v ? "true" : "false");
    });
    persistView();
    // Leaflet needs a nudge when its container goes from display:none to visible,
    // otherwise tiles render at the wrong size.
    if (v === "map" && state.map) state.map.invalidateSize();
}

// ---------- venue sheet ----------

function _sourceLink(d) {
    const url = d.source_url || d.external_link;
    if (!url || !/^https?:\/\//i.test(url)) return "";
    const host = (url.match(/^https?:\/\/([^/]+)/i) || [, ""])[1].replace(/^www\./, "");
    return ` <a class="deal-source-link" target="_blank" rel="noopener nofollow"
              href="${escapeHtml(url)}">source: ${escapeHtml(host)} ↗</a>`;
}

function renderDeal(d) {
    const kindClass = `kind kind-${d.kind}`;
    const dealTextLine = (d.raw_text && d.raw_text.trim())
        ? `<span class="deal-text">${escapeHtml(d.raw_text.trim())}</span>`
        : "";
    const srcLink = _sourceLink(d);
    if (d.kind === "happy_hour") {
        const wins = (d.windows || [])
            .filter(w => w.day === state.selectedDay)
            .map(w => {
                const start = escapeHtml(formatTime12(w.start));
                const end = w.end ? " - " + escapeHtml(formatTime12(w.end)) : "";
                const tag = w.type === "reverse_hh" ? " (reverse)" : "";
                return `${start}${end}${tag}`;
            })
            .join(", ");
        return `<div class="venue-deal"><span class="${kindClass}">happy hour</span>${wins}
                ${dealTextLine}${srcLink}</div>`;
    }
    if (d.kind === "special") {
        return `<div class="venue-deal"><span class="${kindClass}">special</span>${escapeHtml(d.title || "")}
                <br><small>${escapeHtml(d.valid_from || "?")} to ${escapeHtml(d.valid_until || "?")}</small>
                ${dealTextLine}${srcLink}</div>`;
    }
    if (d.kind === "voucher") {
        return `<div class="venue-deal"><span class="${kindClass}">voucher</span>${escapeHtml(d.title || "")}
                <br><small>$${fmtMoney(d.original_price)} to $${fmtMoney(d.sale_price)}
                (save $${fmtMoney(d.savings)})</small>${srcLink}</div>`;
    }
    return "";
}

function distanceLines(r) {
    // Build distance + drive-time lines for both home and current location, if set.
    // Walking time is only shown for venues under a mile, where it's actually a
    // realistic alternative; beyond that it just clutters the line.
    const lines = [];
    const target = [r.lat, r.lng];
    const tail = mi => {
        const drive = `~${formatDriveTime(driveTimeMinutes(mi))} drive`;
        if (mi < 1) {
            return `${drive} &middot; ~${formatDriveTime(walkTimeMinutes(mi))} walk`;
        }
        return drive;
    };
    if (state.home) {
        const mi = haversineMiles([state.home.lat, state.home.lng], target);
        lines.push(
            `<p class="distance">🏠 ${formatMiles(mi)} from home &middot; ${tail(mi)}</p>`
        );
    }
    if (state.userLocation) {
        const mi = haversineMiles(state.userLocation, target);
        lines.push(
            `<p class="distance">📍 ${formatMiles(mi)} from you &middot; ${tail(mi)}</p>`
        );
    }
    return lines.join("");
}

const REPO_ISSUES_URL = "https://github.com/nitrocode/omaha-deals-map/issues/new";

// Google Form for anonymous (no-login) contributions. Entry IDs were
// extracted from FB_PUBLIC_LOAD_DATA_ on the live form page; they're stable
// across responses (Google doesn't rotate them on form edits, only when a
// question is deleted and recreated).
const GOOGLE_FORM_EMBED_URL =
    "https://docs.google.com/forms/d/e/1FAIpQLSfbJH3elOl8Al-G9fSURno-QWa-Jn-f3HjXPWeQxoQ0BjJbcg/viewform?embedded=true";
const GOOGLE_FORM_ENTRY_SLUG = "entry.1208694505";  // Venue ID field
const GOOGLE_FORM_ENTRY_NAME = "entry.53145432";    // Venue name field

function reportIssueLinkFor(r) {
    const params = new URLSearchParams({
        template: "fix-venue.yml",
        slug: r.id || "",
        name: r.name || "",
    });
    return `${REPO_ISSUES_URL}?${params.toString()}`;
}

function contributeFormUrlFor(r) {
    // Returns the embed URL with venue context prefilled, or null when the
    // Google Form isn't configured yet (we ship that way and let the maintainer
    // wire it up post-deploy without redeploying).
    if (!GOOGLE_FORM_EMBED_URL) return null;
    const url = new URL(GOOGLE_FORM_EMBED_URL);
    if (r?.id && GOOGLE_FORM_ENTRY_SLUG) url.searchParams.set(GOOGLE_FORM_ENTRY_SLUG, r.id);
    if (r?.name && GOOGLE_FORM_ENTRY_NAME) url.searchParams.set(GOOGLE_FORM_ENTRY_NAME, r.name);
    if (!url.searchParams.has("embedded")) url.searchParams.set("embedded", "true");
    return url.toString();
}

function openContributeSheet(r) {
    const sheet = document.getElementById("contribute-sheet");
    const iframe = document.getElementById("contribute-iframe");
    const fallback = document.getElementById("contribute-fallback");
    const directLink = document.getElementById("contribute-direct-link");
    const url = contributeFormUrlFor(r);
    if (url) {
        iframe.src = url;
        iframe.hidden = false;
        fallback.hidden = true;
        const directUrl = new URL(url);
        directUrl.searchParams.delete("embedded");
        directLink.href = directUrl.toString();
        directLink.hidden = false;
    } else {
        iframe.hidden = true;
        directLink.hidden = true;
        fallback.hidden = false;
    }
    sheet.classList.remove("hidden");
}

function mapsLinkFor(r) {
    // If home is set, deep-link Google Maps directions from home -> restaurant.
    // Otherwise fall back to a search link (matches prior behavior).
    if (r.lat != null && r.lng != null && state.home) {
        return "https://www.google.com/maps/dir/?api=1" +
            `&origin=${state.home.lat},${state.home.lng}` +
            `&destination=${r.lat},${r.lng}`;
    }
    if (r.lat != null && r.lng != null) {
        return `https://www.google.com/maps/search/?api=1&query=${r.lat},${r.lng}`;
    }
    return `https://www.google.com/maps/search/${encodeURIComponent(r.name + " Omaha NE")}`;
}

const REVIEW_REASON_LABELS = {
    missing_location: "address unknown (hidden from map)",
    uncertain_location: "address might be wrong (low-confidence geocode)",
    missing_end_time: "happy-hour end time unknown",
};

function reviewReasonsText(r) {
    const reasons = (r.review_reasons || []).map(k => REVIEW_REASON_LABELS[k]).filter(Boolean);
    return reasons.join(", ");
}

function renderReviewReasons(r) {
    if (!r.needs_review) return "";
    const reasons = (r.review_reasons || []).map(k => REVIEW_REASON_LABELS[k]).filter(Boolean);
    if (!reasons.length) return "";
    const items = reasons.map(t => `<li>${escapeHtml(t)}</li>`).join("");
    return `
      <div class="review-reasons">
        <p class="review-reasons-title">⚠ Help fix this venue:</p>
        <ul>${items}</ul>
      </div>
    `;
}

function showVenue(r) {
    const sheet = document.getElementById("venue-sheet");
    const metaParts = [];
    if (r.cuisine && r.cuisine.length) metaParts.push(escapeHtml(r.cuisine.join(", ")));
    if (r.neighborhood) metaParts.push(escapeHtml(r.neighborhood));
    if (r.price_tier) metaParts.push(escapeHtml(r.price_tier));
    const cuisineLine = metaParts.length
        ? `<p class="meta">${metaParts.join(" &middot; ")}</p>`
        : "";
    // Photo: discovered free-of-charge via OSM image / Wikidata / venue's
    // own og:image. URL and attribution come from a trusted pipeline
    // cache, but still escape every interpolated string since this lands
    // in innerHTML.
    const photoBlock = (r.photo && r.photo.url)
        ? `<figure class="venue-photo">
             <img src="${escapeHtml(r.photo.url)}" alt="${escapeHtml(r.name)}" loading="lazy"
                  onerror="this.closest('figure').style.display='none'">
             <figcaption>${escapeHtml(r.photo.attribution || "")}</figcaption>
           </figure>`
        : "";
    const fav = state.favorites.has(r.id);
    const mapsUrl = mapsLinkFor(r);
    const mapsLabel = state.home ? "Directions from home" : "Open in Google Maps";
    sheet.innerHTML = `
        <h2>${escapeHtml(r.name)}</h2>
        ${cuisineLine}
        ${photoBlock}
        <p>${escapeHtml(r.address || "(no address yet)")}</p>
        ${renderReviewReasons(r)}
        ${distanceLines(r)}
        <p>
          <button class="fav-btn ${fav ? "active" : ""}" id="fav-toggle">
            ${fav ? "♥ Favorited" : "♡ Favorite"}
          </button>
        </p>
        ${(r.deals || []).map(renderDeal).join("")}
        ${r.website ? `<p><a target="_blank" rel="noopener nofollow" href="${escapeHtml(r.website)}">Official site ↗</a></p>` : ""}
        <p><a target="_blank" rel="noopener" href="${mapsUrl}">${mapsLabel}</a></p>
        ${r.personal?.notes ? `<p><em>${escapeHtml(r.personal.notes)}</em></p>` : ""}
        <p class="report-link">
          <button id="venue-contribute" class="link-btn">Suggest a fix (no login)</button>
          &middot;
          <a target="_blank" rel="noopener" href="${reportIssueLinkFor(r)}">via GitHub</a>
        </p>
        <button id="venue-close">Close</button>
    `;
    sheet.classList.remove("hidden");

    document.getElementById("venue-close").addEventListener("click", () => {
        sheet.classList.add("hidden");
        if (state.selectedMarker) {
            const k = state.selectedMarker._kind;
            state.selectedMarker.setStyle(markerStyle(k, false));
            state.selectedMarker = null;
        }
        state.selectedId = null;
        document.querySelectorAll(".venue-row.selected").forEach(el => el.classList.remove("selected"));
    });
    document.getElementById("fav-toggle").addEventListener("click", () => {
        if (state.favorites.has(r.id)) state.favorites.delete(r.id);
        else state.favorites.add(r.id);
        persistFavorites();
        showVenue(r);  // re-render to flip the button
        render();      // re-render markers in case favoritesOnly is on
    });
    document.getElementById("venue-contribute").addEventListener("click", () => {
        openContributeSheet(r);
    });
}

// ---------- cuisine filter populator ----------

function buildCuisineFilter() {
    const all = new Set();
    for (const r of state.data.restaurants) (r.cuisine || []).forEach(c => all.add(c));
    const sorted = [...all].sort();
    const host = document.getElementById("cuisine-filter");
    if (sorted.length === 0) {
        host.innerHTML = "<legend>Cuisine</legend>" +
            "<p class='hint'>No cuisine data yet. Edit <code>data/overrides/categories.yaml</code>.</p>";
        return;
    }
    // Count venues per cuisine so the user sees up front whether a
    // checkbox will narrow the map to 100 or to 2.
    const counts = {};
    for (const r of state.data.restaurants) {
        for (const c of (r.cuisine || [])) counts[c] = (counts[c] || 0) + 1;
    }
    host.innerHTML = "<legend>Cuisine</legend>" + sorted.map(c =>
        `<label><input type="checkbox" data-cuisine="${escapeHtml(c)}"
          ${state.cuisines.has(c) ? "checked" : ""}> ${escapeHtml(c)} <span class="count-tag">(${counts[c] || 0})</span></label>`
    ).join("");
    host.querySelectorAll("[data-cuisine]").forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.cuisines.add(cb.dataset.cuisine);
            else state.cuisines.delete(cb.dataset.cuisine);
            persistFilters();
            render();
        });
    });
}

function buildPriceAndNeighborhoodFilters() {
    // Both filters hide when there's no data populated yet, so an empty
    // map doesn't show an empty filter box. They reveal automatically as
    // soon as overrides start landing entries.
    // Counts make sparse-data filters honest: users see "$ (1)" or
    // "Old Market (12)" up front so clicking doesn't gray the map
    // unexpectedly.
    const priceCounts = {};
    const neighborhoodCounts = {};
    for (const r of state.data.restaurants) {
        if (r.price_tier) priceCounts[r.price_tier] = (priceCounts[r.price_tier] || 0) + 1;
        if (r.neighborhood) neighborhoodCounts[r.neighborhood] = (neighborhoodCounts[r.neighborhood] || 0) + 1;
    }
    const priceCount = Object.keys(priceCounts).length;
    const neighborhoodCount = Object.keys(neighborhoodCounts).length;
    document.getElementById("price-filter").hidden = priceCount === 0;
    document.getElementById("neighborhood-filter").hidden = neighborhoodCount === 0;
    // Update price labels to include the count.
    document.querySelectorAll("[data-price]").forEach(cb => {
        const tier = cb.dataset.price;
        const count = priceCounts[tier] || 0;
        const label = cb.parentElement;
        label.querySelector(".count-tag")?.remove();
        const span = document.createElement("span");
        span.className = "count-tag";
        span.textContent = ` (${count})`;
        label.appendChild(span);
        cb.disabled = count === 0;
    });
    const sel = document.getElementById("neighborhood-select");
    sel.innerHTML = '<option value="">Any neighborhood</option>' +
        Object.entries(neighborhoodCounts)
            .sort()
            .map(([n, c]) =>
                `<option value="${escapeHtml(n)}"${state.neighborhood === n ? " selected" : ""}>${escapeHtml(n)} (${c})</option>`
            ).join("");
}

// ---------- home location ----------

function renderHomeMarker() {
    if (state.homeMarker) {
        state.map.removeLayer(state.homeMarker);
        state.homeMarker = null;
    }
    if (!state.home) return;
    // A divIcon with the 🏠 emoji is clearer than an unlabeled circle: at a
    // glance the user knows what that point on the map is. The transparent
    // bg + drop-shadow keeps it visible on either light or dark map tiles.
    const icon = L.divIcon({
        className: "home-icon",
        html: "🏠",
        iconSize: [28, 28],
        iconAnchor: [14, 14],
    });
    // The marker IS the 🏠 emoji, so the tooltip just needs to confirm "yes,
    // this is your home" without repeating the icon. Keeping it short also
    // avoids showing the Nominatim display_name, which is often long and
    // sometimes contains the user's geocoded street address that they may
    // not want hovering above the map (privacy nudge).
    state.homeMarker = L.marker([state.home.lat, state.home.lng], { icon })
        .addTo(state.map)
        .bindTooltip("Home");
}

function renderRadiusCircle() {
    // Visualizes the currently-set radius filter as a translucent circle
    // around the home point. Helps the user see at a glance what area is
    // included. interactive:false so clicks fall through to venues underneath.
    if (state.radiusCircle) {
        state.map.removeLayer(state.radiusCircle);
        state.radiusCircle = null;
    }
    if (!state.home || state.radiusMi == null) return;
    state.radiusCircle = L.circle([state.home.lat, state.home.lng], {
        radius: state.radiusMi * 1609.344,  // miles to meters
        color: "#7a5af5",
        weight: 1.5,
        opacity: 0.55,
        fillColor: "#7a5af5",
        fillOpacity: 0.08,
        interactive: false,
    }).addTo(state.map);
}

function setHome(lat, lng, label = "") {
    state.home = { lat, lng, label };
    persistHome();
    renderHomeMarker();
    renderRadiusCircle();
    refreshHomeSheet();
    updateRadiusFilterUI();
    // If the venue sheet is open, re-render so the new distance shows up.
    // (We don't have a reference to the active venue, so just hide; user can re-tap.)
    document.getElementById("venue-sheet").classList.add("hidden");
    render();  // re-sort the list and refresh per-row distances
}

function clearHome() {
    state.home = null;
    persistHome();
    renderHomeMarker();
    renderRadiusCircle();
    refreshHomeSheet();
    updateRadiusFilterUI();
    render();
}

function refreshHomeSheet() {
    const el = document.getElementById("home-current");
    if (state.home) {
        const label = state.home.label || `${state.home.lat.toFixed(4)}, ${state.home.lng.toFixed(4)}`;
        el.textContent = `Set: ${label}`;
    } else {
        el.textContent = "Not set. Distance lines won't show until you set one.";
    }
}

async function geocodeHomeAddress() {
    const input = document.getElementById("home-address");
    const status = document.getElementById("home-geocode-status");
    const q = input.value.trim();
    if (!q) {
        status.textContent = "Enter an address first.";
        return;
    }
    status.textContent = "Looking up...";
    try {
        const url = "https://nominatim.openstreetmap.org/search?format=json&limit=1" +
            "&countrycodes=us&q=" + encodeURIComponent(q);
        const r = await fetch(url, {
            headers: { "Accept": "application/json" },
        });
        const results = await r.json();
        if (!results.length) {
            status.textContent = "No match. Try adding city/state.";
            return;
        }
        const top = results[0];
        const lat = parseFloat(top.lat);
        const lng = parseFloat(top.lon);
        setHome(lat, lng, top.display_name);
        status.textContent = `Found: ${top.display_name.slice(0, 80)}`;
        state.map.setView([lat, lng], 14);
    } catch (e) {
        status.textContent = "Lookup failed: " + e.message;
    }
}

function startPickingHomeOnMap() {
    state.pickingHomeOnMap = true;
    document.getElementById("home-sheet").classList.add("hidden");
    showBanner("Tap the map to set home");
    state.map.getContainer().style.cursor = "crosshair";
}

function setHomeFromCurrentLocation() {
    if (state.userLocation) {
        setHome(state.userLocation[0], state.userLocation[1], "Current location");
        return;
    }
    // Otherwise prompt for permission via locateMe; setHome called from there if granted.
    if (!navigator.geolocation) {
        alert("Geolocation not supported.");
        return;
    }
    navigator.geolocation.getCurrentPosition(
        pos => setHome(pos.coords.latitude, pos.coords.longitude, "Current location"),
        err => alert("Couldn't get location: " + err.message),
        { enableHighAccuracy: false, timeout: 10000 },
    );
}

function openHomeSheet() {
    refreshHomeSheet();
    document.getElementById("home-sheet").classList.remove("hidden");
}

// ---------- geolocation ----------

function locateMe() {
    if (!navigator.geolocation) {
        alert("Geolocation not supported in this browser.");
        return;
    }
    navigator.geolocation.getCurrentPosition(
        pos => {
            const ll = [pos.coords.latitude, pos.coords.longitude];
            state.userLocation = ll;
            if (state.userMarker) state.map.removeLayer(state.userMarker);
            state.userMarker = L.circleMarker(ll, {
                radius: 8, color: "#fff", weight: 2,
                fillColor: "#4285f4", fillOpacity: 0.9,
            }).addTo(state.map).bindTooltip("You are here");
            state.map.setView(ll, 13);
            document.getElementById("locate-btn").classList.add("active");
            render();  // re-sort the list by distance from current location
        },
        err => alert("Could not get location: " + err.message),
        { enableHighAccuracy: false, timeout: 10000 },
    );
}

// ---------- control wiring ----------

function applyFilterUI() {
    document.querySelectorAll("[data-kind]").forEach(cb => {
        cb.checked = state.kinds.has(cb.dataset.kind);
    });
    document.querySelectorAll("[data-price]").forEach(cb => {
        cb.checked = state.priceTiers.has(cb.dataset.price);
    });
    const nbSel = document.getElementById("neighborhood-select");
    if (nbSel) nbSel.value = state.neighborhood || "";
    document.getElementById("now-only").checked = state.nowOnly;
    document.getElementById("favorites-only").checked = state.favoritesOnly;
    document.getElementById("needs-review-only").checked = state.needsReviewOnly;
    document.getElementById("reverse-only").checked = state.reverseOnly;
    const slider = document.getElementById("at-hour");
    if (state.atHour === null) {
        slider.value = "";
        document.getElementById("at-hour-label").textContent = "Any time";
    } else {
        slider.value = String(state.atHour);
        document.getElementById("at-hour-label").textContent = "At " + formatTime12(`${state.atHour}:00`);
    }
    updateRadiusFilterUI();
}

function clearAllFilters() {
    state.kinds = new Set(DEFAULT_FILTERS.kinds);
    state.nowOnly = DEFAULT_FILTERS.nowOnly;
    state.atHour = DEFAULT_FILTERS.atHour;
    state.favoritesOnly = DEFAULT_FILTERS.favoritesOnly;
    state.cuisines = new Set(DEFAULT_FILTERS.cuisines);
    state.radiusMi = DEFAULT_FILTERS.radiusMi;
    state.priceTiers = new Set(DEFAULT_FILTERS.priceTiers);
    state.neighborhood = DEFAULT_FILTERS.neighborhood;
    state.needsReviewOnly = DEFAULT_FILTERS.needsReviewOnly;
    applyFilterUI();
    buildCuisineFilter();
    buildPriceAndNeighborhoodFilters();
    persistFilters();
    render();
}

function updateRadiusFilterUI() {
    // Radius is only meaningful with a home location. Hide the fieldset until
    // home is set; reset the slider when home is cleared so a stale filter
    // doesn't haunt the next session.
    const fieldset = document.getElementById("radius-filter");
    if (!fieldset) return;
    const slider = document.getElementById("radius");
    const label = document.getElementById("radius-label");
    if (state.home) {
        fieldset.hidden = false;
        if (state.radiusMi == null) {
            slider.value = "";
            label.textContent = "Any distance";
        } else {
            slider.value = String(state.radiusMi);
            label.textContent = `Within ${state.radiusMi} mi`;
        }
    } else {
        fieldset.hidden = true;
        // Don't keep filtering by a radius the user can no longer see.
        state.radiusMi = null;
    }
}

function wireControls() {
    document.querySelectorAll(".day-tabs button").forEach(btn => {
        btn.addEventListener("click", () => {
            state.selectedDay = btn.dataset.day;
            updateDayCounts();
            render();
        });
    });
    document.getElementById("filter-btn").addEventListener("click", () => {
        document.getElementById("filter-sheet").classList.toggle("hidden");
    });
    document.getElementById("close-filter").addEventListener("click", () => {
        document.getElementById("filter-sheet").classList.add("hidden");
    });
    document.getElementById("clear-filters").addEventListener("click", clearAllFilters);
    document.querySelectorAll("[data-kind]").forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.kinds.add(cb.dataset.kind);
            else state.kinds.delete(cb.dataset.kind);
            persistFilters();
            render();
        });
    });
    document.querySelectorAll("[data-price]").forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.priceTiers.add(cb.dataset.price);
            else state.priceTiers.delete(cb.dataset.price);
            persistFilters();
            render();
        });
    });
    document.getElementById("neighborhood-select").addEventListener("change", e => {
        state.neighborhood = e.target.value || null;
        persistFilters();
        render();
    });
    document.getElementById("now-only").addEventListener("change", e => {
        state.nowOnly = e.target.checked;
        if (e.target.checked) {
            document.getElementById("at-hour").value = "";
            state.atHour = null;
            document.getElementById("at-hour-label").textContent = "Any time";
        }
        persistFilters();
        render();
    });
    document.getElementById("at-hour").addEventListener("input", e => {
        const v = e.target.value;
        if (v === "") {
            state.atHour = null;
            document.getElementById("at-hour-label").textContent = "Any time";
        } else {
            state.atHour = Number(v);
            document.getElementById("at-hour-label").textContent = "At " + formatTime12(`${state.atHour}:00`);
            document.getElementById("now-only").checked = false;
            state.nowOnly = false;
        }
        persistFilters();
        render();
    });
    document.getElementById("favorites-only").addEventListener("change", e => {
        state.favoritesOnly = e.target.checked;
        persistFilters();
        render();
    });
    document.getElementById("needs-review-only").addEventListener("change", e => {
        state.needsReviewOnly = e.target.checked;
        persistFilters();
        render();
    });
    document.getElementById("reverse-only").addEventListener("change", e => {
        state.reverseOnly = e.target.checked;
        persistFilters();
        render();
    });
    document.getElementById("radius").addEventListener("input", e => {
        const v = e.target.value;
        if (v === "") {
            state.radiusMi = null;
            document.getElementById("radius-label").textContent = "Any distance";
        } else {
            state.radiusMi = Number(v);
            document.getElementById("radius-label").textContent = `Within ${state.radiusMi} mi`;
        }
        persistFilters();
        renderRadiusCircle();
        render();
    });
    // Double-click the slider thumb to clear (drag-to-zero would be < min=1).
    document.getElementById("radius").addEventListener("dblclick", e => {
        e.target.value = "";
        state.radiusMi = null;
        document.getElementById("radius-label").textContent = "Any distance";
        persistFilters();
        renderRadiusCircle();
        render();
    });
    document.getElementById("locate-btn").addEventListener("click", locateMe);
    document.getElementById("home-btn").addEventListener("click", openHomeSheet);
    document.getElementById("close-home").addEventListener("click", () => {
        document.getElementById("home-sheet").classList.add("hidden");
    });
    document.getElementById("home-geocode-btn").addEventListener("click", geocodeHomeAddress);
    document.getElementById("home-address").addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); geocodeHomeAddress(); }
    });
    document.getElementById("home-from-map").addEventListener("click", startPickingHomeOnMap);
    document.getElementById("home-from-locate").addEventListener("click", setHomeFromCurrentLocation);
    document.getElementById("home-clear").addEventListener("click", clearHome);
    document.querySelectorAll("#view-toggle button").forEach(btn => {
        btn.addEventListener("click", () => setView(btn.dataset.view));
    });
    document.getElementById("open-contribute-btn").addEventListener("click", () => {
        openContributeSheet(null);
    });
    document.getElementById("contribute-close").addEventListener("click", () => {
        const sheet = document.getElementById("contribute-sheet");
        sheet.classList.add("hidden");
        // Clear iframe src so leaving the sheet stops any audio/animations and
        // resets form state on the next open.
        document.getElementById("contribute-iframe").src = "about:blank";
    });

    // Crossing the 900px breakpoint (or any resize) can leave Leaflet with
    // stale dimensions if its container was hidden at init time. Nudge it.
    window.addEventListener("resize", () => {
        if (state.map) state.map.invalidateSize();
    });

    // Map-click handler. Two responsibilities:
    //  - In pick-home mode, claim the next click to set the home location.
    //  - Otherwise, treat the click as "dismiss" for any open sheet so the user
    //    can tap the map to get back to a clean view (matches the iOS/Maps
    //    convention for bottom sheets).
    //  Leaflet only fires this event for clicks that didn't land on a marker
    //  or other interactive layer, so tapping a venue still opens its sheet.
    state.map.on("click", e => {
        if (state.pickingHomeOnMap) {
            state.pickingHomeOnMap = false;
            hideBanner();
            state.map.getContainer().style.cursor = "";
            setHome(e.latlng.lat, e.latlng.lng, "Picked on map");
            return;
        }
        // Leaflet fires map "click" alongside marker "click" for the same
        // pointer event. Suppress the background-dismiss when a marker
        // handler just ran, otherwise the venue sheet would open and close
        // in the same tap.
        if (Date.now() - state.lastMarkerClickAt < 100) return;
        dismissOpenSheets();
    });
}

function dismissOpenSheets() {
    const venueSheet = document.getElementById("venue-sheet");
    const contributeSheet = document.getElementById("contribute-sheet");
    const wasOpen = !venueSheet.classList.contains("hidden")
        || !contributeSheet.classList.contains("hidden");
    if (!wasOpen) return;
    venueSheet.classList.add("hidden");
    contributeSheet.classList.add("hidden");
    document.getElementById("contribute-iframe").src = "about:blank";
    if (state.selectedMarker) {
        state.selectedMarker.setStyle(markerStyle(state.selectedMarker._kind, false));
        state.selectedMarker = null;
    }
    state.selectedId = null;
    document.querySelectorAll(".venue-row.selected").forEach(el => el.classList.remove("selected"));
}

// ---------- boot ----------

(async function () {
    loadPersistedFilters();
    loadFavorites();
    loadHome();
    loadView();
    document.body.dataset.view = state.view;
    setView(state.view);  // syncs aria-selected on the toggle buttons
    initMap();
    wireControls();
    renderHomeMarker();
    renderRadiusCircle();
    try {
        state.data = await loadData();
        buildCuisineFilter();
        buildPriceAndNeighborhoodFilters();
        applyFilterUI();
        render();
    } catch (e) {
        console.error(e);
        document.getElementById("map").innerHTML =
            `<p>Could not load data: ${escapeHtml(e.message)}</p>`;
    }
})();
