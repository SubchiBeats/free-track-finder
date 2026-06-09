// App orchestration — wires search, filters, views, wheel, player, crate, storage.

import * as api from "./api.js";
import { crate, favorites, history, filters as filterStore, trackKey } from "./store.js";
import { camelotLabel, ALL_CAMELOT, compatible } from "./keys.js";
import { buildWheel } from "./camelot.js";
import { player, onPlayerEvent } from "./player.js";
import { estimateBpm } from "./bpm.js";
import * as ui from "./ui.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  tracks: [],
  view: "cards",
  selectedKey: null,
  harmonic: false,
  platforms: [],
  searching: false,
  controller: null,
};

let highlightWheel = () => {};

/* ===================== INIT ===================== */
async function init() {
  buildKeySelect();
  await loadPlatforms();
  setupWheel();
  restoreFilters();
  renderHistory();
  updateCrateCount();
  updateFavCount();
  wireEvents();
  wirePlayer();
}

function buildKeySelect() {
  const sel = $("#key-select");
  ALL_CAMELOT.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = `${c} — ${camelotLabel(c)}`;
    sel.appendChild(opt);
  });
}

async function loadPlatforms() {
  const wrap = $("#platform-toggles");
  try {
    state.platforms = await api.getPlatforms();
  } catch (_) {
    state.platforms = [
      { id: "soundcloud", name: "SoundCloud" },
      { id: "bandcamp", name: "Bandcamp" },
      { id: "hypeddit", name: "Hypeddit" },
    ];
  }
  wrap.innerHTML = "";
  state.platforms.forEach((p) => {
    const label = document.createElement("label");
    label.className = "checkbox";
    label.innerHTML = `<input type="checkbox" value="${p.id}" checked /><span></span>`;
    label.querySelector("span").textContent = p.name || p.id;
    if (p.notes) label.title = p.notes;
    wrap.appendChild(label);
  });
}

function setupWheel() {
  highlightWheel = buildWheel($("#wheel-container"), (camelot) => {
    setSelectedKey(camelot);
    highlightWheel(camelot);
    $("#wheel-selected").textContent = camelot
      ? `Filtering to ${camelot} (${camelotLabel(camelot)}) + compatible keys`
      : "Showing all keys";
  });
}

/* ===================== FILTERS <-> FORM ===================== */
function selectedPlatforms() {
  const boxes = $$("#platform-toggles input:checked");
  const all = $$("#platform-toggles input");
  if (boxes.length === 0 || boxes.length === all.length) return null; // null = all
  return boxes.map((b) => b.value);
}

function setSelectedKey(camelot) {
  state.selectedKey = camelot;
  $("#key-select").value = camelot || "";
}

const HIDE_MIX_SECONDS = 570; // 9:30

function gatherFilters() {
  const customMax = numOrNull("#max-minutes");
  let maxDuration = customMax ? customMax * 60 : null;
  if ($("#hide-mixes").checked) {
    maxDuration = maxDuration ? Math.min(maxDuration, HIDE_MIX_SECONDS) : HIDE_MIX_SECONDS;
  }
  return {
    bpm_min: numOrNull("#bpm-min"),
    bpm_max: numOrNull("#bpm-max"),
    known_bpm_only: $("#known-bpm-only").checked,
    key: $("#key-select").value || null,
    harmonic: $("#harmonic-toggle").checked,
    genre: $("#genre").value.trim(),
    format: $("#format-select").value,
    min_bitrate: numOrNull("#min-bitrate"),
    download_types: $$(".dl-type-cb:checked").map((b) => b.value),
    hide_mixes: $("#hide-mixes").checked,
    max_minutes: customMax,
    max_duration_seconds: maxDuration,
    sort_by: $("#sort-select").value,
    max_results: Number($("#max-results").value) || 50,
    platforms: $$("#platform-toggles input:checked").map((b) => b.value),
  };
}

function restoreFilters() {
  const f = filterStore.get();
  if (!f) return;
  setVal("#bpm-min", f.bpm_min); setVal("#bpm-max", f.bpm_max);
  if (f.known_bpm_only !== undefined) $("#known-bpm-only").checked = !!f.known_bpm_only;
  if (f.key) setSelectedKey(f.key);
  $("#harmonic-toggle").checked = !!f.harmonic; state.harmonic = !!f.harmonic;
  setVal("#genre", f.genre); setVal("#format-select", f.format);
  setVal("#min-bitrate", f.min_bitrate);
  if (Array.isArray(f.download_types) && f.download_types.length) {
    $$(".dl-type-cb").forEach((b) => { b.checked = f.download_types.includes(b.value); });
  }
  if (f.hide_mixes !== undefined) $("#hide-mixes").checked = !!f.hide_mixes;
  setVal("#max-minutes", f.max_minutes);
  setVal("#sort-select", f.sort_by); setVal("#max-results", f.max_results);
}

function numOrNull(sel) { const v = $(sel).value; return v === "" ? null : Number(v); }
function setVal(sel, v) { if (v !== null && v !== undefined && v !== "") $(sel).value = v; }

/* ===================== SEARCH ===================== */
async function runSearch(query) {
  if (!query) return;
  if (state.searching && state.controller) state.controller.abort();

  const f = gatherFilters();
  state.selectedKey = f.key;
  state.harmonic = f.harmonic;

  // Build backend params.
  const params = {
    query,
    platforms: selectedPlatforms(),
    bpm_min: f.bpm_min,
    bpm_max: f.bpm_max,
    key: f.harmonic ? null : f.key, // harmonic filtering done client-side over compatible set
    genres: f.genre ? [f.genre] : [],
    formats: f.format ? [f.format] : [],
    min_bitrate_kbps: f.min_bitrate,
    download_types: f.download_types.length === 3 ? [] : f.download_types,
    exclude_unknown_bpm: f.known_bpm_only,
    max_duration_seconds: f.max_duration_seconds,
    sort_by: f.sort_by,
    max_results: f.max_results,
  };

  filterStore.set(f);
  history.add(query);
  renderHistory();

  state.searching = true;
  state.controller = new AbortController();
  setSearchingUI(true);
  ui.announce(`Searching for ${query}…`);

  try {
    const results = await api.search(params, { signal: state.controller.signal });
    state.tracks = applyClientFilters(results.tracks, f);
    ui.renderPlatformErrors($("#platform-errors"), results.errors);
    renderResults(results);
  } catch (err) {
    if (err.name === "AbortError") return;
    showError(err.message || "Search failed.");
  } finally {
    state.searching = false;
    setSearchingUI(false);
  }
}

// Harmonic-key filtering happens here so the wheel selection includes neighbours.
function applyClientFilters(tracks, f) {
  if (f.harmonic && f.key) {
    const compat = new Set(compatible(f.key));
    return tracks.filter((t) => !t.camelot_key || compat.has(t.camelot_key));
  }
  return tracks;
}

const cardCallbacks = () => ({
  onPreview: previewTrack,
  onAdd: (t) => { if (crate.add(t)) { ui.toast(`Added “${t.title}” to crate`, "success"); updateCrateCount(); } },
  onFav: (t) => { const on = favorites.toggle(t); updateFavCount(); ui.toast(on ? "Saved to favorites" : "Removed from favorites"); },
  onEstimateBpm: async (t) => {
    const bpm = await estimateBpm(t.preview_url);
    t.bpm = bpm; // cache on the in-memory track so crate/export carry it
    return bpm;
  },
  onEstimateError: (err) => ui.toast(err.message || "Couldn't estimate BPM", "error"),
});

function renderResults(results) {
  const meta = [];
  meta.push(`${state.tracks.length} track${state.tracks.length === 1 ? "" : "s"}`);
  if (results.search_time_seconds) meta.push(`in ${results.search_time_seconds.toFixed(1)}s`);
  if (results.bpm_range) {
    const [lo, hi] = results.bpm_range.split("–");
    meta.push(lo === hi ? `BPM ${lo}` : `BPM ${results.bpm_range}`);
  }
  renderTrackList(meta.join(" · "), "No free tracks matched. Try broadening filters, removing the key, or another genre.");
}

// Shared renderer for both search results and the favorites view.
function renderTrackList(metaText, emptyMsg) {
  const cards = $("#results-cards");
  const tbody = $("#results-tbody");
  $("#empty-state").hidden = true;
  $("#loading-state").hidden = true;
  $("#results-meta").textContent = metaText;
  ui.announce(`${state.tracks.length} tracks.`);

  const cbs = cardCallbacks();
  cards.innerHTML = "";
  tbody.innerHTML = "";

  const hasTracks = state.tracks.length > 0;
  $("#add-all").hidden = !hasTracks;
  if (!hasTracks) {
    $("#empty-state").hidden = false;
    $("#empty-state").querySelector("p").innerHTML = emptyMsg;
    cards.hidden = true;
    $("#results-table-wrap").hidden = true;
    return;
  }

  state.tracks.forEach((t) => {
    cards.appendChild(ui.buildCard(t, cbs));
    tbody.appendChild(ui.buildRow(t, cbs));
  });
  applyView();
}

function showFavorites() {
  state.tracks = favorites.all();
  $("#platform-errors").hidden = true;
  $("#query").value = "";
  renderTrackList(
    `♥ ${state.tracks.length} saved favorite${state.tracks.length === 1 ? "" : "s"}`,
    "No favorites yet. Tap the ♥ on any track to save it here.",
  );
  $("#results").focus();
}

function applyView() {
  const isCards = state.view === "cards";
  $("#results-cards").hidden = !isCards || state.tracks.length === 0;
  $("#results-table-wrap").hidden = isCards || state.tracks.length === 0;
  $("#view-cards").classList.toggle("is-active", isCards);
  $("#view-cards").setAttribute("aria-pressed", String(isCards));
  $("#view-table").classList.toggle("is-active", !isCards);
  $("#view-table").setAttribute("aria-pressed", String(!isCards));
}

function setSearchingUI(on) {
  const btn = $("#search-btn");
  btn.disabled = on;
  btn.querySelector(".btn-label").textContent = on ? "Searching…" : "Search";
  if (on) {
    $("#empty-state").hidden = true;
    $("#results-cards").hidden = true;
    $("#results-table-wrap").hidden = true;
    $("#add-all").hidden = true;
    const usingBandcamp = $$("#platform-toggles input:checked").some((b) => b.value === "bandcamp");
    $("#results-meta").textContent = usingBandcamp
      ? "Searching… Bandcamp digs deep for free tracks, so this can take ~30s."
      : "Searching…";
    const sk = $("#loading-state");
    sk.hidden = false;
    ui.showSkeletons(sk, 8);
  } else {
    $("#loading-state").hidden = true;
  }
}

function showError(message) {
  ui.toast(message, "error");
  $("#loading-state").hidden = true;
  if (state.tracks.length === 0) $("#empty-state").hidden = false;
}

/* ===================== PREVIEW PLAYER ===================== */
async function previewTrack(track, btn) {
  try {
    await player.play(track);
  } catch (err) {
    ui.toast(err.message || "Preview unavailable", "error");
  }
}

function wirePlayer() {
  const bar = $("#player-bar");
  const playBtn = $("#player-play");
  const seek = $("#player-seek");
  const timeEl = $("#player-time");

  onPlayerEvent((type, data) => {
    if (type === "loading") { bar.hidden = false; bar.classList.add("is-loading"); $("#player-title").textContent = "Loading…"; }
    if (type === "track") {
      bar.hidden = false; bar.classList.remove("is-loading");
      $("#player-title").textContent = data.title;
      $("#player-artist").textContent = data.artist;
    }
    if (type === "play") playBtn.textContent = "⏸";
    if (type === "pause") playBtn.textContent = "▶";
    if (type === "ended") playBtn.textContent = "▶";
    if (type === "error") { bar.classList.remove("is-loading"); ui.toast("Could not play preview", "error"); }
    if (type === "time" && data.duration) {
      seek.value = (data.current / data.duration) * 100 || 0;
      timeEl.textContent = fmtTime(data.current);
    }
    if (type === "stop") bar.hidden = true;
  });

  playBtn.addEventListener("click", () => player.toggle());
  seek.addEventListener("input", () => player.seek(seek.value / 100));
  $("#player-vol").addEventListener("input", (e) => player.setVolume(Number(e.target.value)));
  $("#player-close").addEventListener("click", () => player.stop());
  player.setVolume(Number($("#player-vol").value));
}

function fmtTime(s) {
  if (!s || isNaN(s)) return "0:00";
  const m = Math.floor(s / 60); const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/* ===================== CRATE ===================== */
function updateCrateCount() { $("#crate-count").textContent = String(crate.all().length); }
function updateFavCount() { $("#fav-count").textContent = String(favorites.all().length); }

function addAllToCrate() {
  let added = 0;
  state.tracks.forEach((t) => { if (crate.add(t)) added++; });
  updateCrateCount();
  ui.toast(added ? `Added ${added} track${added === 1 ? "" : "s"} to crate` : "All already in crate", added ? "success" : "");
}

function refreshCrateDrawer() {
  ui.renderCrate($("#crate-list"), $("#crate-empty"), {
    onMove: (key, dir) => { crate.move(key, dir); refreshCrateDrawer(); },
    onRemove: (key) => { crate.remove(key); refreshCrateDrawer(); updateCrateCount(); },
  });
}

async function exportCrate(format) {
  const tracks = crate.all();
  if (tracks.length === 0) { ui.toast("Your crate is empty", "error"); return; }
  try {
    await api.exportCrate(tracks, format, "crate");
    ui.toast(`Exported ${tracks.length} tracks as ${format.toUpperCase()}`, "success");
  } catch (err) {
    ui.toast(err.message || "Export failed", "error");
  }
}

function copyToClipboard(text, okMsg) {
  navigator.clipboard.writeText(text)
    .then(() => ui.toast(okMsg, "success"))
    .catch(() => ui.toast("Clipboard blocked by browser", "error"));
}

function copyCrateLinks() {
  const tracks = crate.all();
  if (tracks.length === 0) { ui.toast("Your crate is empty", "error"); return; }
  copyToClipboard(tracks.map((t) => t.download_url || t.url).join("\n"), "Copied all links");
}

function copyTracklist() {
  const tracks = crate.all();
  if (tracks.length === 0) { ui.toast("Your crate is empty", "error"); return; }
  const lines = tracks.map((t, i) => {
    const tags = [t.camelot_key, t.bpm ? `${Math.round(t.bpm)} BPM` : null].filter(Boolean).join(", ");
    return `${i + 1}. ${t.artist} - ${t.title}${tags ? ` [${tags}]` : ""}`;
  });
  copyToClipboard(lines.join("\n"), "Copied tracklist");
}

function openAllPages() {
  const tracks = crate.all();
  if (tracks.length === 0) { ui.toast("Your crate is empty", "error"); return; }
  if (tracks.length > 8 && !confirm(`Open ${tracks.length} tabs?`)) return;
  tracks.forEach((t) => window.open(t.download_url || t.url, "_blank", "noopener"));
}

/* ===================== HISTORY ===================== */
function renderHistory() {
  const items = history.all();
  const row = $("#quick-row");
  const chips = $("#history-chips");
  row.hidden = items.length === 0;
  chips.innerHTML = "";
  items.forEach((q) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.textContent = q;
    b.addEventListener("click", () => { $("#query").value = q; runSearch(q); });
    chips.appendChild(b);
  });
}

/* ===================== CONVERTER ===================== */
function wireConverter() {
  const dlg = $("#convert-dialog");
  $("#convert-toggle").addEventListener("click", async () => {
    dlg.showModal();
    try {
      const info = await api.convertAvailable();
      $("#convert-unavailable").hidden = info.available;
      $("#convert-btn").disabled = !info.available;
    } catch (_) {
      $("#convert-unavailable").hidden = false;
      $("#convert-btn").disabled = true;
    }
  });

  $("#convert-btn").addEventListener("click", async () => {
    const fileInput = $("#convert-file");
    const file = fileInput.files[0];
    if (!file) { ui.toast("Choose an audio file first", "error"); return; }
    const btn = $("#convert-btn");
    btn.disabled = true; btn.textContent = "Converting…";
    try {
      await api.convertFile(file, $("#convert-target").value);
      ui.toast("Converted — check your downloads", "success");
    } catch (err) {
      ui.toast(err.message || "Conversion failed", "error");
    } finally {
      btn.disabled = false; btn.textContent = "Convert & download";
    }
  });
}

/* ===================== EVENTS ===================== */
function wireEvents() {
  $("#search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    runSearch($("#query").value.trim());
  });

  // Key select <-> wheel
  $("#key-select").addEventListener("change", (e) => {
    setSelectedKey(e.target.value || null);
    highlightWheel(e.target.value || null);
  });
  $("#harmonic-toggle").addEventListener("change", (e) => { state.harmonic = e.target.checked; });

  // BPM preset chips
  $$(".bpm-presets .chip").forEach((chip) => chip.addEventListener("click", () => {
    const [lo, hi] = (chip.dataset.bpm || "").split("-");
    $("#bpm-min").value = lo || "";
    $("#bpm-max").value = hi || "";
  }));

  // View toggle
  $("#view-cards").addEventListener("click", () => { state.view = "cards"; applyView(); });
  $("#view-table").addEventListener("click", () => { state.view = "table"; applyView(); });

  // Favorites view + add-all
  $("#favorites-toggle").addEventListener("click", showFavorites);
  $("#add-all").addEventListener("click", addAllToCrate);

  // Wheel dialog
  const wheelDlg = $("#wheel-dialog");
  $("#wheel-open").addEventListener("click", () => { highlightWheel(state.selectedKey); wheelDlg.showModal(); });

  // Crate drawer
  const crateDlg = $("#crate-drawer");
  $("#crate-toggle").addEventListener("click", () => { refreshCrateDrawer(); crateDlg.showModal(); });
  $("#crate-clear").addEventListener("click", () => {
    if (crate.all().length && !confirm("Clear the whole crate?")) return;
    crate.clear(); refreshCrateDrawer(); updateCrateCount();
  });
  $("#crate-copy").addEventListener("click", copyCrateLinks);
  $("#crate-tracklist").addEventListener("click", copyTracklist);
  $("#crate-openall").addEventListener("click", openAllPages);
  $$("[data-export]").forEach((b) => b.addEventListener("click", () => exportCrate(b.dataset.export)));

  // Converter dialog
  wireConverter();

  // Generic dialog close buttons + backdrop click
  $$("[data-close-dialog]").forEach((b) => b.addEventListener("click", (e) => e.target.closest("dialog").close()));
  $$("dialog").forEach((dlg) => dlg.addEventListener("click", (e) => {
    if (e.target === dlg) dlg.close(); // click on backdrop
  }));
}

init();
