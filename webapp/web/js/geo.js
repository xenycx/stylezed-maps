// lon/lat ⇄ image pixel, exactly as CONTRACT.md defines it (north up, no rotation).

export function makeProjection(side) {
  const [fx, fy, fw, fh] = side.frame_px;
  const cx = fx + fw / 2, cy = fy + fh / 2;
  const [clon, clat] = side.center;
  const [mLon, mLat] = side.m_per_deg;
  const mpp = side.m_per_px;
  const r6 = (v) => Math.round(v * 1e6) / 1e6;
  return {
    mpp,
    frame: { x: fx, y: fy, w: fw, h: fh },
    size: { w: side.px[0], h: side.px[1] },
    toPx: (lon, lat) => [cx + (lon - clon) * mLon / mpp, cy - (lat - clat) * mLat / mpp],
    toLonLat: (x, y) => [r6(clon + (x - cx) * mpp / mLon), r6(clat - (y - cy) * mpp / mLat)],
    inFrame: (x, y) => x >= fx && x <= fx + fw && y >= fy && y <= fy + fh,
    clampToFrame: (x, y) => [Math.min(fx + fw, Math.max(fx, x)), Math.min(fy + fh, Math.max(fy, y))],
    /** metres between two [lon, lat] */
    dist: (a, b) => Math.hypot((a[0] - b[0]) * mLon, (a[1] - b[1]) * mLat),
  };
}

export function lineLength(proj, coords) {
  let m = 0;
  for (let i = 1; i < coords.length; i += 1) m += proj.dist(coords[i - 1], coords[i]);
  return m;
}

/** Point at distance d (metres) along a lon/lat line. */
export function pointAlong(proj, coords, d) {
  let acc = 0;
  for (let i = 1; i < coords.length; i += 1) {
    const seg = proj.dist(coords[i - 1], coords[i]);
    if (acc + seg >= d && seg > 0) {
      const f = (d - acc) / seg;
      return [coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * f, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * f];
    }
    acc += seg;
  }
  return coords[coords.length - 1];
}

/** Closest point on segment a→b to p (all [x, y]); returns {d, t, x, y}. */
export function nearestOnSegment(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.min(1, Math.max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2)) : 0;
  const x = a[0] + dx * t, y = a[1] + dy * t;
  return { d: Math.hypot(p[0] - x, p[1] - y), t, x, y };
}
