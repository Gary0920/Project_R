import { useEffect, useRef } from "react";

type DotState = {
  opacity: number;
  rotate?: number;
  sx?: number;
  sy?: number;
  x: number;
  y: number;
};

const TIMING = {
  cycleMs: 13200,
  speed: 1,
};

const ACTION_LOOPS = {
  wave: 3,
  rotateCycles: 3,
  corePulse: 2,
};

const PHASE_RATIO = {
  wave: 0.29,
  mergeToCore: 0.105,
  corePulse: 0.145,
  splitToTriangle: 0.11,
  rotate: 0.29,
  returnToRow: 0.06,
};

const row = [
  { x: 18, y: 29 },
  { x: 32, y: 29 },
  { x: 46, y: 29 },
];

const center = { x: 32, y: 27 };
const orbitRadius = 17;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const easeInCubic = (t: number) => t * t * t;
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);
const easeInOutCubic = (t: number) => (
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
);
const easeOutBack = (t: number) => {
  const c1 = 1.55;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};

const phaseBounds = (() => {
  let start = 0;
  return Object.entries(PHASE_RATIO).map(([name, ratio]) => {
    const item = { name, start, end: start + ratio };
    start += ratio;
    return item;
  });
})();

function getPhase(progress: number) {
  const phase = phaseBounds.find((item) => progress >= item.start && progress < item.end)
    ?? phaseBounds[phaseBounds.length - 1];
  return {
    name: phase.name,
    t: clamp01((progress - phase.start) / (phase.end - phase.start)),
  };
}

function trianglePoint(index: number, turn = 0) {
  const angle = -Math.PI / 2 + index * (Math.PI * 2 / 3) + turn;
  return {
    x: center.x + Math.cos(angle) * orbitRadius,
    y: center.y + Math.sin(angle) * orbitRadius,
  };
}

function pulseJump(t: number, index: number) {
  const start = index * 0.15;
  const width = 0.34;
  const p = (t - start) / width;
  if (p < 0 || p > 1) return 0;
  return Math.sin(Math.PI * p);
}

function waveState(t: number, index: number): DotState {
  const base = row[index];
  const localT = t >= 1 ? 1 : (t * ACTION_LOOPS.wave) % 1;
  const jump = pulseJump(localT, index);
  const settle = Math.max(0, pulseJump(localT - 0.22, index));
  return {
    x: base.x,
    y: base.y - jump * 13,
    sx: 1 + settle * 0.14,
    sy: 1 - settle * 0.18,
    opacity: 1,
  };
}

function mergeToCoreState(t: number, index: number): DotState {
  const from = waveState(1, index);
  const eased = easeInOutCubic(t);
  const squash = Math.sin(Math.PI * t);
  const side = index - 1;
  return {
    x: lerp(from.x, center.x + side * 1.4, eased),
    y: lerp(from.y, center.y, eased),
    sx: lerp(1 + squash * 0.35, 0.12, easeInCubic(t)),
    sy: lerp(1 - squash * 0.22, 0.12, easeInCubic(t)),
    opacity: 1 - easeOutCubic(t),
  };
}

function hiddenDotState(): DotState {
  return { x: center.x, y: center.y, sx: 0.08, sy: 0.08, opacity: 0 };
}

function splitToTriangleState(t: number, index: number): DotState {
  const target = trianglePoint(index);
  const eased = easeOutCubic(t);
  const pop = easeOutBack(t);
  const angle = -Math.PI / 2 + index * (Math.PI * 2 / 3);
  const coreEdge = 5.8;
  const seedX = center.x + Math.cos(angle) * coreEdge * Math.min(1, t * 1.7);
  const seedY = center.y + Math.sin(angle) * coreEdge * Math.min(1, t * 1.7);
  const scale = lerp(0.18, 1, pop);
  return {
    x: lerp(seedX, target.x, eased),
    y: lerp(seedY, target.y, eased),
    sx: scale,
    sy: scale,
    opacity: easeOutCubic(t),
  };
}

function rotateState(t: number, index: number): DotState {
  const cycles = ACTION_LOOPS.rotateCycles;
  const raw = t >= 1 ? 1 : t * cycles;
  const cycleIndex = Math.min(cycles - 1, Math.floor(raw));
  const localT = raw >= cycles ? 1 : raw - cycleIndex;
  const cycleEase = easeInOutCubic(localT);
  const turn = (cycleIndex + cycleEase) * Math.PI * 2;
  const pos = trianglePoint(index, turn);
  return {
    x: pos.x,
    y: pos.y,
    sx: 1,
    sy: 1,
    rotate: (turn * 180 / Math.PI) + 120 * index,
    opacity: 1,
  };
}

function returnToRowState(t: number, index: number): DotState {
  const from = rotateState(1, index);
  const target = row[index];
  const eased = easeInOutCubic(t);
  const scale = 1 - Math.sin(Math.PI * t) * 0.12;
  return {
    x: lerp(from.x, target.x, eased),
    y: lerp(from.y, target.y, eased),
    sx: scale,
    sy: scale,
    opacity: 1,
  };
}

function stateFor(progress: number, index: number): DotState {
  const phase = getPhase(progress);
  if (phase.name === "wave") return waveState(phase.t, index);
  if (phase.name === "mergeToCore") return mergeToCoreState(phase.t, index);
  if (phase.name === "corePulse") return hiddenDotState();
  if (phase.name === "splitToTriangle") return splitToTriangleState(phase.t, index);
  if (phase.name === "rotate") return rotateState(phase.t, index);
  return returnToRowState(phase.t, index);
}

function coreStateFor(progress: number): DotState {
  const phase = getPhase(progress);
  if (phase.name === "mergeToCore") {
    const scale = lerp(0.9, 1.75, easeOutBack(phase.t));
    return {
      x: center.x,
      y: center.y,
      sx: scale,
      sy: scale,
      opacity: easeOutCubic(phase.t),
    };
  }
  if (phase.name === "corePulse") {
    const localT = phase.t >= 1 ? 1 : (phase.t * ACTION_LOOPS.corePulse) % 1;
    const breath = 1 + Math.sin(localT * Math.PI * 2) * 0.22;
    return {
      x: center.x,
      y: center.y,
      sx: 1.58 * breath,
      sy: 1.58 * breath,
      opacity: 1,
    };
  }
  if (phase.name === "splitToTriangle") {
    return {
      x: center.x,
      y: center.y,
      sx: lerp(1.58, 0.34, easeOutCubic(phase.t)),
      sy: lerp(1.58, 0.34, easeOutCubic(phase.t)),
      opacity: 1 - easeInCubic(phase.t),
    };
  }
  return hiddenDotState();
}

function renderDot(dot: SVGEllipseElement | null, state: DotState) {
  if (!dot) return;
  const rotate = state.rotate ?? 0;
  const sx = state.sx ?? 1;
  const sy = state.sy ?? 1;
  dot.setAttribute("opacity", state.opacity.toFixed(3));
  dot.setAttribute(
    "transform",
    [
      `translate(${state.x.toFixed(3)} ${state.y.toFixed(3)})`,
      `rotate(${rotate.toFixed(3)})`,
      `scale(${sx.toFixed(3)} ${sy.toFixed(3)})`,
    ].join(" "),
  );
}

export function ChatReplyLoadingMotion() {
  const coreRef = useRef<SVGEllipseElement | null>(null);
  const dotRefs = useRef<Array<SVGEllipseElement | null>>([]);

  useEffect(() => {
    let frame = 0;
    const startTime = performance.now();
    const tick = (now: number) => {
      const elapsed = (now - startTime) * TIMING.speed;
      const progress = (elapsed % TIMING.cycleMs) / TIMING.cycleMs;
      renderDot(coreRef.current, coreStateFor(progress));
      dotRefs.current.forEach((dot, index) => renderDot(dot, stateFor(progress, index)));
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <svg aria-hidden="true" className="chat-loading-motion" height="56" viewBox="0 0 64 56" width="64">
      <ellipse className="chat-loading-motion-dot is-core" cx="0" cy="0" ref={coreRef} rx="5" ry="5" />
      {[0, 1, 2].map((index) => (
        <ellipse
          className={`chat-loading-motion-dot is-dot-${index + 1}`}
          cx="0"
          cy="0"
          key={index}
          ref={(node) => { dotRefs.current[index] = node; }}
          rx="5"
          ry="5"
        />
      ))}
    </svg>
  );
}
