// Approximate BPM estimation from a preview clip, using the Web Audio API.
// Audio bytes are pulled through the backend proxy (same-origin so we can read
// them), decoded offline, low-passed to isolate the kick, then we histogram the
// intervals between energy peaks to find the most likely tempo.
//
// This is a heuristic — it can land on a half/double of the true tempo. Results
// are labelled "~" and clamped to a sane DJ range.

const MIN_BPM = 70;
const MAX_BPM = 190;

export async function estimateBpm(previewUrl) {
  const res = await fetch(`api/audio?url=${encodeURIComponent(previewUrl)}`);
  if (!res.ok) throw new Error("Could not load audio for analysis");
  const arrayBuf = await res.arrayBuffer();

  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) throw new Error("Web Audio not supported");
  const ctx = new AC();
  let buffer;
  try {
    buffer = await ctx.decodeAudioData(arrayBuf.slice(0));
  } finally {
    ctx.close();
  }

  // Render a low-passed copy offline to emphasise kicks/bass.
  const offline = new OfflineAudioContext(1, buffer.length, buffer.sampleRate);
  const src = offline.createBufferSource();
  src.buffer = buffer;
  const lp = offline.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 150;
  const hp = offline.createBiquadFilter();
  hp.type = "highpass";
  hp.frequency.value = 30;
  src.connect(lp); lp.connect(hp); hp.connect(offline.destination);
  src.start(0);
  const rendered = await offline.startRendering();

  return tempoFromPeaks(rendered.getChannelData(0), rendered.sampleRate);
}

function tempoFromPeaks(data, sampleRate) {
  // Find peaks above a dynamic threshold, spaced at least 120ms apart.
  const threshold = 0.9 * maxAbs(data);
  const minGap = Math.floor(sampleRate * 0.12);
  const peaks = [];
  for (let i = 0; i < data.length; i++) {
    if (Math.abs(data[i]) >= threshold) {
      peaks.push(i);
      i += minGap;
    }
  }
  if (peaks.length < 4) throw new Error("Not enough rhythmic detail to estimate");

  // Histogram candidate BPMs from inter-peak intervals.
  const counts = {};
  for (let i = 0; i < peaks.length; i++) {
    for (let j = i + 1; j < Math.min(i + 10, peaks.length); j++) {
      const seconds = (peaks[j] - peaks[i]) / sampleRate;
      let bpm = 60 / seconds;
      while (bpm < MIN_BPM) bpm *= 2;
      while (bpm > MAX_BPM) bpm /= 2;
      const rounded = Math.round(bpm);
      counts[rounded] = (counts[rounded] || 0) + 1;
    }
  }

  let best = null, bestCount = -1;
  for (const [bpm, count] of Object.entries(counts)) {
    if (count > bestCount) { bestCount = count; best = Number(bpm); }
  }
  if (best === null) throw new Error("Could not estimate tempo");
  return best;
}

function maxAbs(data) {
  let m = 0;
  for (let i = 0; i < data.length; i++) { const v = Math.abs(data[i]); if (v > m) m = v; }
  return m;
}
