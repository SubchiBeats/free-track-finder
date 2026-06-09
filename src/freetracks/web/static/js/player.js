// In-browser preview player built on the Web Audio API.
// Uses an <audio> element as the source node so we get streaming + a GainNode
// for volume (and a hook for future visualisation). Falls back gracefully if a
// stream can't be resolved or AudioContext is unavailable.

import { resolveStream } from "./api.js";

let ctx = null;
let gain = null;
let sourceNode = null;
const audio = new Audio();
audio.crossOrigin = "anonymous";
audio.preload = "none";

let current = null; // { key, title, artist }
const listeners = new Set();

function ensureGraph() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return false; // no Web Audio — we still play via the <audio> element
  if (!ctx) {
    ctx = new AC();
    gain = ctx.createGain();
    try {
      sourceNode = ctx.createMediaElementSource(audio);
      sourceNode.connect(gain).connect(ctx.destination);
    } catch (_) {
      // Cross-origin media without CORS taints the graph; fall back to element audio.
      sourceNode = null;
    }
  }
  return true;
}

function emit(type, data) {
  listeners.forEach((fn) => fn(type, data));
}

export function onPlayerEvent(fn) { listeners.add(fn); return () => listeners.delete(fn); }

audio.addEventListener("timeupdate", () => emit("time", { current: audio.currentTime, duration: audio.duration }));
audio.addEventListener("ended", () => emit("ended", current));
audio.addEventListener("play", () => emit("play", current));
audio.addEventListener("pause", () => emit("pause", current));
audio.addEventListener("error", () => emit("error", current));

export const player = {
  get current() { return current; },
  isPlaying: () => !audio.paused && !audio.ended,

  async play(track) {
    const key = track.track_id || track.url;
    // Toggle pause if same track.
    if (current && current.key === key && !audio.paused) { audio.pause(); return; }
    if (current && current.key === key && audio.paused && audio.src) { await audio.play(); return; }

    if (!track.preview_url) { emit("error", track); throw new Error("No preview available for this track."); }

    emit("loading", track);
    let url = track.preview_url;
    // SoundCloud previews need server-side resolution; Bandcamp plays directly.
    if (url.includes("soundcloud.com")) {
      url = await resolveStream(track.preview_url);
    }

    ensureGraph();
    if (ctx && ctx.state === "suspended") await ctx.resume();

    current = { key, title: track.title, artist: track.artist };
    audio.src = url;
    await audio.play();
    emit("track", { ...current, ...track });
  },

  toggle() { if (audio.paused) audio.play().catch(() => emit("error", current)); else audio.pause(); },
  seek(fraction) { if (audio.duration) audio.currentTime = fraction * audio.duration; },
  setVolume(v) { audio.volume = v; if (gain) gain.gain.value = v; },
  stop() { audio.pause(); audio.removeAttribute("src"); audio.load(); current = null; emit("stop"); },
};
