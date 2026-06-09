// localStorage persistence — crate, favorites, search history, last filters.
// No backend DB needed; everything lives in the browser.

const KEYS = {
  crate: "ftf.crate",
  favorites: "ftf.favorites",
  history: "ftf.history",
  filters: "ftf.filters",
};

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (_) {
    return fallback;
  }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* quota / private mode */ }
}

// Stable identity for a track across sessions.
export function trackKey(t) {
  return t.track_id ? `${t.platform}:${t.track_id}` : `${t.platform}:${t.url}`;
}

/* ---------- Crate ---------- */
export const crate = {
  all: () => read(KEYS.crate, []),
  has: (t) => crate.all().some((x) => trackKey(x) === trackKey(t)),
  add(t) {
    const list = crate.all();
    if (list.some((x) => trackKey(x) === trackKey(t))) return false;
    list.push(t);
    write(KEYS.crate, list);
    return true;
  },
  remove(key) { write(KEYS.crate, crate.all().filter((x) => trackKey(x) !== key)); },
  move(key, dir) {
    const list = crate.all();
    const i = list.findIndex((x) => trackKey(x) === key);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    write(KEYS.crate, list);
  },
  clear() { write(KEYS.crate, []); },
};

/* ---------- Favorites ---------- */
export const favorites = {
  all: () => read(KEYS.favorites, []),
  has: (t) => favorites.all().some((x) => trackKey(x) === trackKey(t)),
  toggle(t) {
    const list = favorites.all();
    const i = list.findIndex((x) => trackKey(x) === trackKey(t));
    if (i >= 0) { list.splice(i, 1); write(KEYS.favorites, list); return false; }
    list.push(t); write(KEYS.favorites, list); return true;
  },
};

/* ---------- Search history ---------- */
export const history = {
  all: () => read(KEYS.history, []),
  add(query) {
    if (!query) return;
    let list = read(KEYS.history, []).filter((q) => q.toLowerCase() !== query.toLowerCase());
    list.unshift(query);
    write(KEYS.history, list.slice(0, 8));
  },
  clear() { write(KEYS.history, []); },
};

/* ---------- Last-used filters ---------- */
export const filters = {
  get: () => read(KEYS.filters, null),
  set: (f) => write(KEYS.filters, f),
};
