// drawings.mjs - original illustrative SVG renderings of welding-torch parts.
// Shapes are schematic interpretations of catalogue component silhouettes,
// not exact product / CAD geometry and not guaranteed compatible parts.
// Every SVG: viewBox 0 0 600 340, transparent background, no text, no scripts,
// no external resources, no bitmaps. Tuned for a graphite #202620 page.

/* ------------------------------------------------------------------ */
/* number / point formatting                                          */
/* ------------------------------------------------------------------ */
const f = (n) => {
  const v = Math.round(n * 100) / 100;
  return Object.is(v, -0) ? '0' : String(v);
};
const pt = (p) => `${f(p[0])},${f(p[1])}`;

/* ------------------------------------------------------------------ */
/* materials                                                          */
/* ------------------------------------------------------------------ */
const DARK_EDGE = 'rgba(0,0,0,.42)';
const LIGHT_EDGE = 'rgba(190,200,190,.3)';
const M = {
  copper: { n: 'cu', hl: '#f2c9a8', lt: '#d99168', base: '#b96d3e', dk: '#7c4323', xd: '#3f2212', edge: DARK_EDGE },
  brass: { n: 'br', hl: '#f3e6bd', lt: '#d8c185', base: '#bca166', dk: '#83703c', xd: '#463b1d', edge: DARK_EDGE },
  graphite: { n: 'gr', hl: '#8b938d', lt: '#4f5752', base: '#2d322f', dk: '#1a1e1b', xd: '#0c0e0d', edge: LIGHT_EDGE },
  rubber: { n: 'rb', hl: '#767b80', lt: '#3f4347', base: '#26292c', dk: '#151719', xd: '#090a0b', edge: LIGHT_EDGE },
  ceramic: { n: 'ce', hl: '#f4e2ea', lt: '#e2b8cb', base: '#cf9bb4', dk: '#a87690', xd: '#6c4659', edge: DARK_EDGE, matte: true },
  insul: { n: 'in', hl: '#fbfaf6', lt: '#eeece4', base: '#d9d6cb', dk: '#aca89b', xd: '#6f6b62', edge: DARK_EDGE, matte: true },
  steel: { n: 'st', hl: '#eef1f2', lt: '#c3c9cc', base: '#959ca0', dk: '#5e6569', xd: '#2f3437', edge: DARK_EDGE },
  trigger: { n: 'tr', hl: '#f1e2a6', lt: '#d9c26f', base: '#bfa04c', dk: '#856f30', xd: '#4a3d19', edge: DARK_EDGE },
  teal: { n: 'te', hl: '#b6dcdc', lt: '#69a7ab', base: '#3d7f86', dk: '#245159', xd: '#122d31', edge: DARK_EDGE },
  red: { n: 'rd', hl: '#efa197', lt: '#c9554a', base: '#a63a32', dk: '#6d2420', xd: '#3a1311', edge: DARK_EDGE },
  blue: { n: 'bl', hl: '#a9c6ee', lt: '#4f7fc4', base: '#30609f', dk: '#1d3d68', xd: '#0f2038', edge: DARK_EDGE },
  navy: { n: 'nv', hl: '#6a7598', lt: '#3a4360', base: '#252b42', dk: '#161a2a', xd: '#0a0c15', edge: LIGHT_EDGE },
  grey: { n: 'gy', hl: '#e2e5e2', lt: '#b2b7b3', base: '#8d938f', dk: '#5d625f', xd: '#323533', edge: DARK_EDGE },
  green: { n: 'gn', hl: '#bfe0b5', lt: '#6fa865', base: '#4c8546', dk: '#2e5a2a', xd: '#173016', edge: DARK_EDGE },
  brown: { n: 'bn', hl: '#e3b49b', lt: '#a8664a', base: '#86492f', dk: '#57301f', xd: '#2c180f', edge: DARK_EDGE },
  white: { n: 'wh', hl: '#ffffff', lt: '#ecebe6', base: '#cfcdc5', dk: '#9a978e', xd: '#5d5b55', edge: DARK_EDGE },
};

/* ------------------------------------------------------------------ */
/* defs context (ids are prefixed per part so inline SVGs never clash) */
/* ------------------------------------------------------------------ */
function lin(id, [x1, y1, x2, y2], stops, extra = '') {
  const st = stops
    .map(([o, col, a]) => `<stop offset="${o}" stop-color="${col}"${a == null ? '' : ` stop-opacity="${a}"`}/>`)
    .join('');
  return `<linearGradient id="${id}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"${extra}>${st}</linearGradient>`;
}

class Ctx {
  constructor(pid) {
    this.pid = pid;
    this.defs = [];
    this.ids = new Set();
    this.n = 0;
  }
  uid(tag) {
    this.n += 1;
    return `${this.pid}-${tag}${this.n}`;
  }
  once(key, build) {
    const id = `${this.pid}-${key}`;
    if (!this.ids.has(id)) {
      this.ids.add(id);
      this.defs.push(build(id));
    }
    return `url(#${id})`;
  }
  body(m) {
    const stops = m.matte
      ? [[0, m.dk], [0.12, m.base], [0.3, m.lt], [0.42, m.hl], [0.6, m.lt], [0.84, m.base], [1, m.dk]]
      : [[0, m.dk], [0.1, m.base], [0.24, m.hl], [0.37, m.lt], [0.6, m.base], [0.84, m.dk], [1, m.xd]];
    return this.once(`b-${m.n}`, (id) => lin(id, [0, 0, 0, 1], stops));
  }
  face(m) {
    return this.once(`f-${m.n}`, (id) => lin(id, [0, 0, 1, 1], [[0, m.lt], [0.55, m.base], [1, m.dk]]));
  }
  wall(m) {
    return this.once(`w-${m.n}`, (id) => lin(id, [0, 0, 0, 1], [[0, '#050505'], [0.5, m.xd], [1, m.dk]]));
  }
  cham(m) {
    return this.once(`c-${m.n}`, (id) => lin(id, [0, 0, 0, 1], [[0, m.xd], [0.5, m.dk], [1, m.lt]]));
  }
  ridge(m) {
    return this.once(`r-${m.n}`, (id) => lin(id, [0, 0, 0, 1], [[0, m.hl, 0.85], [0.5, m.lt, 0.35], [1, m.lt, 0]]));
  }
  deep() {
    return this.once('deep', (id) => lin(id, [0, 0, 1, 0], [[0, '#0d0e0d'], [1, '#030303']]));
  }
  shade() {
    return this.once(
      'shadow',
      (id) =>
        `<radialGradient id="${id}"><stop offset="0" stop-color="#000" stop-opacity=".5"/><stop offset=".55" stop-color="#000" stop-opacity=".2"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>`,
    );
  }
  mouth() {
    return this.once('mouth', (id) => lin(id, [0, 0, 1, 0], [[0, '#000', 0.75], [0.65, '#000', 0.3], [1, '#000', 0]]));
  }
}

function svg(c, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 340" aria-hidden="true" focusable="false"><defs>${c.defs.join('')}</defs>${body}</svg>`;
}

function shadow(c, cx, cy, rx, ry) {
  return `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="${c.shade()}"/>`;
}

/* ------------------------------------------------------------------ */
/* lathe engine: axis along local +x, viewer sees the +x end faces.    */
/* k = ellipse aspect (end-face width / height).                       */
/* ------------------------------------------------------------------ */
function cylPath(x0, r0, x1, r1, k) {
  return `M${f(x0)},${f(-r0)} L${f(x1)},${f(-r1)} A${f(k * r1)},${f(r1)} 0 0 1 ${f(x1)},${f(r1)} L${f(x0)},${f(r0)} A${f(k * r0)},${f(r0)} 0 0 1 ${f(x0)},${f(-r0)} Z`;
}

// visible (near-side) half of a cross-section ring - bulges toward -x
function nearArc(x, r, k) {
  const c = 1.3333 * k * r;
  return `M${f(x)},${f(-r)} C${f(x - c)},${f(-r)} ${f(x - c)},${f(r)} ${f(x)},${f(r)}`;
}

function threadPath(x0, x1, r, p, dep, k) {
  const rr = r - dep;
  const top = [[x0, -rr]];
  for (let x = x0; x < x1 - 0.01; x += p) {
    if (x + p / 2 < x1) top.push([x + p / 2, -r]);
    top.push([Math.min(x + p, x1), -rr]);
  }
  let d = `M${pt(top[0])}` + top.slice(1).map((q) => ` L${pt(q)}`).join('');
  d += ` A${f(k * rr)},${f(rr)} 0 0 1 ${f(x1)},${f(rr)}`;
  const bot = [];
  for (let xp = x0; xp < x1 - 0.01; xp += p) {
    if (xp > x0 + 0.01) bot.push([xp, r]);
    if (xp + p / 2 < x1) bot.push([xp + p / 2, rr]);
  }
  d += bot.reverse().map((q) => ` L${pt(q)}`).join('');
  d += ` L${f(x0)},${f(rr)} A${f(k * rr)},${f(rr)} 0 0 1 ${f(x0)},${f(-rr)} Z`;
  return d;
}

function threadLines(c, x0, x1, r, p, dep, k, m) {
  const rr = r - dep;
  const cc = 1.3333 * k * r;
  let g = '';
  let h = '';
  for (let x = x0; x + p / 2 <= x1 + 0.01; x += p) {
    g += `M${f(x)},${f(-rr)} C${f(x - cc)},${f(-rr)} ${f(x + p / 2 - cc)},${f(rr)} ${f(x + p / 2)},${f(rr)} `;
    if (x + p <= x1 + 0.01) {
      h += `M${f(x + p / 2)},${f(-r)} C${f(x + p / 2 - cc)},${f(-r)} ${f(x + p - cc)},${f(r)} ${f(x + p)},${f(r)} `;
    }
  }
  let s = `<path d="${g}" fill="none" stroke="${m.xd}" stroke-opacity=".7" stroke-width="${f(p * 0.3)}"/>`;
  if (h) s += `<path d="${h}" fill="none" stroke="${c.ridge(m)}" stroke-width="${f(p * 0.22)}"/>`;
  return s;
}

function lathe(c, segs, k) {
  let s = '';
  segs.forEach((g, i) => {
    const m = g.m;
    const r0 = g.r0;
    const r1 = g.r1 ?? g.r0;
    const edge = g.edge ?? m.edge;
    const dep = g.depth ?? (g.thread ? g.thread * 0.3 : 0);
    const d = g.thread ? threadPath(g.x0, g.x1, r0, g.thread, dep, k) : cylPath(g.x0, r0, g.x1, r1, k);
    s += `<path d="${d}" fill="${c.body(m)}" stroke="${edge}" stroke-width=".8" stroke-linejoin="round"/>`;
    if (g.thread) s += threadLines(c, g.x0, g.x1, r0, g.thread, dep, k, m);
    if (g.deco) s += g.deco(k);
    const nx = segs[i + 1];
    if (!nx || nx.r0 < r1 - 0.3 || nx.x0 > g.x1 + 0.1) {
      s += `<ellipse cx="${f(g.x1)}" cy="0" rx="${f(k * r1)}" ry="${f(r1)}" fill="${c.face(m)}" stroke="${edge}" stroke-width=".7"/>`;
      if (g.faceDeco) s += g.faceDeco(k);
    }
  });
  return s;
}

// open bore in an end face: inner wall crescent + dark depth (+ optional thread rings / chamfer)
function bore(c, x, rb, k, m, o = {}) {
  let s = '';
  if (o.ch) {
    s += `<ellipse cx="${f(x)}" cy="0" rx="${f(k * (rb + o.ch))}" ry="${f(rb + o.ch)}" fill="${c.cham(o.chm || m)}"/>`;
  }
  const id = c.uid('cl');
  c.defs.push(`<clipPath id="${id}"><ellipse cx="${f(x)}" cy="0" rx="${f(k * rb)}" ry="${f(rb)}"/></clipPath>`);
  const sh = k * rb * (o.depth ?? 1.25);
  const rx = f(k * rb);
  const ry = f(rb);
  s += `<g clip-path="url(#${id})"><ellipse cx="${f(x)}" cy="0" rx="${rx}" ry="${ry}" fill="${c.wall(m)}"/>`;
  const nT = o.threads || 0;
  for (let i = 1; i <= nT; i++) {
    const xx = x - (sh * i) / (nT + 1.2);
    s += `<ellipse cx="${f(xx)}" cy="0" rx="${rx}" ry="${ry}" fill="none" stroke="#000" stroke-opacity=".55" stroke-width="1.1"/>`;
    s += `<ellipse cx="${f(xx + 1.2)}" cy="0" rx="${rx}" ry="${ry}" fill="none" stroke="${m.lt}" stroke-opacity=".22" stroke-width=".8"/>`;
  }
  s += `<ellipse cx="${f(x - sh)}" cy="0" rx="${rx}" ry="${ry}" fill="${c.deep()}"/></g>`;
  s += `<ellipse cx="${f(x)}" cy="0" rx="${rx}" ry="${ry}" fill="none" stroke="rgba(0,0,0,.5)" stroke-width=".9"/>`;
  return s;
}

// radial port on a cylinder surface; phi = angle from the front toward the top
function hole(xc, r, phiDeg, w, h, k, m) {
  const p = (phiDeg * Math.PI) / 180;
  const cx = xc - k * r * Math.cos(p);
  const cy = -r * Math.sin(p);
  const ry = h * Math.cos(p);
  return (
    `<ellipse cx="${f(cx)}" cy="${f(cy)}" rx="${f(w)}" ry="${f(ry)}" fill="${m.dk}" stroke="${m.xd}" stroke-width=".8"/>` +
    `<ellipse cx="${f(cx)}" cy="${f(cy - ry * 0.2)}" rx="${f(w * 0.84)}" ry="${f(ry * 0.76)}" fill="#090807"/>`
  );
}

function ribs(xs, r, k, m, w = 1.4) {
  let a = '';
  let b = '';
  xs.forEach((x) => {
    a += nearArc(x, r, k) + ' ';
    b += nearArc(x + w * 1.2, r, k) + ' ';
  });
  return (
    `<path d="${a}" fill="none" stroke="${m.xd}" stroke-opacity=".6" stroke-width="${w}"/>` +
    `<path d="${b}" fill="none" stroke="${m.hl}" stroke-opacity=".22" stroke-width="${f(w * 0.8)}"/>`
  );
}

function knurl(x0, x1, r, k, m, n = 9) {
  let a = '';
  let b = '';
  for (let i = 0; i < n; i++) {
    const ph = ((-70 + (140 * i) / (n - 1)) * Math.PI) / 180;
    const y = -r * Math.sin(ph);
    const xs = -k * r * Math.cos(ph);
    a += `M${f(x0 + xs + 1)},${f(y)} L${f(x1 + xs - 1)},${f(y)} `;
    b += `M${f(x0 + xs + 1)},${f(y - 1.1)} L${f(x1 + xs - 1)},${f(y - 1.1)} `;
  }
  return (
    `<path d="${a}" fill="none" stroke="${m.xd}" stroke-opacity=".45" stroke-width="1"/>` +
    `<path d="${b}" fill="none" stroke="${m.hl}" stroke-opacity=".3" stroke-width=".8"/>`
  );
}

function hexLines(x0, x1, r, k, m) {
  const xs = -k * r * 0.866;
  return (
    `<path d="M${f(x0 + xs + 1)},${f(-r * 0.5)} L${f(x1 + xs - 1)},${f(-r * 0.5)}" stroke="${m.hl}" stroke-opacity=".55" stroke-width="1.2"/>` +
    `<path d="M${f(x0 + xs + 1)},${f(r * 0.5)} L${f(x1 + xs - 1)},${f(r * 0.5)}" stroke="${m.xd}" stroke-opacity=".55" stroke-width="1.2"/>`
  );
}

// place a lathe group at (x,y) with its axis at angle a (deg); mirrored when pointing left so light stays on top
function place(x, y, a, inner) {
  const flip = Math.cos((a * Math.PI) / 180) < 0;
  return `<g transform="translate(${f(x)} ${f(y)}) rotate(${f(a)})${flip ? ' scale(1 -1)' : ''}">${inner}</g>`;
}

/* ------------------------------------------------------------------ */
/* curves & stroked tubes                                              */
/* ------------------------------------------------------------------ */
function bez(P, t) {
  const u = 1 - t;
  const a = u * u * u;
  const b = 3 * u * u * t;
  const cc = 3 * u * t * t;
  const d = t * t * t;
  return [a * P[0][0] + b * P[1][0] + cc * P[2][0] + d * P[3][0], a * P[0][1] + b * P[1][1] + cc * P[2][1] + d * P[3][1]];
}
function bezD(P, t) {
  const u = 1 - t;
  const g = (i) =>
    3 * u * u * (P[1][i] - P[0][i]) + 6 * u * t * (P[2][i] - P[1][i]) + 3 * t * t * (P[3][i] - P[2][i]);
  return [g(0), g(1)];
}
function angleAt(P, t) {
  const d = bezD(P, t);
  return (Math.atan2(d[1], d[0]) * 180) / Math.PI;
}
function cubicD(P) {
  return `M${pt(P[0])} C${pt(P[1])} ${pt(P[2])} ${pt(P[3])}`;
}
function polyD(P, t0, t1, n = 48) {
  let d = '';
  for (let i = 0; i <= n; i++) d += (i ? ' L' : 'M') + pt(bez(P, t0 + ((t1 - t0) * i) / n));
  return d;
}

// layered strokes give a lit round tube along any path (light from above)
function tube(d, r, m) {
  const p = (w, col, dy, op = 1) =>
    `<path d="${d}" stroke="${col}" stroke-width="${f(w)}"${op < 1 ? ` stroke-opacity="${op}"` : ''}${dy ? ` transform="translate(0 ${f(dy)})"` : ''}/>`;
  return (
    `<g fill="none" stroke-linecap="butt" stroke-linejoin="round">` +
    p(2 * r, m.xd, 0) +
    p(2 * r - 1.6, m.dk, 0) +
    p(0.3 * r, m.base, 0.58 * r, 0.35) +
    p(1.45 * r, m.base, -0.22 * r) +
    p(0.8 * r, m.lt, -0.38 * r) +
    p(0.26 * r, m.hl, -0.52 * r, 0.75) +
    `</g>`
  );
}

function fadeMask(c, x0, x1) {
  const g = c.uid('fg');
  const id = c.uid('mk');
  c.defs.push(
    `<linearGradient id="${g}" gradientUnits="userSpaceOnUse" x1="${x0}" y1="0" x2="${x1}" y2="0"><stop offset="0" stop-color="#000"/><stop offset="1" stop-color="#fff"/></linearGradient>` +
      `<mask id="${id}" maskUnits="userSpaceOnUse" x="-500" y="-400" width="1200" height="800"><rect x="-500" y="-400" width="1200" height="800" fill="url(#${g})"/></mask>`,
  );
  return `url(#${id})`;
}

// clip = opening ellipse ∪ everything in front of the face plane
function mouthClip(c, x, r, k) {
  const id = c.uid('mc');
  c.defs.push(
    `<clipPath id="${id}"><ellipse cx="${f(x)}" cy="0" rx="${f(k * r)}" ry="${f(r)}"/><rect x="${f(x)}" y="-500" width="900" height="1000"/></clipPath>`,
  );
  return `url(#${id})`;
}

function hose(c, h, k, clip) {
  const body = tube(cubicD(h.P), h.r, h.m);
  const a = angleAt(h.P, 1);
  return (clip ? `<g clip-path="${clip}">${body}</g>` : body) + place(h.P[3][0], h.P[3][1], a, lathe(c, h.cap, k));
}

const openCap = (c, r, m, br = 0.56) => [
  { x0: -1.5, x1: 4, r0: r, m, faceDeco: (k) => bore(c, 4, r * br, k, m, { depth: 1.1 }) },
];
const stripCap = (r, m) => [
  { x0: -1, x1: 2, r0: r, m },
  { x0: 2, x1: 13, r0: r * 0.56, r1: r * 0.5, m: M.copper },
];
const fitCap = (c, r) => {
  const br = M.brass;
  return [
    { x0: -2, x1: 2.2 * r - 4, r0: r * 1.1, m: br, deco: (k) => ribs([r * 0.55, r * 1.15], r * 1.1, k, br, 1.2) },
    { x0: 2.2 * r - 4, x1: 3.4 * r - 4, r0: r * 1.3, m: br, deco: (k) => hexLines(2.2 * r - 4, 3.4 * r - 4, r * 1.3, k, br) },
    { x0: 3.4 * r - 4, x1: 5.1 * r - 4, r0: r * 0.78, m: br, thread: Math.max(2.6, r * 0.3), depth: r * 0.1 },
    {
      x0: 5.1 * r - 4,
      x1: 5.1 * r - 1.5,
      r0: r * 0.78,
      r1: r * 0.66,
      m: br,
      faceDeco: (k) => bore(c, 5.1 * r - 1.5, r * 0.3, k, br, { depth: 1.2 }),
    },
  ];
};

/* ================================================================== */
/* MIG parts                                                          */
/* ================================================================== */

// Contact tip - variant 23: threaded seat, smooth body, tapered nose, narrow axial bore
function migTip() {
  const c = new Ctx('mig-tip');
  const m = M.copper;
  const k = 0.42;
  const segs = [
    { x0: -172, x1: -166, r0: 28, r1: 33, m },
    { x0: -166, x1: -64, r0: 33, m, thread: 8.5, depth: 2.6 },
    { x0: -64, x1: -50, r0: 29.5, m },
    { x0: -50, x1: 70, r0: 40, r1: 38.5, m },
    { x0: 70, x1: 148, r0: 38.5, r1: 25, m },
    {
      x0: 148,
      x1: 156,
      r0: 25,
      r1: 23.5,
      m,
      faceDeco: (kk) => bore(c, 156, 6, kk, m, { ch: 3.5, depth: 1.6 }),
    },
  ];
  return svg(c, shadow(c, 305, 250, 185, 15) + `<g transform="translate(308 166) rotate(-9)">${lathe(c, segs, k)}</g>`);
}

// Gas nozzle - position 24: hollow copper sleeve, tapered front, pale insulating insert at the rear
function migNozzle() {
  const c = new Ctx('mig-nozzle');
  const cu = M.copper;
  const k = 0.36;
  const segs = [
    { x0: -178, x1: -160, r0: 58, m: M.insul },
    { x0: -163, x1: -156, r0: 63, r1: 67, m: cu },
    { x0: -156, x1: 35, r0: 67, r1: 66, m: cu, deco: (kk) => ribs([35], 66, kk, cu, 0.9) },
    { x0: 35, x1: 118, r0: 66, r1: 51, m: cu },
    { x0: 118, x1: 148, r0: 51, r1: 49.5, m: cu },
    {
      x0: 148,
      x1: 154,
      r0: 49.5,
      r1: 47,
      m: cu,
      faceDeco: (kk) => bore(c, 154, 41, kk, cu, { depth: 1.5, ch: 2 }),
    },
  ];
  return svg(c, shadow(c, 305, 266, 190, 18) + `<g transform="translate(312 164) rotate(-8)">${lathe(c, segs, k)}</g>`);
}

// Diffuser / retaining head - position 22: brass body, sealing ring, insulating band, radial gas ports, tip seat
function migDiffuser() {
  const c = new Ctx('mig-diffuser');
  const br = M.brass;
  const k = 0.34;
  const ports = (kk) =>
    hole(18, 31.3, 0, 6.5, 6.5, kk, br) + hole(18, 31.3, 58, 6.5, 6.5, kk, br) + hole(18, 31.3, -58, 6.5, 6.5, kk, br);
  const segs = [
    { x0: -176, x1: -170, r0: 38, r1: 43, m: br },
    { x0: -170, x1: -152, r0: 43, m: br },
    { x0: -152, x1: -143, r0: 45, m: M.rubber },
    { x0: -143, x1: -131, r0: 43, m: br },
    { x0: -131, x1: -92, r0: 46, m: M.teal },
    { x0: -92, x1: -76, r0: 44, m: br },
    { x0: -76, x1: 96, r0: 32, r1: 30.5, m: br, deco: ports },
    { x0: 96, x1: 150, r0: 30.5, r1: 21, m: br },
    {
      x0: 150,
      x1: 158,
      r0: 21,
      r1: 20,
      m: br,
      faceDeco: (kk) => bore(c, 158, 10, kk, br, { threads: 3, depth: 1.5, ch: 2 }),
    },
  ];
  return svg(c, shadow(c, 305, 254, 185, 15) + `<g transform="translate(306 168) rotate(-9)">${lathe(c, segs, k)}</g>`);
}

// Wire liner - position 19: close-wound steel spiral, short coated section, brass end fitting, dashed continuation
function migLiner() {
  const c = new Ctx('mig-liner');
  const st = M.steel;
  const br = M.brass;
  const k = 0.34;
  const r = 13;
  const P = [[130, 238], [225, 238], [300, 130], [405, 112]];
  const t1 = 0.7;
  const wire = c.once('wire', (id) =>
    lin(id, [0, 0, 0, 1], [[0, st.dk], [0.18, st.hl], [0.4, st.lt], [0.7, st.base], [1, st.xd]]),
  );

  let s = shadow(c, 290, 282, 210, 12);
  // dashed continuation of the (long) liner
  s += `<g fill="none" stroke="${st.lt}" stroke-opacity=".42" stroke-width="1.2" stroke-dasharray="7 6"><path d="M58,${238 - r} L126,${238 - r}"/><path d="M58,${238 + r} L126,${238 + r}"/></g>`;
  s += `<path d="M44,238 L126,238" fill="none" stroke="${st.lt}" stroke-opacity=".28" stroke-width="1" stroke-dasharray="14 4 2 4"/>`;
  // dark core visible between turns
  s += tube(polyD(P, 0, t1 + 0.01), r - 2.5, M.rubber);

  // coil turns, spaced by arc length
  const N = 400;
  const tab = [{ t: 0, s: 0 }];
  let prev = bez(P, 0);
  let L = 0;
  for (let i = 1; i <= N; i++) {
    const q = bez(P, i / N);
    L += Math.hypot(q[0] - prev[0], q[1] - prev[1]);
    tab.push({ t: i / N, s: L });
    prev = q;
  }
  const tAt = (sv) => {
    for (let i = 1; i < tab.length; i++) {
      if (tab[i].s >= sv) {
        const a = tab[i - 1];
        const b = tab[i];
        return a.t + ((b.t - a.t) * (sv - a.s)) / (b.s - a.s || 1);
      }
    }
    return 1;
  };
  const sEnd = tab[Math.round(N * t1)].s;
  const pitch = 4.7;
  const cc = 1.3333 * k * r;
  let turns = '';
  for (let sv = 2; sv < sEnd - 1; sv += pitch) {
    const t = tAt(sv);
    const p = bez(P, t);
    const d = bezD(P, t);
    const l = Math.hypot(d[0], d[1]) || 1;
    const T = [d[0] / l, d[1] / l];
    const Nn = [-T[1], T[0]];
    const A = [p[0] - Nn[0] * r, p[1] - Nn[1] * r];
    const B = [p[0] + Nn[0] * r + (T[0] * pitch) / 2, p[1] + Nn[1] * r + (T[1] * pitch) / 2];
    turns += `<path d="M${pt(A)} C${pt([A[0] - T[0] * cc, A[1] - T[1] * cc])} ${pt([B[0] - T[0] * cc, B[1] - T[1] * cc])} ${pt(B)}"/>`;
  }
  s += `<g fill="none" stroke="${wire}" stroke-width="${f(pitch * 0.82)}" stroke-linecap="round">${turns}</g>`;

  // coated section
  const ps = bez(P, t1);
  s += place(ps[0], ps[1], angleAt(P, t1), lathe(c, [{ x0: 0, x1: 3, r0: r + 1.5, m: M.graphite }], k));
  s += tube(polyD(P, t1, 1, 24), r + 1.5, M.graphite);

  // brass end fitting
  const fit = [
    { x0: -6, x1: 40, r0: 15.5, m: br, deco: (kk) => ribs([10, 26], 15.5, kk, br, 1.4) },
    { x0: 40, x1: 58, r0: 21, m: br, deco: (kk) => hexLines(40, 58, 21, kk, br) },
    { x0: 58, x1: 66, r0: 9, m: br },
    { x0: 66, x1: 92, r0: 11, m: br },
    { x0: 92, x1: 96, r0: 11, r1: 9.5, m: br, faceDeco: (kk) => bore(c, 96, 3.4, kk, br, { ch: 1.5, depth: 1.2 }) },
  ];
  s += place(P[3][0], P[3][1], angleAt(P, 1), lathe(c, fit, k));
  return svg(c, s);
}

// Trigger - position 4: small ochre lever with rounded finger surface (not the metal hook 3)
function migTrigger() {
  const c = new Ctx('mig-trigger');
  const m = M.trigger;
  const F =
    'M112,196 C130,168 175,152 240,140 L455,100 Q474,97 480,114 L492,160 Q494,172 482,174 L445,176 L438,192 Q434,204 420,204 L372,204 C330,204 300,214 268,232 C225,256 168,256 132,236 C112,225 104,210 112,196 Z';
  const side = c.once('side', (id) => lin(id, [0, 0, 0, 1], [[0, m.lt], [0.3, m.base], [0.65, m.dk], [1, m.xd]]));
  const front = c.once('front', (id) => lin(id, [0, 0, 0.55, 1], [[0, m.lt], [0.45, m.base], [1, m.dk]]));
  const bevel = c.once('bevel', (id) =>
    lin(id, [0, 0, 0, 1], [[0, m.hl, 0.9], [0.4, m.lt, 0.2], [0.7, m.dk, 0.25], [1, m.xd, 0.8]]),
  );
  const recess = c.once('recess', (id) => lin(id, [0, 0, 0, 1], [[0, m.xd], [0.4, m.dk], [1, m.base]]));
  const boss = c.once(
    'boss',
    (id) =>
      `<radialGradient id="${id}" cx=".38" cy=".32" r=".75"><stop offset="0" stop-color="${m.hl}"/><stop offset=".45" stop-color="${m.lt}"/><stop offset="1" stop-color="${m.dk}"/></radialGradient>`,
  );
  const clip = c.uid('fc');
  c.defs.push(`<clipPath id="${clip}"><path d="${F}"/></clipPath>`);

  let s = shadow(c, 300, 276, 190, 15);
  s += '<g transform="translate(-6 4)">';
  // extruded thickness
  const NS = 16;
  const ex = 17;
  const ey = -13;
  for (let i = NS; i >= 1; i--) {
    s += `<path d="${F}" transform="translate(${f((ex * i) / NS)} ${f((ey * i) / NS)})" fill="${side}"${i === NS ? ' stroke="rgba(0,0,0,.55)" stroke-width="1.2"' : ''}/>`;
  }
  // front face
  s += `<path d="${F}" fill="${front}"/>`;
  const belly = 'M268,232 C225,256 168,256 132,236';
  let grip = '';
  [[4, -12], [7, -23], [10, -34], [13, -45]].forEach(([dx, dy]) => {
    grip += `<path d="${belly}" transform="translate(${dx} ${dy})" fill="none" stroke="${m.xd}" stroke-opacity=".5" stroke-width="1.6"/>`;
    grip += `<path d="${belly}" transform="translate(${dx} ${f(dy + 1.8)})" fill="none" stroke="${m.hl}" stroke-opacity=".4" stroke-width="1.1"/>`;
  });
  s += `<g clip-path="url(#${clip})">${grip}<path d="${F}" fill="none" stroke="${bevel}" stroke-width="9"/></g>`;
  // moulded recess
  s += `<path d="M372,146 L432,136 Q440,135 441,143 L442,160 Q442,168 434,168 L376,172 Q368,173 368,165 L368,153 Q368,147 372,146 Z" fill="${recess}" stroke="${m.xd}" stroke-opacity=".6" stroke-width="1"/>`;
  s += `<path d="M369.5,166 Q370.5,172.5 377,172 L433,168.2 Q441,167.6 441.8,160" fill="none" stroke="${m.hl}" stroke-opacity=".5" stroke-width="1"/>`;
  // pivot boss and pin bore
  s += `<circle cx="458" cy="134" r="14" fill="${boss}" stroke="${m.xd}" stroke-opacity=".6" stroke-width="1"/>`;
  s += `<circle cx="458" cy="134" r="6.4" fill="${m.xd}"/><circle cx="457.2" cy="132.6" r="4.8" fill="#0b0a07"/>`;
  s += `<path d="${F}" fill="none" stroke="rgba(0,0,0,.45)" stroke-width=".9"/>`;
  s += '</g>';
  return svg(c, s);
}

// Swan neck - position 1: bent brass tube, front seat, rear connector with nut, O-ring and thread
function migNeck() {
  const c = new Ctx('mig-neck');
  const br = M.brass;
  const cu = M.copper;
  const k = 0.34;
  const d = 'M130,238 C157,190 205,128 295,108 L375,92';
  const front = [
    { x0: -14, x1: 12, r0: 21.5, m: br },
    { x0: 12, x1: 32, r0: 20, r1: 19.5, m: cu },
    { x0: 32, x1: 35, r0: 19.5, r1: 18, m: cu, faceDeco: (kk) => bore(c, 35, 10.5, kk, cu, { threads: 3, depth: 1.3 }) },
  ];
  const rear = [
    { x0: -10, x1: 18, r0: 22.5, m: br },
    { x0: 18, x1: 22, r0: 26, r1: 29, m: br },
    { x0: 22, x1: 50, r0: 29, m: br, deco: (kk) => knurl(22, 50, 29, kk, br, 13) },
    { x0: 50, x1: 54, r0: 29, r1: 26, m: br },
    { x0: 54, x1: 62, r0: 21, m: br },
    { x0: 62, x1: 65, r0: 21.5, r1: 23, m: M.rubber },
    { x0: 65, x1: 68, r0: 23, r1: 21.5, m: M.rubber },
    { x0: 68, x1: 74, r0: 20, m: br },
    { x0: 74, x1: 112, r0: 17, m: br, thread: 5.5, depth: 1.8 },
    { x0: 112, x1: 124, r0: 10, m: cu, faceDeco: (kk) => bore(c, 124, 4.2, kk, cu, { depth: 1.2 }) },
  ];
  let s = shadow(c, 300, 292, 200, 13);
  s += tube(d, 21, br);
  s += place(130, 238, (Math.atan2(48, -27) * 180) / Math.PI, lathe(c, front, k));
  s += place(375, 92, (Math.atan2(-16, 80) * 180) / Math.PI, lathe(c, rear, k));
  return svg(c, s);
}

// Cable / hose assembly - positions 5–11: corrugated sheath with end cuff, conductors fanned out
function migCable() {
  const c = new Ctx('mig-cable');
  const k = 0.32;
  const gr = M.graphite;
  const rb = M.rubber;
  const rings = [];
  for (let x = -112; x < 56; x += 8) rings.push(x);
  const sheath = [
    { x0: -125, x1: 58, r0: 48, m: gr, deco: (kk) => ribs(rings, 48, kk, gr) },
    { x0: 58, x1: 66, r0: 52, m: rb },
    { x0: 66, x1: 72, r0: 55, m: rb },
    { x0: 72, x1: 78, r0: 52, m: rb },
    { x0: 78, x1: 84, r0: 55, m: rb },
    { x0: 84, x1: 96, r0: 52, m: rb, faceDeco: (kk) => bore(c, 96, 46, kk, rb, { depth: 0.6 }) },
  ];
  const clip = mouthClip(c, 96, 46, k);
  const H = [
    { P: [[60, 38], [150, 48], [190, 96], [236, 104]], r: 7, m: rb, cap: openCap(c, 7, rb, 0.55) }, // gas 9
    { P: [[60, 24], [160, 28], [210, 62], [285, 66]], r: 8, m: rb, cap: openCap(c, 8, rb, 0.45) }, // guide 8
    { P: [[60, -34], [150, -40], [175, -85], [226, -96]], r: 3.2, m: gr, cap: stripCap(3.2, gr) }, // control 5
    { P: [[60, -26], [160, -30], [200, -62], [250, -72]], r: 3.2, m: gr, cap: stripCap(3.2, gr) }, // control 5
    { P: [[60, -12], [170, -14], [230, -50], [300, -52]], r: 9, m: M.blue, cap: openCap(c, 9, M.blue, 0.58) }, // water 6
    { P: [[60, 8], [170, 8], [210, 18], [262, 18]], r: 12, m: M.red, cap: fitCap(c, 12) }, // power 7
  ];
  let s = shadow(c, 300, 292, 215, 15);
  s += `<g transform="translate(195 200) rotate(-8)">`;
  s += `<g mask="${fadeMask(c, -125, -55)}">${lathe(c, sheath, k)}</g>`;
  H.forEach((h) => {
    s += hose(c, h, k, clip);
  });
  s += `<ellipse cx="96" cy="0" rx="${f(k * 46)}" ry="46" fill="${c.mouth()}"/>`;
  s += `</g>`;
  return svg(c, s);
}

/* ================================================================== */
/* TIG parts                                                          */
/* ================================================================== */

// Ceramic cup - position 19: pink hollow cup with wall thickness and inner mouth
function tigCup() {
  const c = new Ctx('tig-cup');
  const m = M.ceramic;
  const k = 0.36;
  const segs = [
    { x0: -165, x1: -158, r0: 63, r1: 67, m },
    { x0: -158, x1: 40, r0: 67, r1: 66, m },
    { x0: 40, x1: 58, r0: 66, r1: 59, m },
    { x0: 58, x1: 75, r0: 59, r1: 50, m },
    { x0: 75, x1: 140, r0: 50, r1: 48, m },
    {
      x0: 140,
      x1: 146,
      r0: 48,
      r1: 46,
      m,
      faceDeco: (kk) => bore(c, 146, 36, kk, m, { depth: 1.35, ch: 3 }),
    },
  ];
  return svg(c, shadow(c, 312, 270, 185, 17) + `<g transform="translate(312 166) rotate(-8)">${lathe(c, segs, k)}</g>`);
}

// Collet - position 17: thin copper sleeve, single through-slot at the clamping end, electrode bore
function tigCollet() {
  const c = new Ctx('tig-collet');
  const m = M.copper;
  const k = 0.5;
  const phi = (22 * Math.PI) / 180;
  const cs = Math.cos(phi);
  const sn = Math.sin(phi);
  const sp = (x, r) => [x - k * r * cs, -r * sn];
  const slot = (kk) => {
    void kk;
    const a = sp(64, 16);
    const b = sp(150, 16);
    const e = sp(190, 13.5);
    const d = `M${pt(a)} L${pt(b)} L${pt(e)}`;
    return (
      `<path d="${d}" fill="none" stroke="#2a1408" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>` +
      `<path d="${d}" transform="translate(0 1.9)" fill="none" stroke="${m.hl}" stroke-opacity=".35" stroke-width=".9"/>`
    );
  };
  const faceSlot = (kk) => {
    const out1 = [190 - kk * 13.5 * cs, -13.5 * sn];
    const in1 = [190 - kk * 6.5 * cs, -6.5 * sn];
    const in2 = [190 + kk * 6.5 * cs, 6.5 * sn];
    const out2 = [190 + kk * 13.5 * cs, 13.5 * sn];
    return (
      bore(c, 190, 6.5, kk, m, { depth: 1.5, ch: 1.5 }) +
      `<path d="M${pt(out1)} L${pt(in1)} M${pt(in2)} L${pt(out2)}" stroke="#2a1408" stroke-width="2.4" stroke-linecap="round"/>`
    );
  };
  const segs = [
    { x0: -200, x1: -194, r0: 13.5, r1: 16, m },
    { x0: -194, x1: -180, r0: 16, m },
    { x0: -180, x1: -173, r0: 14.3, m },
    { x0: -173, x1: 150, r0: 16, m, deco: slot },
    { x0: 150, x1: 190, r0: 16, r1: 13.5, m, faceDeco: faceSlot },
  ];
  return svg(c, shadow(c, 305, 246, 195, 11) + `<g transform="translate(300 170) rotate(-10)">${lathe(c, segs, k)}</g>`);
}

// Collet body - standard position 18 only (gas lens 21 is an alternative, not shown)
function tigBody() {
  const c = new Ctx('tig-body');
  const m = M.copper;
  const k = 0.38;
  const ports = (kk) => hole(78, 27, 0, 10, 6.5, kk, m) + hole(78, 27, 62, 10, 6.5, kk, m) + hole(78, 27, -62, 10, 6.5, kk, m);
  const segs = [
    { x0: -182, x1: -176, r0: 15, r1: 19, m },
    { x0: -176, x1: -144, r0: 19, m },
    { x0: -146, x1: -140, r0: 29, r1: 33, m },
    { x0: -140, x1: 0, r0: 34, m, thread: 8, depth: 2.4 },
    { x0: 0, x1: 4, r0: 34, r1: 37, m },
    { x0: 4, x1: 18, r0: 37, m },
    { x0: 18, x1: 140, r0: 27, m, deco: ports },
    { x0: 140, x1: 175, r0: 27, r1: 21, m },
    { x0: 175, x1: 179, r0: 21, r1: 20, m, faceDeco: (kk) => bore(c, 179, 9, kk, m, { ch: 3.5, depth: 1.5 }) },
  ];
  return svg(c, shadow(c, 305, 254, 185, 15) + `<g transform="translate(302 168) rotate(-9)">${lathe(c, segs, k)}</g>`);
}

// Torch-head insulator - position 15: short pale ring with opening (material kept neutral)
function tigInsulator() {
  const c = new Ctx('tig-insulator');
  const m = M.insul;
  const k = 0.55;
  const segs = [
    { x0: -62, x1: -56, r0: 84, r1: 90, m },
    { x0: -56, x1: -50, r0: 90, r1: 93, m },
    { x0: -50, x1: 18, r0: 93, r1: 97, m },
    { x0: 18, x1: 28, r0: 97, r1: 95, m },
    { x0: 28, x1: 34, r0: 95, r1: 90, m, faceDeco: (kk) => bore(c, 34, 52, kk, m, { ch: 12, depth: 1.0 }) },
  ];
  return svg(c, shadow(c, 312, 284, 125, 15) + `<g transform="translate(314 166) rotate(-6)">${lathe(c, segs, k)}</g>`);
}

// Back cap - medium length 2.2: black tapered cap, grip collar, schematic sealing ring, threaded stud
function tigBackcap() {
  const c = new Ctx('tig-backcap');
  const g = M.graphite;
  const br = M.brass;
  const rb = M.rubber;
  const k = 0.34;
  const segs = [
    { x0: -196, x1: -192, r0: 8, r1: 14, m: g },
    { x0: -192, x1: -186, r0: 14, r1: 18.5, m: g },
    { x0: -186, x1: -177, r0: 18.5, r1: 21.5, m: g },
    { x0: -177, x1: -168, r0: 21.5, r1: 22.5, m: g },
    { x0: -168, x1: 90, r0: 22.5, r1: 32, m: g },
    { x0: 90, x1: 94, r0: 32, r1: 35, m: g },
    { x0: 94, x1: 120, r0: 35, m: g, deco: (kk) => knurl(94, 120, 35, kk, g, 11) },
    { x0: 120, x1: 126, r0: 35, r1: 32, m: g },
    { x0: 126, x1: 129, r0: 27, r1: 29, m: rb },
    { x0: 129, x1: 134, r0: 29, m: rb },
    { x0: 134, x1: 137, r0: 29, r1: 27, m: rb },
    { x0: 137, x1: 184, r0: 25, m: br, thread: 7, depth: 2.2 },
    { x0: 184, x1: 190, r0: 24, r1: 21, m: br, faceDeco: (kk) => bore(c, 190, 7, kk, br, { depth: 0.5 }) },
  ];
  return svg(c, shadow(c, 300, 268, 190, 13) + `<g transform="translate(300 168) rotate(-14)">${lathe(c, segs, k)}</g>`);
}

// Torch body - standard 1.1: black angled head with pale insulator face, handle stem, rib collar, brass connector
function tigHead() {
  const c = new Ctx('tig-head');
  const g = M.graphite;
  const br = M.brass;
  const ins = M.insul;
  const k = 0.38;
  const handle = [
    { x0: -10, x1: 40, r0: 27, m: g },
    { x0: 40, x1: 172, r0: 27, r1: 22, m: g },
  ];
  let x = 172;
  for (let i = 0; i < 5; i++) {
    handle.push({ x0: x, x1: x + 7, r0: 26.5, m: g });
    handle.push({ x0: x + 7, x1: x + 12, r0: 22.5, m: g });
    x += 12;
  }
  handle.push({ x0: 232, x1: 246, r0: 22.5, r1: 21, m: g });
  handle.push({ x0: 246, x1: 278, r0: 19, m: br, deco: (kk) => hexLines(246, 278, 19, kk, br) });
  handle.push({ x0: 278, x1: 294, r0: 12, m: br, faceDeco: (kk) => bore(c, 294, 5.5, kk, br, { ch: 2, depth: 1.3 }) });

  const head = [
    { x0: -86, x1: -82, r0: 22, r1: 28, m: g },
    { x0: -82, x1: -76, r0: 28, r1: 33, m: g },
    { x0: -76, x1: -68, r0: 33, r1: 36.5, m: g },
    { x0: -68, x1: 26, r0: 37, r1: 38, m: g },
    { x0: 26, x1: 34, r0: 38, r1: 36, m: g },
    { x0: 33, x1: 62, r0: 37.5, r1: 37, m: ins },
    {
      x0: 62,
      x1: 66,
      r0: 37,
      r1: 35,
      m: ins,
      faceDeco: (kk) =>
        `<ellipse cx="66" cy="0" rx="${f(kk * 19)}" ry="19" fill="${c.face(br)}" stroke="rgba(0,0,0,.4)" stroke-width=".7"/>` +
        bore(c, 66, 15, kk, br, { threads: 3, depth: 1.4 }),
    },
  ];
  let s = shadow(c, 300, 278, 200, 15);
  s += place(418, 155, 165, lathe(c, handle, k));
  s += place(418, 155, -78, lathe(c, head, k));
  return svg(c, s);
}

// Water-cooled cable group - AQ20 reference: fabric sleeve with gas 6, water 7, power 8, control 9 (stand-alone)
function tigHoses() {
  const c = new Ctx('tig-hoses');
  const k = 0.32;
  const nv = M.navy;
  const weave = c.once(
    'weave',
    (id) =>
      `<pattern id="${id}" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(40)"><rect width="2.2" height="5" fill="#fff" fill-opacity=".06"/></pattern>`,
  );
  const seamY = -44 * Math.sin((50 * Math.PI) / 180);
  const seamX = -k * 44 * Math.cos((50 * Math.PI) / 180);
  const sleeve = [
    {
      x0: -122,
      x1: 60,
      r0: 44,
      m: nv,
      deco: (kk) =>
        `<path d="${cylPath(-122, 44, 60, 44, kk)}" fill="${weave}"/>` +
        `<path d="M${f(-118 + seamX)},${f(seamY)} L${f(56 + seamX)},${f(seamY)}" stroke="${nv.hl}" stroke-opacity=".4" stroke-width="1.1" stroke-dasharray="4 3"/>`,
      faceDeco: (kk) => bore(c, 60, 41, kk, nv, { depth: 0.6 }),
    },
  ];
  const clip = mouthClip(c, 60, 41, k);
  const ctrlEnd = [196, -50];
  const H = [
    { P: [[44, -26], [115, -30], [155, -46], ctrlEnd], r: 6, m: M.grey, cap: [{ x0: -1, x1: 2, r0: 6, m: M.grey }] }, // control 9
    { P: [[44, -6], [120, -8], [160, -16], [206, -18]], r: 10, m: M.red, cap: fitCap(c, 10) }, // power 8
    { P: [[44, 14], [120, 16], [170, 26], [226, 28]], r: 8, m: M.blue, cap: openCap(c, 8, M.blue, 0.57) }, // water 7
    { P: [[44, 32], [110, 36], [150, 52], [204, 56]], r: 8, m: M.rubber, cap: openCap(c, 8, M.rubber, 0.57) }, // gas 6
  ];
  const W = [
    { P: [[198, -52.5], [212, -54], [220, -64], [234, -68]], r: 1.7, m: M.green },
    { P: [[198, -50], [214, -51], [226, -57], [242, -59]], r: 1.7, m: M.brown },
    { P: [[198, -47.5], [214, -47], [224, -49.5], [238, -48.5]], r: 1.7, m: M.white },
  ];
  let s = shadow(c, 300, 298, 210, 13);
  s += `<g transform="translate(244 214) rotate(-22)">`;
  s += `<g mask="${fadeMask(c, -122, -50)}">${lathe(c, sleeve, k)}</g>`;
  H.forEach((h) => {
    s += hose(c, h, k, clip);
  });
  W.forEach((w) => {
    s += tube(cubicD(w.P), w.r, w.m) + place(w.P[3][0], w.P[3][1], angleAt(w.P, 1), lathe(c, [{ x0: -0.5, x1: 8, r0: 1.15, m: M.copper }], k));
  });
  s += `<ellipse cx="60" cy="0" rx="${f(k * 41)}" ry="41" fill="${c.mouth()}"/>`;
  s += `</g>`;
  return svg(c, s);
}

/* ------------------------------------------------------------------ */
/* public API                                                          */
/* ------------------------------------------------------------------ */
const DRAW = {
  'mig-tip': migTip,
  'mig-nozzle': migNozzle,
  'mig-diffuser': migDiffuser,
  'mig-liner': migLiner,
  'mig-trigger': migTrigger,
  'mig-neck': migNeck,
  'mig-cable': migCable,
  'tig-cup': tigCup,
  'tig-collet': tigCollet,
  'tig-body': tigBody,
  'tig-insulator': tigInsulator,
  'tig-backcap': tigBackcap,
  'tig-head': tigHead,
  'tig-hoses': tigHoses,
};

export const drawingIds = Object.keys(DRAW);

export function drawPart(id) {
  const fn = DRAW[id];
  if (!fn) throw new Error(`drawPart: unknown part id "${id}"`);
  return fn();
}
