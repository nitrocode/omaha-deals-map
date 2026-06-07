const JS_DAY = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

const state = {
    data: null,
    selectedDay: JS_DAY[new Date().getDay()],
    kinds: new Set(["happy_hour"]),
    nowOnly: false,
    favoritesOnly: false,
    markers: [],
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

function isActiveNow(w) {
    const now = new Date();
    if (JS_DAY[now.getDay()] !== w.day) return false;
    const cur = now.getHours() * 60 + now.getMinutes();
    const [sh, sm] = w.start.split(":").map(Number);
    const [eh, em] = (w.end || "23:59").split(":").map(Number);
    return cur >= sh * 60 + sm && cur <= eh * 60 + em;
}

function matchesFilters(r) {
    if (state.favoritesOnly) {
        const tags = r.personal?.tags || [];
        if (!tags.includes("favorite")) return false;
    }
    return r.deals.some(d => {
        if (!state.kinds.has(d.kind)) return false;
        if (d.kind === "happy_hour") {
            const wins = (d.windows || []).filter(w => w.day === state.selectedDay);
            if (wins.length === 0) return false;
            if (state.nowOnly && !wins.some(isActiveNow)) return false;
        }
        return true;
    });
}

function clearMarkers() {
    state.markers.forEach(m => state.map.removeLayer(m));
    state.markers = [];
}

function render() {
    if (!state.map || !state.data) return;
    clearMarkers();
    for (const r of state.data.restaurants) {
        if (r.lat == null || r.lng == null) continue;
        if (!matchesFilters(r)) continue;
        const marker = L.marker([r.lat, r.lng]).addTo(state.map);
        marker.on("click", () => showVenue(r));
        state.markers.push(marker);
    }
}

function escapeHtml(s) {
    return String(s).replace(/[<>&"]/g, c =>
        ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;" }[c]));
}

function renderDeal(d) {
    if (d.kind === "happy_hour") {
        const wins = (d.windows || [])
            .filter(w => w.day === state.selectedDay)
            .map(w => `${w.start}${w.end ? '-' + w.end : ''}${w.type === 'reverse_hh' ? ' (reverse)' : ''}`)
            .join(", ");
        return `<div class="venue-deal"><span class="kind">happy hour</span>${wins}</div>`;
    }
    if (d.kind === "special") {
        return `<div class="venue-deal"><span class="kind">special</span>${escapeHtml(d.title || "")}
                <br><small>${d.valid_from} to ${d.valid_until}</small></div>`;
    }
    if (d.kind === "voucher") {
        return `<div class="venue-deal"><span class="kind">voucher</span>${escapeHtml(d.title || "")}
                <br><small>$${d.original_price} to $${d.sale_price} (save $${d.savings})</small></div>`;
    }
    return "";
}

function showVenue(r) {
    const sheet = document.getElementById("venue-sheet");
    sheet.innerHTML = `
        <h2>${escapeHtml(r.name)}</h2>
        <p>${escapeHtml(r.address || "")}</p>
        ${(r.deals || []).map(renderDeal).join("")}
        <p><a target="_blank"
              href="https://www.google.com/maps/search/${encodeURIComponent(r.name + " Omaha NE")}">
              Open in Google Maps</a></p>
        ${r.personal?.notes ? `<p><em>${escapeHtml(r.personal.notes)}</em></p>` : ""}
        <button onclick="document.getElementById('venue-sheet').classList.add('hidden')">Close</button>
    `;
    sheet.classList.remove("hidden");
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
        state.nowOnly = e.target.checked; render();
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
        render();
    } catch (e) {
        console.error(e);
        document.getElementById("map").innerHTML = `<p>Could not load data: ${escapeHtml(e.message)}</p>`;
    }
})();
