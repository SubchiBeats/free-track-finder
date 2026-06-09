// Camelot wheel data + harmonic-compatibility logic.
// Mirrors freetracks.utils.keys so the wheel works instantly without a round-trip.

// Camelot -> canonical standard key label (for the select + display).
export const CAMELOT_TO_STANDARD = {
  "1A": "Abm", "2A": "Ebm", "3A": "Bbm", "4A": "Fm", "5A": "Cm", "6A": "Gm",
  "7A": "Dm", "8A": "Am", "9A": "Em", "10A": "Bm", "11A": "F#m", "12A": "C#m",
  "1B": "B", "2B": "F#", "3B": "Db", "4B": "Ab", "5B": "Eb", "6B": "Bb",
  "7B": "F", "8B": "C", "9B": "G", "10B": "D", "11B": "A", "12B": "E",
};

// All 24 keys in wheel order (1..12), both rings.
export const ALL_CAMELOT = [];
for (let n = 1; n <= 12; n++) { ALL_CAMELOT.push(`${n}A`, `${n}B`); }

// Harmonic neighbours: same key, relative major/minor, ±1 on the wheel.
export function compatible(camelot) {
  if (!camelot) return [];
  const number = parseInt(camelot, 10);
  const letter = camelot.slice(-1);
  const other = letter === "A" ? "B" : "A";
  const prev = number === 1 ? 12 : number - 1;
  const next = number === 12 ? 1 : number + 1;
  return [camelot, `${number}${other}`, `${prev}${letter}`, `${next}${letter}`];
}

export function camelotLabel(camelot) {
  return CAMELOT_TO_STANDARD[camelot] || camelot;
}
