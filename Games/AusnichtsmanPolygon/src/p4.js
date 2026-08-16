/* ============================================================
   Мир: рельеф, тропинки, текстуры, растительность, скалы
   ============================================================ */

const GROUND_EXTENT = 260;   // сколько метров покрывает текстура песка
const WORLD_RADIUS = 430;

/** Тропинки заданы ломаными в мировых координатах (x, z). */
const PATHS = [
  [[0, 30], [0.6, 22], [-1.2, 14], [0.4, 6], [0, 1]],
  [[0, 6], [7, 1], [15, -4], [23, -11], [29, -21], [31, -32]],
  [[-1, 5], [-9, 1], [-17, -6], [-24, -16], [-27, -28]],
  [[0, 24], [10, 27], [20, 31], [29, 30], [35, 24]],
  [[0, 24], [-11, 26], [-21, 30], [-30, 28]],
  [[0, 2], [4, -6], [9, -13], [16, -19], [22, -24]],     // к ветряку
  [[0, 2], [-5, -7], [-9, -14], [-13, -21], [-16, -28]], // к чёрной дыре
  [[20, 31], [26, 30], [30, 28], [32, 25]],              // к палатке
];

/** Катмулл-Ром: сглаживаем ломаные, чтобы тропы вились. */
function smoothPath(pts, steps = 14) {
  const out = [];
  const p = [pts[0], ...pts, pts[pts.length - 1]];
  for (let i = 1; i < p.length - 2; i++) {
    for (let j = 0; j < steps; j++) {
      const t = j / steps, t2 = t * t, t3 = t2 * t;
      const x = 0.5 * ((2 * p[i][0]) + (-p[i - 1][0] + p[i + 1][0]) * t +
        (2 * p[i - 1][0] - 5 * p[i][0] + 4 * p[i + 1][0] - p[i + 2][0]) * t2 +
        (-p[i - 1][0] + 3 * p[i][0] - 3 * p[i + 1][0] + p[i + 2][0]) * t3);
      const z = 0.5 * ((2 * p[i][1]) + (-p[i - 1][1] + p[i + 1][1]) * t +
        (2 * p[i - 1][1] - 5 * p[i][1] + 4 * p[i + 1][1] - p[i + 2][1]) * t2 +
        (-p[i - 1][1] + 3 * p[i][1] - 3 * p[i + 1][1] + p[i + 2][1]) * t3);
      out.push([x, z]);
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}

const SMOOTH_PATHS = PATHS.map((p) => smoothPath(p));

function distToPaths(x, z) {
  let best = 1e9;
  for (const path of SMOOTH_PATHS) {
    for (let i = 0; i < path.length - 1; i++) {
      const [ax, az] = path[i], [bx, bz] = path[i + 1];
      const dx = bx - ax, dz = bz - az;
      const len2 = dx * dx + dz * dz || 1e-6;
      let t = ((x - ax) * dx + (z - az) * dz) / len2;
      t = clamp(t, 0, 1);
      const cx = ax + dx * t, cz = az + dz * t;
      const d = Math.hypot(x - cx, z - cz);
      if (d < best) best = d;
    }
  }
  return best;
}

/** Рельеф: поляна ровная, дальше пологие волны. */
function terrainH(x, z) {
  const d = Math.hypot(x, z);
  const ramp = smoothstep(13, 46, d);
  const h =
    1.15 * Math.sin(x * 0.021 + 0.4) * Math.cos(z * 0.018 - 0.9) +
    0.62 * Math.sin((x * 0.6 + z * 0.8) * 0.043 + 2.1) +
    0.26 * Math.sin((x * 0.9 - z * 0.5) * 0.11 + 0.7);
  const far = smoothstep(70, 260, d) * 6.0 * (0.6 + 0.4 * Math.sin(x * 0.008 + z * 0.006));
  return h * ramp * 1.2 + far + 0.05 * Math.sin(x * 0.31) * Math.cos(z * 0.27);
}

/* ---------------- текстура песка ---------------- */

function makeGroundTexture() {
  const S = 1024;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  const R = rng(20240807);
  const m = S / GROUND_EXTENT;                       // пикселей на метр
  const px = (x) => (x + GROUND_EXTENT / 2) * m;
  const pz = (z) => (z + GROUND_EXTENT / 2) * m;

  g.fillStyle = '#c3a179';
  g.fillRect(0, 0, S, S);

  // крупные пятна выветривания
  for (let i = 0; i < 700; i++) {
    const x = R() * S, y = R() * S, r = 18 + R() * 90;
    const tint = R();
    g.fillStyle = tint < 0.4 ? 'rgba(168,131,92,0.10)'
      : tint < 0.75 ? 'rgba(214,183,140,0.11)'
        : 'rgba(139,105,74,0.08)';
    g.beginPath();
    g.ellipse(x, y, r, r * (0.5 + R() * 0.7), R() * Math.PI, 0, TAU);
    g.fill();
  }

  // светлая утоптанная поляна
  const clearing = g.createRadialGradient(px(0), pz(0), 6 * m, px(0), pz(0), 17 * m);
  clearing.addColorStop(0, 'rgba(226,201,163,0.55)');
  clearing.addColorStop(1, 'rgba(226,201,163,0)');
  g.fillStyle = clearing;
  g.fillRect(0, 0, S, S);

  // тропинки: тёмная обочина, светлый утоптанный центр
  for (const path of SMOOTH_PATHS) {
    for (const pass of [
      { w: 4.4 * m, style: 'rgba(150,116,80,0.34)' },
      { w: 2.3 * m, style: 'rgba(226,203,166,0.72)' },
      { w: 1.1 * m, style: 'rgba(238,219,187,0.55)' },
    ]) {
      g.strokeStyle = pass.style;
      g.lineWidth = pass.w;
      g.lineCap = 'round';
      g.lineJoin = 'round';
      g.beginPath();
      path.forEach(([x, z], i) => (i ? g.lineTo(px(x), pz(z)) : g.moveTo(px(x), pz(z))));
      g.stroke();
    }
  }

  // камешки и сухие кустики сверху
  for (let i = 0; i < 5200; i++) {
    const x = R() * S, y = R() * S;
    const wx = (x / m) - GROUND_EXTENT / 2, wz = (y / m) - GROUND_EXTENT / 2;
    if (distToPaths(wx, wz) < 1.4 && R() < 0.85) continue;
    const s = 0.6 + R() * 2.4;
    g.fillStyle = R() < 0.5 ? 'rgba(112,88,64,0.34)' : 'rgba(233,214,180,0.30)';
    g.fillRect(x, y, s, s * (0.6 + R() * 0.8));
  }

  // мелкое зерно
  const img = g.getImageData(0, 0, S, S);
  const px32 = img.data;
  for (let i = 0; i < px32.length; i += 4) {
    const n = (R() - 0.5) * 16;
    px32[i] += n; px32[i + 1] += n; px32[i + 2] += n;
  }
  g.putImageData(img, 0, 0);
  return c;
}

/* ---------------- Млечный Путь: печём один раз в текстуру ----------------

   Поле гладкое и низкочастотное, поэтому 512×256 хватает с запасом, а в
   шейдере остаётся одна выборка вместо двух fbm по четыре октавы на пиксель.
*/

function makeMilkyTexture() {
  const W = 1024, H = 512;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  const img = g.createImageData(W, H);
  const px = img.data;

  // целочисленный хеш: на полмиллиона текселей синус был бы вчетверо дороже
  const hash3 = (x, y, z) => {
    let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(z | 0, 1442695041);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  };
  const noise3 = (x, y, z) => {
    const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
    let fx = x - xi, fy = y - yi, fz = z - zi;
    fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy); fz = fz * fz * (3 - 2 * fz);
    const n = (dx, dy, dz) => hash3(xi + dx, yi + dy, zi + dz);
    const l = (a, b, t) => a + (b - a) * t;
    return l(
      l(l(n(0,0,0), n(1,0,0), fx), l(n(0,1,0), n(1,1,0), fx), fy),
      l(l(n(0,0,1), n(1,0,1), fx), l(n(0,1,1), n(1,1,1), fx), fy), fz);
  };
  const fbm3 = (x, y, z) => {
    let v = 0, a = 0.5;
    for (let i = 0; i < 3; i++) { v += noise3(x, y, z) * a; a *= 0.5; x *= 2.03; y *= 2.03; z *= 2.03; }
    return v;
  };

  const pl = [0.80, 0.18, -0.57];
  const pn = Math.hypot(pl[0], pl[1], pl[2]);
  const pole = [pl[0] / pn, pl[1] / pn, pl[2] / pn];

  for (let row = 0; row < H; row++) {
    const el = Math.PI / 2 - ((row + 0.5) / H) * Math.PI;   // строка 0 — зенит
    const ce = Math.cos(el), se = Math.sin(el);
    for (let colI = 0; colI < W; colI++) {
      const az = ((colI + 0.5) / W) * TAU - Math.PI;
      const dx = ce * Math.cos(az), dy = se, dz = ce * Math.sin(az);

      const band = Math.abs(dx * pole[0] + dy * pole[1] + dz * pole[2]);
      const belt = Math.exp(-Math.pow(band / 0.165, 2));
      const core = Math.exp(-Math.pow(band / 0.055, 2));
      const dust = fbm3(dx * 5.5 + 3, dy * 5.5 + 3, dz * 5.5 + 3);
      const clouds = Math.pow(fbm3(dx * 12 - 7, dy * 12 - 7, dz * 12 - 7), 1.5);
      const milky = (belt * 0.85 + core * 0.9) * (0.45 + 1.15 * clouds)
                  * (0.30 + 0.70 * smoothstep(0.22, 0.80, dust));

      const k = milky * 1.15;
      const i = (row * W + colI) * 4;
      px[i]     = Math.min(255, lerp(0.46, 0.82, clouds) * k * 255);
      px[i + 1] = Math.min(255, lerp(0.50, 0.76, clouds) * k * 255);
      px[i + 2] = Math.min(255, lerp(0.68, 0.64, clouds) * k * 255);
      px[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  return c;
}

/* ---------------- спрайт полыни ---------------- */

function makeBushTexture() {
  const S = 128;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  const R = rng(777);
  g.clearRect(0, 0, S, S);
  g.lineCap = 'round';
  for (let i = 0; i < 90; i++) {
    const baseX = S / 2 + (R() - 0.5) * 26;
    const ang = -Math.PI / 2 + (R() - 0.5) * 2.0;
    const len = 26 + R() * 46;
    const x2 = baseX + Math.cos(ang) * len, y2 = S - 6 + Math.sin(ang) * len;
    const g1 = 104 + Math.floor(R() * 40);
    g.strokeStyle = `rgba(${g1 + 16},${g1 + 22},${Math.floor(g1 * 0.86)},${0.5 + R() * 0.4})`;
    g.lineWidth = 1.2 + R() * 2.1;
    g.beginPath();
    g.moveTo(baseX, S - 4);
    g.quadraticCurveTo((baseX + x2) / 2 + (R() - 0.5) * 12, (S + y2) / 2, x2, y2);
    g.stroke();
  }
  return c;
}

/* ---------------- мягкая тень под фигурой ---------------- */

function makeShadowTexture() {
  const S = 128;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  grad.addColorStop(0, 'rgba(60,40,26,0.42)');
  grad.addColorStop(0.55, 'rgba(70,48,32,0.20)');
  grad.addColorStop(1, 'rgba(80,56,38,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, S, S);
  return c;
}

/* ---------------- подписи фигур ---------------- */

function makeLabelTexture(text) {
  const W = 512, H = 128;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.clearRect(0, 0, W, H);
  g.font = '600 40px ui-sans-serif, "Helvetica Neue", Arial, sans-serif';
  if ('letterSpacing' in g) g.letterSpacing = '9px';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.shadowColor = 'rgba(30,20,12,0.75)';
  g.shadowBlur = 12;
  g.fillStyle = 'rgba(248,240,228,0.96)';
  g.fillText(text.toUpperCase(), W / 2, H / 2 - 6);
  g.shadowBlur = 0;
  g.fillStyle = 'rgba(248,240,228,0.5)';
  g.fillRect(W / 2 - 46, H / 2 + 26, 92, 2);
  return c;
}

/* ---------------- рельеф: полярная сетка ---------------- */

function buildTerrain() {
  const NR = 58, NT = 76;
  const verts = [], norms = [], idx = [];
  for (let i = 0; i <= NR; i++) {
    const r = Math.pow(i / NR, 2.05) * WORLD_RADIUS;
    for (let j = 0; j <= NT; j++) {
      const a = (j / NT) * TAU;
      const x = Math.cos(a) * r, z = Math.sin(a) * r;
      verts.push(x, terrainH(x, z), z);
      const e = Math.max(0.6, r * 0.03);
      const hx = terrainH(x + e, z) - terrainH(x - e, z);
      const hz = terrainH(x, z + e) - terrainH(x, z - e);
      const nx = -hx / (2 * e), nz = -hz / (2 * e);
      const l = Math.hypot(nx, 1, nz);
      norms.push(nx / l, 1 / l, nz / l);
    }
  }
  for (let i = 0; i < NR; i++) {
    for (let j = 0; j < NT; j++) {
      const a = i * (NT + 1) + j, b = a + NT + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return {
    pos: buffer(new Float32Array(verts)),
    nrm: buffer(new Float32Array(norms)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/* ---------------- камни, столовые горы, каменные круги ---------------- */

function buildSolids() {
  const pos = [], nrm = [], col = [], idx = [];
  const R = rng(9153);

  const pushTri = (a, b, c, color) => {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    nx /= l; ny /= l; nz /= l;
    for (const p of [a, b, c]) {
      idx.push(pos.length / 3);
      pos.push(p[0], p[1], p[2]);
      nrm.push(nx, ny, nz);
      col.push(color[0], color[1], color[2]);
    }
  };

  /** Гранёный «валун»: неровный многогранник вращения. */
  function boulder(cx, cy, cz, rad, height, color, sides = 7, rings = 3) {
    const grid = [];
    for (let i = 0; i <= rings; i++) {
      const t = i / rings;
      const ring = [];
      for (let j = 0; j < sides; j++) {
        const a = (j / sides) * TAU + t * 0.6;
        const rr = rad * (1 - t * t * 0.72) * (0.72 + R() * 0.5);
        ring.push([cx + Math.cos(a) * rr, cy + t * height * (0.85 + R() * 0.3), cz + Math.sin(a) * rr]);
      }
      grid.push(ring);
    }
    const top = [cx, cy + height, cz];
    for (let i = 0; i < rings; i++) {
      for (let j = 0; j < sides; j++) {
        const j2 = (j + 1) % sides;
        pushTri(grid[i][j], grid[i + 1][j], grid[i][j2], color);
        pushTri(grid[i][j2], grid[i + 1][j], grid[i + 1][j2], color);
      }
    }
    for (let j = 0; j < sides; j++) pushTri(grid[rings][j], top, grid[rings][(j + 1) % sides], color);
  }

  /** Столовая гора: усечённая призма с осыпью у подножия. */
  function mesa(cx, cz, rad, height, color) {
    const sides = 11;
    const base = [], mid = [], top = [];
    const y0 = terrainH(cx, cz) - 2;
    for (let j = 0; j < sides; j++) {
      const a = (j / sides) * TAU + R() * 0.2;
      const wob = 0.78 + R() * 0.44;
      base.push([cx + Math.cos(a) * rad * 1.42 * wob, y0, cz + Math.sin(a) * rad * 1.42 * wob]);
      mid.push([cx + Math.cos(a) * rad * wob, y0 + height * 0.32, cz + Math.sin(a) * rad * wob]);
      top.push([cx + Math.cos(a) * rad * 0.86 * wob, y0 + height, cz + Math.sin(a) * rad * 0.86 * wob]);
    }
    const capColor = [color[0] * 1.1, color[1] * 1.06, color[2] * 1.02];
    for (let j = 0; j < sides; j++) {
      const k = (j + 1) % sides;
      pushTri(base[j], mid[j], base[k], color);
      pushTri(base[k], mid[j], mid[k], color);
      pushTri(mid[j], top[j], mid[k], color);
      pushTri(mid[k], top[j], top[k], color);
    }
    for (let j = 1; j < sides - 1; j++) pushTri(top[0], top[j], top[j + 1], capColor);
  }

  // дальние столовые горы
  const mesas = [
    [-300, -230, 46, 46], [170, -330, 62, 58], [345, -95, 50, 40],
    [-360, 130, 70, 52], [60, 385, 56, 34], [-175, 355, 40, 28],
    [300, 210, 44, 30],
  ];
  for (const [x, z, r, h] of mesas) {
    mesa(x, z, r, h, [0.40 + R() * 0.05, 0.28 + R() * 0.04, 0.24 + R() * 0.03]);
  }

  // валуны по всей поляне, но не на тропах
  for (let i = 0; i < 90; i++) {
    const a = R() * TAU, r = 12 + Math.pow(R(), 0.7) * 105;
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (distToPaths(x, z) < 1.9) continue;
    const s = 0.25 + Math.pow(R(), 2) * 1.9;
    boulder(x, terrainH(x, z) - s * 0.25, z, s, s * (0.7 + R() * 0.8),
      [0.50 + R() * 0.10, 0.39 + R() * 0.07, 0.30 + R() * 0.05]);
  }

  // каменные круги под фигурами + пирамидки на концах троп
  for (const s of SHAPES) {
    for (let j = 0; j < 13; j++) {
      const a = (j / 13) * TAU + 0.3;
      const rr = 2.15 + R() * 0.3;
      const x = s.home[0] + Math.cos(a) * rr, z = s.home[2] + Math.sin(a) * rr;
      const sz = 0.16 + R() * 0.16;
      boulder(x, terrainH(x, z) - 0.05, z, sz, sz * 1.2,
        [0.53 + R() * 0.07, 0.42 + R() * 0.05, 0.33 + R() * 0.04], 6, 2);
    }
  }
  for (const path of SMOOTH_PATHS) {
    const [x, z] = path[path.length - 1];
    const base = terrainH(x, z);
    for (let j = 0; j < 5; j++) {
      const sz = 0.5 - j * 0.075;
      boulder(x + (R() - 0.5) * 0.2, base + j * 0.36, z + (R() - 0.5) * 0.2, sz, sz * 0.85,
        [0.48 + R() * 0.06, 0.37 + R() * 0.05, 0.29 + R() * 0.04], 7, 2);
    }
  }

  addWindmill({ pushTri, boulder });

  return {
    pos: buffer(new Float32Array(pos)),
    nrm: buffer(new Float32Array(nrm)),
    col: buffer(new Float32Array(col)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/* ---------------- кусты полыни ---------------- */

function buildBushes() {
  const center = [], corner = [], uv = [], phase = [], idx = [];
  const R = rng(4242);
  let n = 0;

  const quad = (x, y, z, w, h, ph, rotated) => {
    const base = n * 4;
    for (const [cx, cy, u, v] of [[-w, 0, 0, 0], [w, 0, 1, 0], [w, h, 1, 1], [-w, h, 0, 1]]) {
      center.push(x, y, z);
      corner.push(rotated ? cx * 0.35 : cx, cy);
      uv.push(u, v);
      phase.push(ph);
    }
    idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
    n++;
  };

  for (let i = 0; i < 260; i++) {
    const a = R() * TAU, r = 9 + Math.pow(R(), 0.6) * 120;
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (distToPaths(x, z) < 2.1) continue;
    if (Math.hypot(x, z) < 11) continue;
    if (Math.hypot(x - MILL.x, z - MILL.z) < 4.2) continue;
    if (Math.hypot(x - TANK.x, z - TANK.z) < 3.4) continue;
    if (Math.hypot(x - TENT.x, z - TENT.z) < 4.0) continue;
    const h = 0.5 + R() * 0.85, w = h * (0.42 + R() * 0.25);
    const y = terrainH(x, z) - 0.06;
    const ph = R() * TAU;
    quad(x, y, z, w, h, ph, false);
    quad(x, y, z, w, h, ph + 1.1, true);
  }

  return {
    center: buffer(new Float32Array(center)),
    corner: buffer(new Float32Array(corner)),
    uv: buffer(new Float32Array(uv)),
    phase: buffer(new Float32Array(phase)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/* ---------------- плоские квадраты (тени) и билборды (подписи) ---------------- */

function buildQuads(items, size) {
  const center = [], corner = [], uv = [], phase = [], idx = [];
  items.forEach((it, k) => {
    const s = size(it);
    const base = k * 4;
    for (const [cx, cy, u, v] of [[-s, -s, 0, 0], [s, -s, 1, 0], [s, s, 1, 1], [-s, s, 0, 1]]) {
      center.push(it[0], it[1], it[2]);
      corner.push(cx, cy);
      uv.push(u, v);
      phase.push(0);
    }
    idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  });
  return {
    center: buffer(new Float32Array(center)),
    corner: buffer(new Float32Array(corner)),
    uv: buffer(new Float32Array(uv)),
    phase: buffer(new Float32Array(phase)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}
