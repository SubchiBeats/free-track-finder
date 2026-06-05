// App orchestration — wires search, filters, views, wheel, player, crate, storage.

import * as api from "./api.js";
import { crate, favorites, history, filters as filterStore, trackKey } from "./store.js";
import { camelotLabel, ALL_CAMELOT, compatible } from "./keys.js";
import { buildWheel } from "./camelot.js";
import { player, onPlayerEvent } from "./player.js";
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

function gatherFilters() {
  return {
    bpm_min: numOrNull("#bpm-min"),
    bpm_max: numOrNull("#bpm-max"),
    key: $("#key-select").value || null,
    harmonic: $("#harmonic-toggle").checked,
    genre: $("#genre").value.trim(),
    format: $("#format-select").value,
    min_bitrate: numOrNull("#min-bitrate"),
    exclude_gated: $("#exclude-gated").checked,
    sort_by: $("#sort-select").value,
    max_results: Number($("#max-results").value) || 50,
    platforms: $$("#platform-toggles input:checked").map((b) => b.value),
  };
}

function restoreFilters() {
  const f = filterStore.get();
  if (!f) return;
  setVal("#bpm-min", f.bpm_min); setVal("#bpm-max", f.bpm_max);
  if (f.key) setSelectedKey(f.key);
  $("#harmonic-toggle").checked = !!f.harmonic; state.harmonic = !!f.harmonic;
  setVal("#genre", f.genre); setVal("#format-select", f.format);
  setVal("#min-bitrate", f.min_bitrate);
  $("#exclude-gated").checked = !!f.exclude_gated;
  setVal("#sort-select", f.sort_by); setVal("#max-results", f.max_results);
  syncBpmRanges();
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
    exclude_gated: f.exclude_gated,
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

function renderResults(results) {
  const cards = $("#results-cards");
  const tbody = $("#results-tbody");
  $("#empty-state").hidden = true;
  $("#loading-state").hidden = true;

  const meta = [];
  meta.push(`${state.tracks.length} track${state.tracks.length === 1 ? "" : "s"}`);
  if (results.search_time_seconds) meta.push(`in ${results.search_time_seconds.toFixed(1)}s`);
  if (results.bpm_range) meta.push(`BPM ${results.bpm_range}`);
  $("#results-meta").textContent = meta.join(" · ");
  ui.announce(`${state.tracks.length} tracks found.`);

  const cbs = {
    onPreview: previewTrack,
    onAdd: (t) => { if (crate.add(t)) { ui.toast(`Added “${t.title}” to crate`, "success"); updateCrateCount(); } },
    onFav: (t) => { const on = favorites.toggle(t); ui.toast(on ? "Saved to favorites" : "Removed from favorites"); },
  };

  cards.innerHTML = "";
  tbody.innerHTML = "";
  if (state.tracks.length === 0) {
    $("#empty-state").hidden = false;
    $("#empty-state").querySelector("p").innerHTML =
      "No free tracks matched. Try broadening filters, removing the key, or another genre.";
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

function copyCrateLinks() {
  const tracks = crate.all();
  if (tracks.length === 0) { ui.toast("Your crate is empty", "error"); return; }
  const text = tracks.map((t) => t.download_url || t.url).join("\n");
  navigator.clipboard.writeText(text)
    .then(() => ui.toast("Copied all links to clipboard", "success"))
    .catch(() => ui.toast("Clipboard blocked by browser", "error"));
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

/* ===================== EVENTS ===================== */
function syncBpmRanges() {
  const min = $("#bpm-min"), max = $("#bpm-max");
  const minR = $("#bpm-min-range"), maxR = $("#bpm-max-range");
  if (min.value) minR.value = min.value;
  if (max.value) maxR.value = max.value;
}

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

  // BPM range sliders <-> number inputs
  $("#bpm-min-range").addEventListener("input", (e) => { $("#bpm-min").value = e.target.value; });
  $("#bpm-max-range").addEventListener("input", (e) => { $("#bpm-max").value = e.target.value; });
  $("#bpm-min").addEventListener("input", syncBpmRanges);
  $("#bpm-max").addEventListener("input", syncBpmRanges);

  // View toggle
  $("#view-cards").addEventListener("click", () => { state.view = "cards"; applyView(); });
  $("#view-table").addEventListener("click", () => { state.view = "table"; applyView(); });

  // Wheel dialog
  const wheelDlg = $("#wheel-dialog");
  $("#wheel-open").addEventListener("click", () => { highlightWheel(state.selectedKey); wheelDlg.showModal(); });

  // Crate drawer
  const crateDlg = $("#crate-drawer");
  $("#crate-toggle").addEventListener("click", () => { refreshCrateDrawer(); crateDlg.showModal(); });
  $("#crate-clear").addEventListener("click", () => { crate.clear(); refreshCrateDrawer(); updateCrateCount(); });
  $("#crate-copy").addEventListener("click", copyCrateLinks);
  $$("[data-export]").forEach((b) => b.addEventListener("click", () => exportCrate(b.dataset.export)));

  // Generic dialog close buttons + backdrop click
  $$("[data-close-dialog]").forEach((b) => b.addEventListener("click", (e) => e.target.closest("dialog").close()));
  $$("dialog").forEach((dlg) => dlg.addEventListener("click", (e) => {
    if (e.target === dlg) dlg.close(); // click on backdrop
  }));
}

init();
