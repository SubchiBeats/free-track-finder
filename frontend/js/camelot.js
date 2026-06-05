// Interactive Camelot wheel — rendered as SVG, keyboard-operable.
// Clicking a key calls onSelect(camelot, compatibleList); clicking the centre clears.

import { ALL_CAMELOT, compatible, camelotLabel } from "./keys.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const SIZE = 320;
const CX = SIZE / 2;
const CY = SIZE / 2;
const R_OUTER = 150; // B ring (major)
const R_MID = 105;   // boundary
const R_INNER = 58;  // A ring (minor) inner edge

// Colour ramp around the wheel (12 hues) — purely decorative, dimmed when filtered.
function hue(n) { return ((n - 1) / 12) * 360; }

function polar(angleDeg, r) {
  const a = ((angleDeg - 90) * Math.PI) / 180;
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)];
}

function segmentPath(n, rInner, rOuter) {
  // Each hour spans 30°, centred so number 12 is at top.
  const start = (n - 1) * 30 - 15;
  const end = start + 30;
  const [x1, y1] = polar(start, rInner);
  const [x2, y2] = polar(end, rInner);
  const [x3, y3] = polar(end, rOuter);
  const [x4, y4] = polar(start, rOuter);
  return `M${x1} ${y1} A${rInner} ${rInner} 0 0 1 ${x2} ${y2} L${x3} ${y3} A${rOuter} ${rOuter} 0 0 0 ${x4} ${y4} Z`;
}

export function buildWheel(container, onSelect) {
  container.innerHTML = "";
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${SIZE} ${SIZE}`);
  svg.setAttribute("class", "wheel");
  svg.setAttribute("role", "group");
  svg.setAttribute("aria-label", "Camelot wheel — choose a key");

  const segs = {};

  function makeSeg(camelot, rInner, rOuter) {
    const n = parseInt(camelot, 10);
    const letter = camelot.slice(-1);
    const g = document.createElementNS(SVG_NS, "g");

    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", segmentPath(n, rInner, rOuter));
    const light = letter === "B" ? 62 : 50;
    path.setAttribute("fill", `hsl(${hue(n)} 55% ${light}%)`);
    path.setAttribute("class", "wheel-seg");
    path.setAttribute("tabindex", "0");
    path.setAttribute("role", "button");
    path.setAttribute("aria-label", `${camelot} (${camelotLabel(camelot)})`);

    const labelR = (rInner + rOuter) / 2;
    const [lx, ly] = polar((n - 1) * 30, labelR);
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", lx);
    text.setAttribute("y", ly + 3);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("class", "wheel-label");
    text.textContent = camelot;

    const activate = () => onSelect(camelot, compatible(camelot));
    path.addEventListener("click", activate);
    path.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
    });

    g.appendChild(path);
    g.appendChild(text);
    segs[camelot] = path;
    return g;
  }

  ALL_CAMELOT.forEach((camelot) => {
    const letter = camelot.slice(-1);
    const node = letter === "B"
      ? makeSeg(camelot, R_MID, R_OUTER)
      : makeSeg(camelot, R_INNER, R_MID);
    svg.appendChild(node);
  });

  // Centre "clear" button.
  const centre = document.createElementNS(SVG_NS, "circle");
  centre.setAttribute("cx", CX);
  centre.setAttribute("cy", CY);
  centre.setAttribute("r", R_INNER - 4);
  centre.setAttribute("fill", "#151823");
  centre.setAttribute("stroke", "#3a4055");
  centre.setAttribute("class", "wheel-seg");
  centre.setAttribute("tabindex", "0");
  centre.setAttribute("role", "button");
  centre.setAttribute("aria-label", "Clear key selection");
  const clear = () => onSelect(null, []);
  centre.addEventListener("click", clear);
  centre.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); clear(); } });
  svg.appendChild(centre);

  const centreLabel = document.createElementNS(SVG_NS, "text");
  centreLabel.setAttribute("x", CX);
  centreLabel.setAttribute("y", CY + 3);
  centreLabel.setAttribute("text-anchor", "middle");
  centreLabel.setAttribute("class", "wheel-label");
  centreLabel.setAttribute("fill", "#a7b0c4");
  centreLabel.textContent = "ANY";
  svg.appendChild(centreLabel);

  container.appendChild(svg);

  // Returns a function to visually reflect the current selection.
  return function highlight(selected) {
    const compat = selected ? compatible(selected) : [];
    Object.entries(segs).forEach(([camelot, path]) => {
      path.classList.toggle("selected", camelot === selected);
      path.classList.toggle("compatible", camelot !== selected && compat.includes(camelot));
      path.classList.toggle("dim", selected && !compat.includes(camelot));
    });
  };
}
