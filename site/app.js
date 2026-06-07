const JS_DAY = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

const state = {
    data: null,
    selectedDay: JS_DAY[new Date().getDay()],
    kinds: new Set(["happy_hour"]),
    nowOnly: false,
    atHour: null,           // null = any time; integer 0-23 = filter to deals active at that hour
    favoritesOnly: false,
    cuisines: new Set(),    // empty = all cuisines (or restaurants with no cuisine)
    markers: [],
    selectedMarker: null,
    map: null,
};

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
}

// "15:00" -> "3:00 PM", "00:30" -> "12:30 AM"
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

function isActiveNow(w) {
    const now = new Date();
    if (JS_DAY[now.getDay()] !== w.day) return false;
    const cur = now.getHours() * 60 + now.getMinutes();
    return windowContainsMinute(w, cur);
}

function windowContainsMinute(w, minuteOfDay) {
    const [sh, sm] = w.start.split(":").map(Number);
    const [eh, em] = (w.end || "23:59").split(":").map(Number);
    return minuteOfDay >= sh * 60 + sm && minuteOfDay <= eh * 60 + em;
}

function matchesFilters(r) {
    if (state.favoritesOnly) {
        const tags = r.personal?.tags || [];
        if (!tags.includes("favorite")) return false;
    }
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
                const minute = state.atHour * 60;
                if (!wins.some(w => windowContainsMinute(w, minute))) return false;
            }
        }
        return true;
    });
}

function clearMarkers() {
    state.markers.forEach(m => state.map.removeLayer(m));
    state.markers = [];
    state.selectedMarker = null;
}

function markerStyle(selected) {
    return {
        radius: selected ? 11 : 7,
        weight: selected ? 3 : 1,
        color: selected ? "#fff" : "#2c5aa0",
        fillColor: selected ? "#d9534f" : "#2c5aa0",
        fillOpacity: 0.9,
    };
}

function selectMarker(marker) {
    if (state.selectedMarker && state.selectedMarker !== marker) {
        state.selectedMarker.setStyle(markerStyle(false));
    }
    marker.setStyle(markerStyle(true));
    marker.bringToFront();
    state.selectedMarker = marker;
}

function render() {
    if (!state.map || !state.data) return;
    clearMarkers();
    for (const r of state.data.restaurants) {
        if (r.lat == null || r.lng == null) continue;
        if (!matchesFilters(r)) continue;
        const marker = L.circleMarker([r.lat, r.lng], markerStyle(false)).addTo(state.map);
        marker.on("click", () => {
            selectMarker(marker);
            showVenue(r);
        });
        state.markers.push(marker);
    }
}

function escapeHtml(s) {
    return String(s).replace(/[<>&"]/g, c =>
        ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;" }[c]));
}

function fmtMoney(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(2) : "?";
}

function renderDeal(d) {
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
        return `<div class="venue-deal"><span class="kind">happy hour</span>${wins}</div>`;
    }
    if (d.kind === "special") {
        return `<div class="venue-deal"><span class="kind">special</span>${escapeHtml(d.title || "")}
                <br><small>${escapeHtml(d.valid_from || "?")} to ${escapeHtml(d.valid_until || "?")}</small></div>`;
    }
    if (d.kind === "voucher") {
        return `<div class="venue-deal"><span class="kind">voucher</span>${escapeHtml(d.title || "")}
                <br><small>$${fmtMoney(d.original_price)} to $${fmtMoney(d.sale_price)} (save $${fmtMoney(d.savings)})</small></div>`;
    }
    return "";
}

function showVenue(r) {
    const sheet = document.getElementById("venue-sheet");
    const cuisineLine = (r.cuisine && r.cuisine.length)
        ? `<p class="meta">${escapeHtml(r.cuisine.join(", "))}${r.neighborhood ? " &middot; " + escapeHtml(r.neighborhood) : ""}</p>`
        : "";
    sheet.innerHTML = `
        <h2>${escapeHtml(r.name)}</h2>
        ${cuisineLine}
        <p>${escapeHtml(r.address || "(no address yet)")}</p>
        ${(r.deals || []).map(renderDeal).join("")}
        <p><a target="_blank"
              href="https://www.google.com/maps/search/${encodeURIComponent(r.name + " Omaha NE")}">
              Open in Google Maps</a></p>
        ${r.personal?.notes ? `<p><em>${escapeHtml(r.personal.notes)}</em></p>` : ""}
        <button id="venue-close">Close</button>
    `;
    sheet.classList.remove("hidden");
    document.getElementById("venue-close").addEventListener("click", () => {
        sheet.classList.add("hidden");
        if (state.selectedMarker) {
            state.selectedMarker.setStyle(markerStyle(false));
            state.selectedMarker = null;
        }
    });
}

function buildCuisineFilter() {
    const all = new Set();
    for (const r of state.data.restaurants) {
        (r.cuisine || []).forEach(c => all.add(c));
    }
    const sorted = Array.from(all).sort();
    const host = document.getElementById("cuisine-filter");
    if (sorted.length === 0) {
        host.innerHTML = "<p class='hint'>No cuisine data yet. Edit <code>data/overrides/categories.yaml</code> to enable this filter.</p>";
        return;
    }
    host.innerHTML = "<legend>Cuisine</legend>" + sorted.map(c =>
        `<label><input type="checkbox" data-cuisine="${escapeHtml(c)}"> ${escapeHtml(c)}</label>`
    ).join("");
    host.querySelectorAll("[data-cuisine]").forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.cuisines.add(cb.dataset.cuisine);
            else state.cuisines.delete(cb.dataset.cuisine);
            render();
        });
    });
}

function wireControls() {
    document.querySelectorAll(".day-tabs button").forEach(btn => {
        btn.addEventListener("click", () => {
            state.selectedDay = btn.dataset.day;
            document.querySelectorAll(".day-tabs button").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            render();
        });
        if (btn.dataset.day === state.selectedDay) btn.classList.add("active");
    });
    document.getElementById("filter-btn").addEventListener("click", () => {
        document.getElementById("filter-sheet").classList.toggle("hidden");
    });
    document.getElementById("close-filter").addEventListener("click", () => {
        document.getElementById("filter-sheet").classList.add("hidden");
    });
    document.querySelectorAll("[data-kind]").forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.kinds.add(cb.dataset.kind);
            else state.kinds.delete(cb.dataset.kind);
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
        render();
    });
    document.getElementById("favorites-only").addEventListener("change", e => {
        state.favoritesOnly = e.target.checked; render();
    });
}

(async function () {
    initMap();
    wireControls();
    try {
        state.data = await loadData();
        buildCuisineFilter();
        render();
    } catch (e) {
        console.error(e);
        document.getElementById("map").innerHTML = `<p>Could not load data: ${escapeHtml(e.message)}</p>`;
    }
})();
