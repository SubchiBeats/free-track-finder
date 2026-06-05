// API client — thin fetch wrappers around the FastAPI backend.
// All calls share the same origin as the served frontend, so paths are relative.

async function jsonOrThrow(res) {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function getPlatforms() {
  return jsonOrThrow(await fetch("api/platforms"));
}

export async function search(params, { signal } = {}) {
  const res = await fetch("api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });
  return jsonOrThrow(res);
}

export async function compatibleKeys(key) {
  const res = await fetch(`api/keys/compatible?key=${encodeURIComponent(key)}`);
  return jsonOrThrow(res);
}

// Resolve a preview URL into something an <audio> element can play.
// SoundCloud transcodings need server-side resolution; Bandcamp URLs pass through.
export async function resolveStream(url) {
  const res = await fetch(`api/stream?url=${encodeURIComponent(url)}`);
  const data = await jsonOrThrow(res);
  return data.url;
}

// Export a crate (array of track objects) — triggers a browser file download.
export async function exportCrate(tracks, format, query = "crate") {
  const res = await fetch("api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tracks, format, query }),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const match = cd.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : `crate.${format}`;
  triggerDownload(blob, filename);
}

export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
