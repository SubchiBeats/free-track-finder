// Rendering helpers: track cards, table rows, skeletons, toasts, SR announcements.
// Pure-ish DOM construction — event wiring lives in app.js via callbacks.

import { crate, favorites, trackKey } from "./store.js";
import { compatible } from "./keys.js";

const $ = (sel, root = document) => root.querySelector(sel);

const DL_LABEL = {
  direct: "⬇ Download",
  name_your_price: "⬇ Free $0",
  gated: "🔒 Unlock",
};

export function announce(msg) {
  const el = $("#sr-status");
  if (el) el.textContent = msg;
}

export function toast(message, kind = "") {
  const region = $("#toast-region");
  const el = document.createElement("div");
  el.className = `toast ${kind ? "is-" + kind : ""}`.trim();
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.textContent = message;
  region.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 250); }, 3600);
}

export function showSkeletons(container, n = 8) {
  container.innerHTML = "";
  for (let i = 0; i < n; i++) {
    const s = document.createElement("div");
    s.className = "skeleton";
    container.appendChild(s);
  }
}

function metaItem(text) {
  if (text === null || text === undefined || text === "") return "";
  return text;
}

// Build a single card from the <template>. callbacks: { onPreview, onAdd, onFav }
export function buildCard(track, callbacks) {
  const tpl = $("#card-template").content.firstElementChild.cloneNode(true);

  const img = $(".card-art img", tpl);
  if (track.artwork_url) { img.src = track.artwork_url; img.alt = `Artwork for ${track.title} by ${track.artist}`; }
  else { img.alt = ""; img.removeAttribute("src"); }

  // Quality badge
  const qb = $(".quality-badge", tpl);
  qb.textContent = track.quality_tier && track.quality_tier !== "unknown" ? track.quality_tier : "";
  qb.classList.toggle("q-lossless", track.quality_tier === "lossless");
  qb.classList.toggle("q-high", track.quality_tier === "high");
  if (!qb.textContent) qb.hidden = true;

  // Title + link
  const titleLink = $(".card-title a", tpl);
  titleLink.textContent = track.title;
  titleLink.href = track.url;
  $(".card-artist", tpl).textContent = track.artist;

  // Meta chips
  $(".m-bpm", tpl).textContent = track.bpm ? `${Math.round(track.bpm)} BPM` : "";
  $(".m-key", tpl).textContent = track.camelot_key ? `${track.key || ""} ${track.camelot_key}`.trim() : "";
  $(".m-genre", tpl).textContent = metaItem(track.genre);
  $(".m-dur", tpl).textContent = metaItem(track.duration_formatted);
  $(".m-fmt", tpl).textContent = (track.file_format && track.file_format !== "unknown") ? track.file_format.toUpperCase() : "";

  // Preview button
  const playBtn = $(".card-play", tpl);
  if (track.preview_url) {
    playBtn.hidden = false;
    playBtn.addEventListener("click", () => callbacks.onPreview(track, playBtn));
  }

  // Estimate-BPM button (only useful when there's a preview and no BPM yet)
  const estBtn = $(".card-estbpm", tpl);
  if (track.preview_url && !track.bpm && callbacks.onEstimateBpm) {
    estBtn.hidden = false;
    estBtn.addEventListener("click", async () => {
      estBtn.disabled = true;
      estBtn.textContent = "Analysing…";
      try {
        const bpm = await callbacks.onEstimateBpm(track);
        $(".m-bpm", tpl).textContent = `~${bpm} BPM`;
        estBtn.hidden = true;
      } catch (err) {
        estBtn.disabled = false;
        estBtn.textContent = "Est. BPM";
        callbacks.onEstimateError && callbacks.onEstimateError(err);
      }
    });
  }

  // Get / page
  const get = $(".card-get", tpl);
  get.textContent = DL_LABEL[track.download_type] || "⬇ Get";
  get.href = track.download_url || track.url;
  const open = $(".card-open", tpl);
  open.href = track.url;

  // Add to crate
  const add = $(".card-add", tpl);
  const refreshAdd = () => {
    const inCrate = crate.has(track);
    add.textContent = inCrate ? "✓ In crate" : "+ Crate";
    add.disabled = inCrate;
  };
  refreshAdd();
  add.addEventListener("click", () => { callbacks.onAdd(track); refreshAdd(); });

  // Favorite
  const fav = $(".card-fav", tpl);
  const refreshFav = () => {
    const isFav = favorites.has(track);
    fav.setAttribute("aria-pressed", String(isFav));
    fav.textContent = isFav ? "♥" : "♡";
  };
  refreshFav();
  fav.addEventListener("click", () => { callbacks.onFav(track); refreshFav(); });

  return tpl;
}

export function buildRow(track, callbacks) {
  const tr = document.createElement("tr");
  const cell = (text, cls) => {
    const td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text ?? "—";
    return td;
  };

  const titleTd = document.createElement("td");
  const a = document.createElement("a");
  a.href = track.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = track.title;
  titleTd.appendChild(a);
  tr.appendChild(titleTd);

  tr.appendChild(cell(track.artist));
  tr.appendChild(cell(track.bpm ? Math.round(track.bpm) : "—"));
  tr.appendChild(cell(track.key || "—"));
  tr.appendChild(cell(track.camelot_key || "—", "t-key"));
  tr.appendChild(cell(track.genre || "—"));
  tr.appendChild(cell(track.duration_formatted || "—"));
  tr.appendChild(cell((track.file_format || "—").toUpperCase()));
  tr.appendChild(cell(track.quality_tier || "—"));
  tr.appendChild(cell(track.platform));

  const actions = document.createElement("td");
  actions.className = "row-actions";
  if (track.preview_url) {
    const p = document.createElement("button");
    p.type = "button"; p.className = "btn btn-icon btn-sm"; p.textContent = "▶";
    p.setAttribute("aria-label", `Preview ${track.title}`);
    p.addEventListener("click", () => callbacks.onPreview(track, p));
    actions.appendChild(p);
  }
  const get = document.createElement("a");
  get.className = "btn btn-sm btn-primary"; get.href = track.download_url || track.url;
  get.target = "_blank"; get.rel = "noopener"; get.textContent = "Get";
  actions.appendChild(get);

  const add = document.createElement("button");
  add.type = "button"; add.className = "btn btn-sm"; add.textContent = crate.has(track) ? "✓" : "+";
  add.setAttribute("aria-label", `Add ${track.title} to crate`);
  add.addEventListener("click", () => { callbacks.onAdd(track); add.textContent = "✓"; });
  actions.appendChild(add);

  tr.appendChild(actions);
  return tr;
}

export function renderCrate(listEl, emptyEl, callbacks) {
  const items = crate.all();
  listEl.innerHTML = "";
  emptyEl.hidden = items.length > 0;
  items.forEach((t, idx) => {
    // Harmonic-flow hint: is this track compatible with the previous one?
    if (idx > 0) {
      const prev = items[idx - 1];
      if (prev.camelot_key && t.camelot_key) {
        const ok = compatible(prev.camelot_key).includes(t.camelot_key);
        const flow = document.createElement("li");
        flow.className = `crate-flow ${ok ? "flow-ok" : "flow-warn"}`;
        flow.setAttribute("aria-hidden", "true");
        flow.textContent = ok
          ? `↕ harmonic: ${prev.camelot_key} → ${t.camelot_key} ✓`
          : `↕ key jump: ${prev.camelot_key} → ${t.camelot_key}`;
        listEl.appendChild(flow);
      }
    }

    const li = document.createElement("li");
    li.className = "crate-item";

    const img = document.createElement("img");
    if (t.artwork_url) img.src = t.artwork_url;
    img.alt = "";
    li.appendChild(img);

    const info = document.createElement("div");
    info.innerHTML = `<div class="ci-title"></div><div class="ci-sub"></div>`;
    info.querySelector(".ci-title").textContent = t.title;
    info.querySelector(".ci-sub").textContent =
      `${t.artist}${t.camelot_key ? " · " + t.camelot_key : ""}${t.bpm ? " · " + Math.round(t.bpm) + " BPM" : ""}`;
    li.appendChild(info);

    const controls = document.createElement("div");
    controls.className = "crate-item-controls";
    const key = trackKey(t);
    const mk = (label, aria, fn) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "btn btn-icon btn-sm"; b.textContent = label;
      b.setAttribute("aria-label", aria); b.addEventListener("click", fn); return b;
    };
    controls.appendChild(mk("↑", `Move ${t.title} up`, () => callbacks.onMove(key, -1)));
    controls.appendChild(mk("↓", `Move ${t.title} down`, () => callbacks.onMove(key, 1)));
    controls.appendChild(mk("✕", `Remove ${t.title}`, () => callbacks.onRemove(key)));
    li.appendChild(controls);

    listEl.appendChild(li);
  });
}

export function renderPlatformErrors(el, errors) {
  if (!errors || errors.length === 0) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = `<strong>Some platforms had trouble:</strong><ul>${
    errors.map((e) => `<li></li>`).join("")
  }</ul>`;
  el.querySelectorAll("li").forEach((li, i) => { li.textContent = errors[i]; });
}
