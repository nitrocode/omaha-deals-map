const JS_DAY = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const STORAGE_KEY = "omaha-deals-filters-v1";
const FAVORITES_KEY = "omaha-deals-favorites-v1";

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
};

const state = {
    data: null,
    today: JS_DAY[new Date().getDay()],
    selectedDay: JS_DAY[new Date().getDay()],
    kinds: new Set(DEFAULT_FILTERS.kinds),
    nowOnly: DEFAULT_FILTERS.nowOnly,
    atHour: DEFAULT_FILTERS.atHour,
    favoritesOnly: DEFAULT_FILTERS.favoritesOnly,
    cuisines: new Set(DEFAULT_FILTERS.cuisines),
    favorites: new Set(),
    markers: [],
    selectedMarker: null,
    cluster: null,
    map: null,
    userLocation: null,    // [lat, lng] or null
    userMarker: null,
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
    } catch (e) { /* ignore corrupt storage */ }
}

function persistFilters() {
    const f = {
        kinds: [...state.kinds],
        nowOnly: state.nowOnly,
        atHour: state.atHour,
        favoritesOnly: state.favoritesOnly,
        cuisines: [...state.cuisines],
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

function matchesFilters(r) {
    if (state.favoritesOnly && !isFavorite(r)) return false;
    if (state.cuisines.size > 0) {
        const cs = r.cuisine || [];
        if (!cs.some(c => state.cuisines.has(c))) return false;
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
    let visible = 0;
    for (const r of state.data.restaurants) {
        if (r.lat == null || r.lng == null) continue;
        if (!matchesFilters(r)) continue;
        const kind = primaryKindForRestaurant(r);
        const marker = L.circleMarker([r.lat, r.lng], markerStyle(kind, false));
        marker._kind = kind;
        marker.on("click", () => {
            selectMarker(marker, kind);
            showVenue(r);
        });
        state.cluster.addLayer(marker);
        state.markers.push(marker);
        visible++;
    }
    document.getElementById("empty-overlay").classList.toggle("hidden", visible > 0);
    updateDayCounts();
}

// ---------- venue sheet ----------

function renderDeal(d) {
    const kindClass = `kind kind-${d.kind}`;
    const dealTextLine = (d.raw_text && d.raw_text.trim())
        ? `<span class="deal-text">${escapeHtml(d.raw_text.trim())}</span>`
        : "";
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
                ${dealTextLine}</div>`;
    }
    if (d.kind === "special") {
        return `<div class="venue-deal"><span class="${kindClass}">special</span>${escapeHtml(d.title || "")}
                <br><small>${escapeHtml(d.valid_from || "?")} to ${escapeHtml(d.valid_until || "?")}</small>
                ${dealTextLine}</div>`;
    }
    if (d.kind === "voucher") {
        return `<div class="venue-deal"><span class="${kindClass}">voucher</span>${escapeHtml(d.title || "")}
                <br><small>$${fmtMoney(d.original_price)} to $${fmtMoney(d.sale_price)}
                (save $${fmtMoney(d.savings)})</small></div>`;
    }
    return "";
}

function showVenue(r) {
    const sheet = document.getElementById("venue-sheet");
    const cuisineLine = (r.cuisine && r.cuisine.length)
        ? `<p class="meta">${escapeHtml(r.cuisine.join(", "))}${r.neighborhood ? " &middot; " + escapeHtml(r.neighborhood) : ""}</p>`
        : "";
    const distance = state.userLocation
        ? `<p class="distance">${haversineMiles(state.userLocation, [r.lat, r.lng]).toFixed(1)} mi from you</p>`
        : "";
    const fav = state.favorites.has(r.id);
    const mapsUrl = `https://www.google.com/maps/search/${encodeURIComponent(r.name + " Omaha NE")}`;
    sheet.innerHTML = `
        <h2>${escapeHtml(r.name)}</h2>
        ${cuisineLine}
        <p>${escapeHtml(r.address || "(no address yet)")}</p>
        ${distance}
        <p>
          <button class="fav-btn ${fav ? "active" : ""}" id="fav-toggle">
            ${fav ? "♥ Favorited" : "♡ Favorite"}
          </button>
        </p>
        ${(r.deals || []).map(renderDeal).join("")}
        <p><a target="_blank" rel="noopener" href="${mapsUrl}">Open in Google Maps</a></p>
        ${r.personal?.notes ? `<p><em>${escapeHtml(r.personal.notes)}</em></p>` : ""}
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
    });
    document.getElementById("fav-toggle").addEventListener("click", () => {
        if (state.favorites.has(r.id)) state.favorites.delete(r.id);
        else state.favorites.add(r.id);
        persistFavorites();
        showVenue(r);  // re-render to flip the button
        render();      // re-render markers in case favoritesOnly is on
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
    host.innerHTML = "<legend>Cuisine</legend>" + sorted.map(c =>
        `<label><input type="checkbox" data-cuisine="${escapeHtml(c)}"
          ${state.cuisines.has(c) ? "checked" : ""}> ${escapeHtml(c)}</label>`
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
    document.getElementById("now-only").checked = state.nowOnly;
    document.getElementById("favorites-only").checked = state.favoritesOnly;
    const slider = document.getElementById("at-hour");
    if (state.atHour === null) {
        slider.value = "";
        document.getElementById("at-hour-label").textContent = "Any time";
    } else {
        slider.value = String(state.atHour);
        document.getElementById("at-hour-label").textContent = "At " + formatTime12(`${state.atHour}:00`);
    }
}

function clearAllFilters() {
    state.kinds = new Set(DEFAULT_FILTERS.kinds);
    state.nowOnly = DEFAULT_FILTERS.nowOnly;
    state.atHour = DEFAULT_FILTERS.atHour;
    state.favoritesOnly = DEFAULT_FILTERS.favoritesOnly;
    state.cuisines = new Set(DEFAULT_FILTERS.cuisines);
    applyFilterUI();
    buildCuisineFilter();  // re-render to clear checkmarks
    persistFilters();
    render();
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
    document.getElementById("locate-btn").addEventListener("click", locateMe);
}

// ---------- boot ----------

(async function () {
    loadPersistedFilters();
    loadFavorites();
    initMap();
    wireControls();
    try {
        state.data = await loadData();
        buildCuisineFilter();
        applyFilterUI();
        render();
    } catch (e) {
        console.error(e);
        document.getElementById("map").innerHTML =
            `<p>Could not load data: ${escapeHtml(e.message)}</p>`;
    }
})();
