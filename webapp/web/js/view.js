// Pan / zoom of the poster inside the stage. Pure maths + one rAF loop; no rendering of its own.

import { Emitter, clamp, reducedMotion } from './util.js';

const TAU = 0.075; // seconds: smoothing constant for wheel / key zoom and pan

export class View extends Emitter {
  constructor(stage) {
    super();
    this.stage = stage;
    this.x = 0; this.y = 0; this.k = 1;
    this.w = 1; this.h = 1;               // image size in image px
    this.sw = 1; this.sh = 1;             // stage size in CSS px
    this.insets = { top: 12, right: 12, bottom: 12, left: 12 };
    this.goal = null;                     // { x, y, k } eased towards
    this.fly = null;                      // authored flight
    this.raf = 0;
    this.last = 0;
    this.hasImage = false;
    this.measure();
  }

  measure() {
    const r = this.stage.getBoundingClientRect();
    this.left = r.left; this.top = r.top;
    this.sw = Math.max(1, r.width); this.sh = Math.max(1, r.height);
  }

  setImage(w, h) { this.w = w; this.h = h; this.hasImage = true; }

  setInsets(insets) { this.insets = { ...this.insets, ...insets }; }

  get avail() {
    const i = this.insets;
    const w = Math.max(80, this.sw - i.left - i.right), h = Math.max(80, this.sh - i.top - i.bottom);
    return { x: i.left, y: i.top, w, h, cx: i.left + w / 2, cy: i.top + h / 2 };
  }

  get fitK() {
    const a = this.avail;
    return Math.min((a.w - 40) / this.w, (a.h - 40) / this.h);
  }
  get minK() { return Math.min(1, this.fitK * 0.6); }
  get maxK() { return Math.max(3, this.fitK * 1.5); }

  toScreen(ix, iy) { return [ix * this.k + this.x, iy * this.k + this.y]; }
  toImage(sx, sy) { return [(sx - this.x) / this.k, (sy - this.y) / this.k]; }
  /** Stage-local coordinates of a pointer event. */
  local(e) { return [e.clientX - this.left, e.clientY - this.top]; }

  /** Keep the paper on the desk: it can't be dragged further than a margin past the free area. */
  constrain(x, y, k) {
    const a = this.avail, m = 56;
    const lim = (pos, size, a0, aSize) => {
      const lo = Math.min(a0 + m, a0 + aSize - size - m), hi = Math.max(a0 + m, a0 + aSize - size - m);
      // when the paper is smaller than the free area, let it sit anywhere inside it
      return size <= aSize - 2 * m ? clamp(pos, a0, a0 + aSize - size) : clamp(pos, lo, hi);
    };
    return [lim(x, this.w * k, a.x, a.w), lim(y, this.h * k, a.y, a.h)];
  }

  set(x, y, k) {
    k = clamp(k, this.minK, this.maxK);
    [x, y] = this.constrain(x, y, k);
    if (x === this.x && y === this.y && k === this.k) return;
    this.x = x; this.y = y; this.k = k;
    this.emit('change');
  }

  stop() { this.goal = null; this.fly = null; }

  /** Direct manipulation (drag, pinch): no easing. */
  panBy(dx, dy) { this.stop(); this.set(this.x + dx, this.y + dy, this.k); }

  /** Eased pan (arrow keys). */
  nudge(dx, dy) {
    const g = this.goal || { x: this.x, y: this.y, k: this.k };
    const [x, y] = this.constrain(g.x + dx, g.y + dy, g.k);
    this.easeTo(x, y, g.k);
  }

  zoomBy(factor, sx = this.avail.cx, sy = this.avail.cy, smooth = true) {
    const fromK = this.goal ? this.goal.k : this.k;
    this.zoomTo(fromK * factor, sx, sy, smooth);
  }

  zoomTo(k, sx = this.avail.cx, sy = this.avail.cy, smooth = true) {
    k = clamp(k, this.minK, this.maxK);
    const [ix, iy] = this.toImage(sx, sy);
    const [x, y] = this.constrain(sx - ix * k, sy - iy * k, k);
    if (smooth) this.easeTo(x, y, k); else { this.stop(); this.set(x, y, k); }
  }

  easeTo(x, y, k) {
    this.fly = null;
    if (reducedMotion()) { this.goal = null; this.set(x, y, k); return; }
    this.goal = { x, y, k };
    this.run();
  }

  fitState() {
    const a = this.avail, k = this.fitK;
    return { x: a.cx - this.w * k / 2, y: a.cy - this.h * k / 2, k };
  }

  fit(animate = true) {
    const f = this.fitState();
    if (animate) this.flyToState(f, 520); else { this.stop(); this.set(f.x, f.y, f.k); }
  }

  /** Authored flight: centre an image point, optionally at a zoom. */
  flyTo(ix, iy, k = this.k, opts = {}) {
    k = clamp(k, this.minK, this.maxK);
    const a = this.avail;
    const [x, y] = this.constrain(a.cx - ix * k, a.cy - iy * k, k);
    this.flyToState({ x, y, k }, opts.dur, opts.onArrive);
  }

  flyToState(to, dur, onArrive) {
    if (reducedMotion()) { this.stop(); this.set(to.x, to.y, to.k); onArrive?.(); return; }
    const a = this.avail;
    // work with the image point under the centre of the free area, and log-zoom
    const from = { cx: (a.cx - this.x) / this.k, cy: (a.cy - this.y) / this.k, k: this.k };
    const dest = { cx: (a.cx - to.x) / to.k, cy: (a.cy - to.y) / to.k, k: to.k };
    const travel = Math.hypot(dest.cx - from.cx, dest.cy - from.cy) * Math.min(from.k, dest.k);
    const far = clamp(travel / Math.hypot(a.w, a.h), 0, 1.6);
    this.goal = null;
    this.fly = {
      from, dest, onArrive, t0: performance.now(),
      dur: dur ?? 520 + 380 * Math.min(1, far + Math.abs(Math.log(dest.k / from.k)) * 0.5),
      dip: clamp((far - 0.35) * 0.32, 0, 0.3), // long hops lift off the paper a little
    };
    this.run();
  }

  run() {
    if (this.raf) return;
    this.last = performance.now();
    const tick = (now) => {
      this.raf = 0;
      const dt = Math.min(0.05, (now - this.last) / 1000);
      this.last = now;
      let more = false;
      if (this.fly) {
        const f = this.fly, a = this.avail;
        const p = clamp((now - f.t0) / f.dur, 0, 1);
        const e = 1 - (1 - p) ** 4; // quartic ease-out
        const k = Math.exp(Math.log(f.from.k) + (Math.log(f.dest.k) - Math.log(f.from.k)) * e) * (1 - f.dip * Math.sin(Math.PI * p));
        const cx = f.from.cx + (f.dest.cx - f.from.cx) * e, cy = f.from.cy + (f.dest.cy - f.from.cy) * e;
        this.set(a.cx - cx * k, a.cy - cy * k, k);
        if (p < 1) more = true; else { this.fly = null; f.onArrive?.(); }
      } else if (this.goal) {
        const g = this.goal, f = 1 - Math.exp(-dt / TAU);
        const k = this.k + (g.k - this.k) * f;
        const near = Math.abs(g.k - k) < g.k * 0.0008 && Math.abs(g.x - this.x) < 0.4 && Math.abs(g.y - this.y) < 0.4;
        if (near) { this.goal = null; this.set(g.x, g.y, g.k); }
        else { this.set(this.x + (g.x - this.x) * f, this.y + (g.y - this.y) * f, k); more = true; }
      }
      if (more) this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  /** Stage resized or insets changed: keep the same image point in the middle. */
  resize(keepFit) {
    const a0 = this.avail;
    const c = this.toImage(a0.cx, a0.cy);
    const wasFit = keepFit || Math.abs(this.k - this.fitK) < 1e-3;
    this.measure();
    if (!this.hasImage) return;
    this.stop();
    if (wasFit) { const f = this.fitState(); this.x = NaN; this.set(f.x, f.y, f.k); return; }
    const a = this.avail, k = clamp(this.k, this.minK, this.maxK);
    this.x = NaN;
    this.set(a.cx - c[0] * k, a.cy - c[1] * k, k);
  }
}
