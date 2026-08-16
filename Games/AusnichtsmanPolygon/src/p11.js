/* ============================================================
   Мир Полигона Гамма: чернозём, море, роща, полигон, дорога, город
   ============================================================ */

const G = {
  R: 7000,                       // радиус ландшафта, метров
  flat: PAD.y,                   // отметка выровненных площадок
  sea: PAD.y - 16,               // уровень моря
  shore: -1150,                  // берег идёт вдоль этой линии по x
  pool: { x: -150, z: 95, w: 52, d: 30, rim: 4.0 },
  zero: { x: 1500, z: 400 },     // мишенное поле в стороне от дороги
  city: { x: 3480, z: -3505 },
  car: { x: 6, z: 24 },
  sith: { x: 25, z: 17 },
};
G.cityDist = Math.hypot(G.city.x - PAD.x, G.city.z - PAD.z);

/** Гладкий шум по координатам — основа рельефа Гаммы. */
function gnoise(x, z) {
  const xi = Math.floor(x), zi = Math.floor(z);
  let fx = x - xi, fz = z - zi;
  fx = fx * fx * (3 - 2 * fx); fz = fz * fz * (3 - 2 * fz);
  const h = (a, b) => {
    let n = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  };
  return lerp(lerp(h(xi, zi), h(xi + 1, zi), fx), lerp(h(xi, zi + 1), h(xi + 1, zi + 1), fx), fz);
}

/* Выровненные участки: у каждого своя отметка, иначе город оказывается
   в яме и его не видно с дороги. */
const SITES = [
  { x: PAD.x, z: PAD.z, r0: 45, r1: 150, y: 0 },
  { x: G.pool.x, z: G.pool.z, r0: 80, r1: 210, y: 0 },
  { x: G.zero.x, z: G.zero.z, r0: 700, r1: 1600, y: 1.5 },
  { x: G.city.x, z: G.city.z, r0: 780, r1: 1700, y: 4.0 },
];

/** Вес выравнивания и отметка, к которой прижимается земля. */
function gammaFlat(x, z) {
  let w = 0, y = 0;
  for (const s of SITES) {
    const k = 1 - smoothstep(s.r0, s.r1, Math.hypot(x - s.x, z - s.z));
    if (k > w) { w = k; y = s.y; }
  }
  // полоса дороги: отметка плавно переходит от площадки к городу
  const dx = G.city.x - PAD.x, dz = G.city.z - PAD.z;
  const L2 = dx * dx + dz * dz;
  const t = clamp(((x - PAD.x) * dx + (z - PAD.z) * dz) / L2, 0, 1);
  const rd = Math.hypot(PAD.x + dx * t - x, PAD.z + dz * t - z);
  const k = 1 - smoothstep(16, 80, rd);
  if (k > w) { w = k; y = lerp(0, 4.0, t); }
  return { w, y };
}

/** Попала ли точка на городскую улицу: там ни травы, ни деревьев. */
function onCityStreet(x, z) {
  const dx = x - G.city.x, dz = z - G.city.z;
  const span = 8 * 62 + 24;
  if (Math.abs(dx) > span || Math.abs(dz) > span) return false;
  // улицы идут по чётным линиям сетки с шагом 62 метра
  const nearLine = (v) => {
    const k = v / 62;
    return Math.abs(k - 2 * Math.round(k / 2)) * 62 < 8.5;
  };
  return nearLine(dx) || nearLine(dz);
}

/** Расстояние до оси дороги — по нему кладём полотно и обочины. */
function roadDist(x, z) {
  const dx = G.city.x - PAD.x, dz = G.city.z - PAD.z;
  const L2 = dx * dx + dz * dz;
  const t = clamp(((x - PAD.x) * dx + (z - PAD.z) * dz) / L2, 0, 1);
  return Math.hypot(PAD.x + dx * t - x, PAD.z + dz * t - z);
}

/**
 * Рельеф Гаммы: пологая степь, к западу спускается в море,
 * а под площадкой, бассейном, полигоном и городом выровнена.
 */
function gammaH(x, z) {
  /* Степь пологая: сильный рельеф прятал бы город и мишенное поле
     за ближайшим бугром. Все низины выше уровня моря. */
  const base = G.flat + 3
             + (gnoise(x * 0.0009, z * 0.0009) - 0.5) * 16
             + (gnoise(x * 0.0055 + 40, z * 0.0055 - 20) - 0.5) * 5.5
             + (gnoise(x * 0.021 + 7, z * 0.021 + 13) - 0.5) * 1.8;
  // берег: плавный уход под воду западнее G.shore
  const toSea = smoothstep(G.shore + 420, G.shore - 620, x);
  let h = lerp(base, G.sea - 24, toSea);
  const flat = gammaFlat(x, z);
  h = lerp(h, G.flat + flat.y + (gnoise(x * 0.02, z * 0.02) - 0.5) * 0.4, flat.w);
  // чаша бассейна вырыта в грунте, вода стоит вровень с землёй
  const P = G.pool;
  const inPool = (1 - smoothstep(P.w - 2, P.w + 1, Math.abs(x - P.x)))
               * (1 - smoothstep(P.d - 2, P.d + 1, Math.abs(z - P.z)));
  h = lerp(h, G.flat - 3.6, inPool);
  return h;
}

/* Сетка ландшафта Гаммы: у горизонта её шаг доходит до семидесяти метров,
   поэтому нарисованная поверхность заметно расходится с аналитической
   высотой. Всё, что должно лежать на земле, спрашивает высоту у самой
   сетки — иначе дорога тонет в бугре, а игрок проваливается под грунт. */
const GT = { NR: 78, NT: 104, pow: 2.4 };

/** Высота ровно той поверхности, которая нарисована. */
function gammaMeshH(x, z) {
  const r = Math.hypot(x, z);
  if (r >= G.R) return gammaH(x, z);
  const u = Math.pow(r / G.R, 1 / GT.pow) * GT.NR;
  let a = Math.atan2(z, x);
  if (a < 0) a += TAU;
  const v = (a / TAU) * GT.NT;
  const i0 = Math.min(Math.floor(u), GT.NR - 1), fu = u - i0;
  const j0 = Math.floor(v) % GT.NT, fv = v - Math.floor(v);
  const j1 = (j0 + 1) % GT.NT;
  const node = (i, j) => {
    const rr = Math.pow(i / GT.NR, GT.pow) * G.R;
    const aa = (j / GT.NT) * TAU;
    return gammaH(Math.cos(aa) * rr, Math.sin(aa) * rr);
  };
  const h00 = node(i0, j0), h10 = node(i0 + 1, j0), h01 = node(i0, j1), h11 = node(i0 + 1, j1);
  // тот же раскрой на треугольники, что и в буфере индексов
  return fu + fv <= 1
    ? h00 + fu * (h10 - h00) + fv * (h01 - h00)
    : h11 + (1 - fu) * (h01 - h11) + (1 - fv) * (h10 - h11);
}

/** Высота земли в текущем мире. */
function groundH(x, z) {
  return game.world === 'earth' ? terrainH(x, z) : gammaMeshH(x, z);
}

/* ---------------- текстуры Гаммы ---------------- */

/** Чернозём: жирная тёмная почва с комками, редкой травой и колеёй дороги. */
function makeSoilTexture() {
  const S = 512;
  const c = document.createElement('canvas');
  c.width = S; c.height = S;
  const g = c.getContext('2d');
  const img = g.createImageData(S, S);
  const px = img.data;
  const hash = (a, b) => {
    let n = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  };
  const noise = (x, y) => {
    const xi = Math.floor(x), yi = Math.floor(y);
    let fx = x - xi, fy = y - yi;
    fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
    return lerp(lerp(hash(xi, yi), hash(xi + 1, yi), fx),
                lerp(hash(xi, yi + 1), hash(xi + 1, yi + 1), fx), fy);
  };
  const fbm = (x, y, o) => { let v = 0, a = 0.5; for (let i = 0; i < o; i++) { v += noise(x, y) * a; a *= 0.5; x *= 2.07; y *= 2.07; } return v; };
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      // комки земли — крупный шум, поверх мелкая крупа
      const clod = fbm(x * 0.035, y * 0.035, 4);
      const grit = fbm(x * 0.32, y * 0.32, 2);
      const v = 0.055 + clod * 0.10 + grit * 0.05;
      let r = v * 1.20, gg = v * 1.02, b = v * 0.86;
      // редкие пучки травы, проросшие сквозь пашню
      const grass = smoothstep(0.60, 0.80, fbm(x * 0.09 + 30, y * 0.09 - 12, 3));
      r = lerp(r, 0.115 + grit * 0.09, grass);
      gg = lerp(gg, 0.190 + grit * 0.12, grass);
      b = lerp(b, 0.070 + grit * 0.05, grass);
      const i = (y * S + x) * 4;
      px[i] = r * 255; px[i + 1] = gg * 255; px[i + 2] = b * 255; px[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  return c;
}

/** Пучок травы: несколько былинок с прожилкой, снизу темнее. */
function makeGrassTexture() {
  const W = 128, H = 128;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.clearRect(0, 0, W, H);
  const R = rngLite(9931);
  for (let i = 0; i < 16; i++) {
    const x0 = 18 + R() * (W - 36);
    const hgt = 52 + R() * 66;
    const bend = (R() - 0.5) * 46;
    const wid = 2.6 + R() * 3.0;
    const tone = 0.55 + R() * 0.45;
    const grd = g.createLinearGradient(0, H, 0, H - hgt);
    grd.addColorStop(0, `rgba(${Math.round(24 * tone)},${Math.round(48 * tone)},${Math.round(16 * tone)},1)`);
    grd.addColorStop(0.55, `rgba(${Math.round(58 * tone)},${Math.round(104 * tone)},${Math.round(34 * tone)},1)`);
    grd.addColorStop(1, `rgba(${Math.round(120 * tone)},${Math.round(158 * tone)},${Math.round(62 * tone)},1)`);
    g.fillStyle = grd;
    g.beginPath();
    g.moveTo(x0 - wid, H);
    g.quadraticCurveTo(x0 - wid * 0.5 + bend * 0.5, H - hgt * 0.6, x0 + bend, H - hgt);
    g.quadraticCurveTo(x0 + wid * 0.5 + bend * 0.5, H - hgt * 0.6, x0 + wid, H);
    g.closePath();
    g.fill();
  }
  return c;
}

/** Лиственная карта: гроздь листьев с прожилками и просветами. */
function makeLeafTexture() {
  const S = 128;
  const c = document.createElement('canvas');
  c.width = S; c.height = S;
  const g = c.getContext('2d');
  g.clearRect(0, 0, S, S);
  const R = rngLite(4477);
  for (let i = 0; i < 42; i++) {
    const cx = 12 + R() * (S - 24), cy = 12 + R() * (S - 24);
    const rr = 6 + R() * 13;
    const a = R() * TAU;
    const tone = 0.5 + R() * 0.5;
    g.save();
    g.translate(cx, cy);
    g.rotate(a);
    g.fillStyle = `rgba(${Math.round(38 * tone + 8)},${Math.round(96 * tone + 14)},${Math.round(30 * tone + 6)},${0.82 + R() * 0.18})`;
    g.beginPath();
    g.ellipse(0, 0, rr, rr * 0.52, 0, 0, TAU);
    g.fill();
    // прожилка
    g.strokeStyle = `rgba(${Math.round(120 * tone)},${Math.round(150 * tone)},${Math.round(70 * tone)},0.55)`;
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(-rr, 0); g.lineTo(rr, 0); g.stroke();
    g.restore();
  }
  return c;
}

/** Маленький детерминированный генератор — чтобы мир был один и тот же. */
function rngLite(seed) {
  let s = seed >>> 0;
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
}

/* ---------------- геометрия ландшафта и моря ---------------- */

function buildGammaTerrain() {
  const NR = GT.NR, NT = GT.NT;
  const pos = [], nrm = [], idx = [];
  for (let i = 0; i <= NR; i++) {
    const r = Math.pow(i / NR, 2.4) * G.R;
    for (let j = 0; j <= NT; j++) {
      const a = (j / NT) * TAU;
      const x = Math.cos(a) * r, z = Math.sin(a) * r;
      pos.push(x, gammaH(x, z), z);
      const e = Math.max(1.4, r * 0.02);
      const hx = gammaH(x + e, z) - gammaH(x - e, z);
      const hz = gammaH(x, z + e) - gammaH(x, z - e);
      const nx = -hx / (2 * e), nz = -hz / (2 * e);
      const l = Math.hypot(nx, 1, nz);
      nrm.push(nx / l, 1 / l, nz / l);
    }
  }
  for (let i = 0; i < NR; i++) {
    for (let j = 0; j < NT; j++) {
      const a = i * (NT + 1) + j, b = a + NT + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return {
    pos: buffer(new Float32Array(pos)), nrm: buffer(new Float32Array(nrm)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length,
  };
}

/** Море: большой диск на уровне воды, волны считает шейдер. */
/** Море: плита к западу от берега, за сушу не заходит. */
function buildSea() {
  const N = 60, pos = [], idx = [];
  const x0 = -26000, x1 = G.shore + 260, z0 = -22000, z1 = 22000;
  for (let i = 0; i <= N; i++) {
    for (let j = 0; j <= N; j++) {
      // к берегу сетка гуще: там видно волну
      const u = Math.pow(i / N, 0.45);
      pos.push(lerp(x1, x0, u), G.sea, lerp(z0, z1, j / N));
    }
  }
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      const a = i * (N + 1) + j, b = a + N + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return { pos: buffer(new Float32Array(pos)),
           idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
}

/* Открытая вода: волны, блик и пена у берега. */
const seaProg = program(`
attribute vec3 aPos;
uniform mat4 uVP;
uniform float uTime;
varying vec3 vW;
void main() {
  vec3 p = aPos;
  p.y += sin(p.x * 0.031 + uTime * 1.1) * 0.42 + sin(p.z * 0.047 - uTime * 0.8) * 0.34;
  vW = p;
  gl_Position = uVP * vec4(p, 1.0);
}`, PRECISION + `
varying vec3 vW;
uniform vec3 uCam;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform float uTime;
uniform float uFogK;
uniform float uShallow;   // 1 — прозрачная вода бассейна
void main() {
  // рябь: две наклонные волны дают наклон нормали
  float w1 = sin(vW.x * 0.31 + uTime * 1.7), w2 = sin(vW.z * 0.27 - uTime * 1.3);
  float w3 = sin((vW.x + vW.z) * 0.11 + uTime * 0.6);
  vec3 N = normalize(vec3(w1 * 0.055 + w3 * 0.03, 1.0, w2 * 0.055 - w3 * 0.03));
  vec3 V = normalize(uCam - vW);
  float fres = pow(1.0 - max(dot(N, V), 0.0), 4.0);
  vec3 deep = vec3(0.016, 0.062, 0.098);
  vec3 shallow = mix(deep, vec3(0.060, 0.205, 0.215), uShallow);
  vec3 col = mix(deep, shallow, 0.35 + 0.65 * w3 * 0.5 + 0.32);
  // отражение неба: берём дымку, а не белый — иначе вода светится сама по себе
  col = mix(col, uHaze * 0.72 + vec3(0.02, 0.035, 0.055), fres * 0.55);
  float spec = pow(max(dot(reflect(-V, N), uSun), 0.0), 220.0);
  col += uLight * spec * 0.9;
  col *= 0.45 + 0.55 * max(uSun.y + 0.35, 0.0);
  float d = length(uCam - vW);
  col = mix(col, uHaze, 1.0 - exp(-pow(d * uFogK, 2.0)));
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---------------- трава: сетка, бегущая за камерой ---------------- */

const GRASS_CELL = 2.1;         // метр сетки
const GRASS_SPAN = 21;          // клеток в каждую сторону
const GRASS_PER = 2;            // пучков в клетке
const GRASS_MAX = (GRASS_SPAN * 2 + 1) * (GRASS_SPAN * 2 + 1) * GRASS_PER;

const grass = {
  center: new Float32Array(GRASS_MAX * 4 * 3),
  corner: new Float32Array(GRASS_MAX * 4 * 2),
  uv: new Float32Array(GRASS_MAX * 4 * 2),
  phase: new Float32Array(GRASS_MAX * 4),
  idx: new Uint16Array(GRASS_MAX * 6),
  gCenter: gl.createBuffer(), gCorner: gl.createBuffer(),
  gUv: gl.createBuffer(), gPhase: gl.createBuffer(), gIdx: gl.createBuffer(),
  n: 0, cx: 1e9, cz: 1e9,
};
(() => {
  for (let i = 0; i < GRASS_MAX; i++) {
    const k = i * 6, o = i * 4;
    grass.idx[k] = o; grass.idx[k + 1] = o + 1; grass.idx[k + 2] = o + 2;
    grass.idx[k + 3] = o; grass.idx[k + 4] = o + 2; grass.idx[k + 5] = o + 3;
    const u = i * 8;
    grass.uv[u] = 0; grass.uv[u + 1] = 0;
    grass.uv[u + 2] = 1; grass.uv[u + 3] = 0;
    grass.uv[u + 4] = 1; grass.uv[u + 5] = 1;
    grass.uv[u + 6] = 0; grass.uv[u + 7] = 1;
  }
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, grass.gIdx);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, grass.idx, gl.STATIC_DRAW);
})();

/**
 * Пересобираем поле травы, когда камера ушла на клетку: держим вокруг
 * игрока квадрат тридцать на тридцать метров, дальше траву не видно всё равно.
 */
function updateGrass(x, z) {
  const cx = Math.floor(x / GRASS_CELL), cz = Math.floor(z / GRASS_CELL);
  if (cx === grass.cx && cz === grass.cz) return;
  grass.cx = cx; grass.cz = cz;
  let n = 0;
  for (let i = -GRASS_SPAN; i <= GRASS_SPAN; i++) {
    for (let j = -GRASS_SPAN; j <= GRASS_SPAN; j++) {
      const gx = (cx + i) * GRASS_CELL, gz = (cz + j) * GRASS_CELL;
      if (Math.hypot(gx - x, gz - z) > GRASS_SPAN * GRASS_CELL) continue;
      for (let k = 0; k < GRASS_PER; k++) {
        const h1 = gnoise(gx * 0.71 + k * 3.1, gz * 0.71 - k * 1.7);
        const h2 = gnoise(gx * 1.13 - k * 2.3, gz * 1.13 + k * 5.9);
        const px = gx + h1 * GRASS_CELL, pz = gz + h2 * GRASS_CELL;
        const y = gammaMeshH(px, pz);
        // на дороге, в воде и на выжженной земле трава не растёт
        if (y < G.sea + 1.5 || roadDist(px, pz) < 9 || onCityStreet(px, pz)) continue;
        let burnt = 0;
        for (const c of CRATERS) burnt = Math.max(burnt, 1 - smoothstep(70, 130, Math.hypot(px - c.x, pz - c.z)));
        if (burnt > 0.5) continue;
        const s = 0.26 + gnoise(px * 2.7, pz * 2.7) * 0.34;
        const o3 = n * 12, o2 = n * 8, o1 = n * 4;
        for (let v = 0; v < 4; v++) {
          grass.center[o3 + v * 3] = px;
          grass.center[o3 + v * 3 + 1] = y;
          grass.center[o3 + v * 3 + 2] = pz;
          grass.phase[o1 + v] = (px + pz) * 0.7;
        }
        grass.corner[o2 + 0] = -s * 0.55; grass.corner[o2 + 1] = 0;
        grass.corner[o2 + 2] = s * 0.55;  grass.corner[o2 + 3] = 0;
        grass.corner[o2 + 4] = s * 0.55;  grass.corner[o2 + 5] = s * 1.5;
        grass.corner[o2 + 6] = -s * 0.55; grass.corner[o2 + 7] = s * 1.5;
        if (++n >= GRASS_MAX) break;
      }
    }
  }
  grass.n = n;
  gl.bindBuffer(gl.ARRAY_BUFFER, grass.gCenter);
  gl.bufferData(gl.ARRAY_BUFFER, grass.center.subarray(0, n * 12), gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, grass.gCorner);
  gl.bufferData(gl.ARRAY_BUFFER, grass.corner.subarray(0, n * 8), gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, grass.gUv);
  gl.bufferData(gl.ARRAY_BUFFER, grass.uv.subarray(0, n * 8), gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, grass.gPhase);
  gl.bufferData(gl.ARRAY_BUFFER, grass.phase.subarray(0, n * 4), gl.DYNAMIC_DRAW);
}

/* ---------------- листва и кора: программа для карт с прозрачностью ---------------- */

const foliageProg = program(`
attribute vec3 aPos;
attribute vec3 aNormal;
attribute vec2 aUv;
attribute float aPhase;
attribute vec3 aColor;
uniform mat4 uVP;
uniform float uTime;
uniform float uSway;
varying vec2 vUv;
varying vec3 vN;
varying vec3 vW;
varying vec3 vC;
void main() {
  vec3 p = aPos;
  // ветер: качаем тем сильнее, чем выше от земли
  float s = sin(uTime * 1.3 + aPhase) + 0.45 * sin(uTime * 2.7 + aPhase * 1.9);
  p.xz += s * uSway * max(aPhase * 0.0 + p.y * 0.02, 0.0);
  vUv = aUv; vN = aNormal; vW = p; vC = aColor;
  gl_Position = uVP * vec4(p, 1.0);
}`, PRECISION + `
varying vec2 vUv;
varying vec3 vN;
varying vec3 vW;
varying vec3 vC;
uniform sampler2D uTex;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform vec3 uCam;
uniform vec3 uTint;
uniform float uFogK;
void main() {
  vec4 t = texture2D(uTex, vUv);
  if (t.a < 0.42) discard;
  vec3 N = normalize(vN);
  // листва двусторонняя и заодно немного просвечивает
  float ndl = abs(dot(N, uSun));
  float back = max(0.0, -dot(N, uSun)) * 0.35;
  vec3 col = t.rgb * vC * uTint * (0.55 * uAmb + (ndl * 0.75 + back) * uLight);
  float d = length(uCam - vW);
  col = mix(col, uHaze, 1.0 - exp(-pow(d * uFogK, 2.0)));
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---------------- деревья ---------------- */

/* Дерево строим из ствола-верёвки, ветвей второго порядка и гроздей
   листвы крестами. Все деревья складываем в несколько крупных мешей —
   иначе на сто пятьдесят стволов уйдёт триста вызовов отрисовки. */

const TREES = [];
const TREE_CHUNK = 34;
const treeChunks = [];

function seedTrees() {
  const R = rngLite(20240915);
  const put = (x, z, scale) => {
    if (Math.hypot(x - PAD.x, z - PAD.z) < 34) return;
    if (roadDist(x, z) < 16) return;
    if (Math.abs(x - G.pool.x) < G.pool.w + 12 && Math.abs(z - G.pool.z) < G.pool.d + 12) return;
    const y = gammaMeshH(x, z);
    if (y < G.sea + 3) return;
    if (Math.hypot(x - G.city.x, z - G.city.z) < 900) return;
    TREES.push({ x, y, z, s: scale, yaw: R() * TAU, seed: (R() * 1e6) | 0,
                 burn: 0, fell: 0, state: 0 });
  };
  // роща у площадки
  for (let i = 0; i < 60; i++) {
    const a = R() * TAU, r = 45 + Math.pow(R(), 0.7) * 330;
    put(PAD.x + Math.cos(a) * r, PAD.z + Math.sin(a) * r, 0.75 + R() * 0.65);
  }
  // лес вокруг мишенного поля — ему и гореть
  for (let i = 0; i < 78; i++) {
    const a = R() * TAU, r = 180 + Math.pow(R(), 0.6) * 620;
    put(G.zero.x + Math.cos(a) * r, G.zero.z + Math.sin(a) * r, 0.8 + R() * 0.8);
  }
  // редкие островки по степи
  for (let i = 0; i < 44; i++) {
    const a = R() * TAU, r = 500 + R() * 2400;
    put(PAD.x + Math.cos(a) * r, PAD.z + Math.sin(a) * r, 0.7 + R() * 0.9);
  }
}
seedTrees();

/** Кладёт одно дерево в накопители: ствол с ветками и грозди листвы. */
function pushTree(t, wood, leaf) {
  const R = rngLite(t.seed);
  const s = t.s;
  /* Поваленное дерево — поворот всего ствола вокруг горизонтальной оси,
     перпендикулярной направлению взрыва, с опорой у самого комля. */
  const lean = t.fell * 1.42;
  const la = t.fellDir || 0;
  const kx = -Math.sin(la), kz = Math.cos(la);     // ось вращения
  const co = Math.cos(lean), si = Math.sin(lean);
  const place = (px, py, pz) => {
    const cy = Math.cos(t.yaw), sy = Math.sin(t.yaw);
    let x = px * cy - pz * sy, z = px * sy + pz * cy, y = py;
    if (lean > 0.001) {
      // формула Родрига вокруг горизонтальной оси k = (kx, 0, kz)
      const cross = [-kz * y, kz * x - kx * z, kx * y];
      const dot = kx * x + kz * z;
      const nx = x * co + cross[0] * si + kx * dot * (1 - co);
      const ny = y * co + cross[1] * si;
      const nz = z * co + cross[2] * si + kz * dot * (1 - co);
      x = nx; y = Math.max(ny, 0.22); z = nz;
    }
    return [t.x + x * s, t.y + y * s, t.z + z * s];
  };

  const scorch = 1 - t.burn * 0.72;
  const bark = [0.24 * scorch, 0.185 * scorch, 0.135 * scorch];
  const barkLight = [0.34 * scorch, 0.27 * scorch, 0.20 * scorch];

  // ствол: неровный, к верху тоньше
  const H = 7.5 + R() * 4.5;
  const nodes = [], radii = [];
  for (let i = 0; i <= 5; i++) {
    const u = i / 5;
    nodes.push(place((R() - 0.5) * 0.5 * u, u * H, (R() - 0.5) * 0.5 * u));
    radii.push((0.42 - u * 0.28) * s * (0.85 + R() * 0.3));
  }
  wood.rope(nodes, radii, i => (i > 3 ? barkLight : bark), 7);

  // корневые наплывы
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * TAU + R();
    wood.rope([place(Math.cos(a) * 0.55, 0.02, Math.sin(a) * 0.55), place(0, 1.1, 0)],
              [0.16 * s, 0.30 * s], bark, 5);
  }

  // ветви: от двух третей ствола, каждая раздваивается
  const nb = 5 + ((R() * 3) | 0);
  const crowns = [];
  for (let i = 0; i < nb; i++) {
    const a = (i / nb) * TAU + R() * 0.7;
    const y0 = H * (0.52 + R() * 0.38);
    const len = (1.9 + R() * 1.9);
    const tipX = Math.cos(a) * len, tipZ = Math.sin(a) * len, tipY = y0 + len * (0.55 + R() * 0.5);
    wood.rope([place(0, y0, 0), place(tipX * 0.5, y0 + len * 0.32, tipZ * 0.5), place(tipX, tipY, tipZ)],
              [0.17 * s, 0.11 * s, 0.05 * s], bark, 5);
    crowns.push(place(tipX, tipY, tipZ));
    // раздвоение
    const a2 = a + (R() - 0.5) * 1.2;
    const l2 = len * 0.55;
    const t2 = place(tipX + Math.cos(a2) * l2, tipY + l2 * 0.5, tipZ + Math.sin(a2) * l2);
    wood.rope([place(tipX, tipY, tipZ), t2], [0.05 * s, 0.025 * s], bark, 4);
    crowns.push(t2);
  }
  crowns.push(place(0, H * 1.03, 0));

  // листва: на каждом окончании крест из трёх карт; обгоревшая — чёрная,
  // и на поваленном дереве её остаётся меньше
  const tint = t.burn > 0.5 ? [0.20, 0.16, 0.13] : [1, 1, 1];
  const keep = t.fell > 0.5 ? 0.45 : 1;
  for (const c of crowns) {
    if (R() > keep) continue;
    const rr = (1.5 + R() * 1.1) * s * (t.burn > 0.5 ? 0.72 : 1);
    for (let k = 0; k < 3; k++) {
      const a = (k / 3) * Math.PI + R() * 0.4;
      leaf.card(c[0], c[1], c[2], rr, a, tint, (c[0] + c[2]) * 0.4);
    }
  }
}

/**
 * Ветви и стволы. Свою трубу пишем потому, что общий rope() теряет кольцо
 * на строго вертикальном отрезке — а ствол как раз вертикальный.
 */
function woodBuilder() {
  const m = meshBuilder();
  return {
    rope(nodes, radii, color, sides) {
      const col = typeof color === 'function' ? color : () => color;
      const rings = [];
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[Math.max(0, i - 1)], b = nodes[Math.min(nodes.length - 1, i + 1)];
        let dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
        const dl = Math.hypot(dx, dy, dz) || 1; dx /= dl; dy /= dl; dz /= dl;
        // ось вбок: перпендикуляр к направлению, с запасным вариантом
        let sx = dz, sy = 0, sz = -dx;
        let sl = Math.hypot(sx, sy, sz);
        if (sl < 1e-4) { sx = 1; sy = 0; sz = 0; sl = 1; }
        sx /= sl; sy /= sl; sz /= sl;
        const ux = dy * sz - dz * sy, uy = dz * sx - dx * sz, uz = dx * sy - dy * sx;
        const ring = [];
        for (let k = 0; k < sides; k++) {
          const t = (k / sides) * TAU, c = Math.cos(t) * radii[i], si = Math.sin(t) * radii[i];
          ring.push([nodes[i][0] + sx * c + ux * si,
                     nodes[i][1] + sy * c + uy * si,
                     nodes[i][2] + sz * c + uz * si]);
        }
        rings.push(ring);
      }
      for (let i = 0; i < rings.length - 1; i++) {
        const c = col(i);
        for (let k = 0; k < sides; k++) {
          const j = (k + 1) % sides;
          m.quad(rings[i][k], rings[i + 1][k], rings[i + 1][j], rings[i][j], c);
        }
      }
    },
    raw: m,
  };
}

/** Накопитель для листвы: крест из плоских карт с текстурой. */
function leafBuilder() {
  const pos = [], nrm = [], uv = [], ph = [], col = [], idx = [];
  return {
    card(x, y, z, r, a, tint, phase) {
      const ca = Math.cos(a), sa = Math.sin(a);
      const ux = ca * r, uz = sa * r;
      const base = pos.length / 3;
      const pts = [[x - ux, y - r, z - uz], [x + ux, y - r, z + uz],
                   [x + ux, y + r, z + uz], [x - ux, y + r, z - uz]];
      const n = [-sa, 0.35, ca];
      const nl = Math.hypot(n[0], n[1], n[2]);
      for (let i = 0; i < 4; i++) {
        pos.push(pts[i][0], pts[i][1], pts[i][2]);
        nrm.push(n[0] / nl, n[1] / nl, n[2] / nl);
        col.push(tint[0], tint[1], tint[2]);
        ph.push(phase);
      }
      uv.push(0, 0, 1, 0, 1, 1, 0, 1);
      idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
    },
    pack() {
      return { pos: buffer(new Float32Array(pos)), nrm: buffer(new Float32Array(nrm)),
               uv: buffer(new Float32Array(uv)), phase: buffer(new Float32Array(ph)),
               col: buffer(new Float32Array(col)),
               idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
    },
    count: () => pos.length / 3,
  };
}

function buildTreeChunk(ci) {
  const wood = woodBuilder(), leaf = leafBuilder();
  for (let i = ci * TREE_CHUNK; i < Math.min((ci + 1) * TREE_CHUNK, TREES.length); i++) {
    pushTree(TREES[i], wood, leaf);
  }
  return { wood: wood.raw.pack(), leaf: leaf.pack() };
}

function buildTrees() {
  treeChunks.length = 0;
  for (let c = 0; c * TREE_CHUNK < TREES.length; c++) treeChunks.push(buildTreeChunk(c));
}

/** Пересобрать кусок после того, как деревья в нём обгорели или легли. */
function rebuildTreeChunk(ci) {
  const old = treeChunks[ci];
  if (old) {
    for (const m of [old.wood, old.leaf]) {
      gl.deleteBuffer(m.pos); gl.deleteBuffer(m.nrm); gl.deleteBuffer(m.idx);
      if (m.col) gl.deleteBuffer(m.col);
      if (m.uv) gl.deleteBuffer(m.uv);
      if (m.phase) gl.deleteBuffer(m.phase);
    }
  }
  treeChunks[ci] = buildTreeChunk(ci);
}

/* ---------------- здания: полигон и город ---------------- */

/* Каждое строение — набор блоков. Пока стоит, блоки лежат в статичном
   меше; когда доходит волна, блок отрывается, летит и падает, и здание
   переезжает в динамический буфер. */

const BUILDINGS = [];
let buildingsDirty = true;

function addBuilding(x, z, yaw, parts, tough) {
  BUILDINGS.push({ x, y: gammaMeshH(x, z), z, yaw, parts, tough, hit: 0, t: 0 });
}

function seedBuildings() {
  const R = rngLite(777001);
  const concrete = [0.62, 0.60, 0.57], dark = [0.40, 0.39, 0.37], rust = [0.45, 0.28, 0.20];
  const glass = [0.30, 0.40, 0.48], panel = [0.55, 0.53, 0.50];

  // — мишенное поле: коробки, башни, ангар, труба
  const ring = [140, 320, 560, 820];
  for (let k = 0; k < ring.length; k++) {
    const n = 3 + k;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * TAU + k * 0.5;
      const x = G.zero.x + Math.cos(a) * ring[k], z = G.zero.z + Math.sin(a) * ring[k];
      const kind = (R() * 3) | 0;
      const parts = [];
      if (kind === 0) {                       // жилая коробка в три этажа
        for (let f = 0; f < 3; f++) {
          parts.push({ dx: 0, dy: 1.6 + f * 3.2, dz: 0, hx: 5.2, hy: 1.6, hz: 4.2,
                       col: f % 2 ? panel : concrete });
        }
        parts.push({ dx: 0, dy: 11.2, dz: 0, hx: 5.6, hy: 0.3, hz: 4.6, col: dark });
      } else if (kind === 1) {                // башня с площадкой
        for (let f = 0; f < 5; f++) {
          parts.push({ dx: 0, dy: 2 + f * 4, dz: 0, hx: 2.1 - f * 0.15, hy: 2, hz: 2.1 - f * 0.15,
                       col: f % 2 ? concrete : dark });
        }
        parts.push({ dx: 0, dy: 22.5, dz: 0, hx: 3.4, hy: 0.5, hz: 3.4, col: rust });
      } else {                                // ангар с воротами
        parts.push({ dx: 0, dy: 2.4, dz: 0, hx: 8.5, hy: 2.4, hz: 5.5, col: concrete });
        parts.push({ dx: 0, dy: 5.6, dz: 0, hx: 8.7, hy: 0.8, hz: 5.7, col: dark });
        parts.push({ dx: -8.6, dy: 1.9, dz: 0, hx: 0.3, hy: 1.9, hz: 2.6, col: rust });
      }
      addBuilding(x, z, R() * TAU, parts, 0.55 + R() * 0.5);
    }
  }
  // труба у эпицентра — заметный ориентир
  {
    const parts = [];
    for (let f = 0; f < 9; f++) {
      parts.push({ dx: 0, dy: 2.5 + f * 5, dz: 0, hx: 1.9 - f * 0.11, hy: 2.5, hz: 1.9 - f * 0.11,
                   col: f % 2 ? rust : concrete });
    }
    addBuilding(G.zero.x + 60, G.zero.z - 40, 0, parts, 0.4);
  }

  // — город: кварталы вдоль улиц
  const CB = 8;
  for (let gx = -CB; gx <= CB; gx++) {
    for (let gz = -CB; gz <= CB; gz++) {
      if ((gx + 100) % 2 === 0 || (gz + 100) % 2 === 0) continue;   // улицы
      const bx = G.city.x + gx * 62 + (R() - 0.5) * 8;
      const bz = G.city.z + gz * 62 + (R() - 0.5) * 8;
      const dist = Math.hypot(gx, gz);
      if (dist > CB) continue;
      const floors = Math.round(3 + (CB - dist) * 1.7 + R() * 5);
      const w = 9 + R() * 8, d = 9 + R() * 8;
      const parts = [];
      for (let f = 0; f < floors; f++) {
        parts.push({ dx: 0, dy: 1.75 + f * 3.5, dz: 0, hx: w, hy: 1.75, hz: d,
                     col: f % 3 === 1 ? glass : (R() < 0.5 ? concrete : panel) });
      }
      parts.push({ dx: 0, dy: floors * 3.5 + 0.4, dz: 0, hx: w + 0.5, hy: 0.4, hz: d + 0.5, col: dark });
      addBuilding(bx, bz, 0, parts, 1.1 + R() * 0.6);
    }
  }
}
seedBuildings();

/* Динамический буфер под все блоки: пересобираем только когда что-то шевелится. */
const bldBuf = (() => {
  let total = 0;
  for (const b of BUILDINGS) total += b.parts.length;
  return {
    total,
    pos: new Float32Array(total * 24 * 3),
    nrm: new Float32Array(total * 24 * 3),
    col: new Float32Array(total * 24 * 3),
    idx: new Uint16Array(0),
    gPos: gl.createBuffer(), gNrm: gl.createBuffer(), gCol: gl.createBuffer(),
    gIdx: gl.createBuffer(), count: 0, chunks: [],
  };
})();

/* Блоков много: индексы разложены по кускам не длиннее 65 000 вершин. */
(() => {
  const perChunk = Math.floor(65000 / 24);
  const chunks = [];
  for (let start = 0; start < bldBuf.total; start += perChunk) {
    const n = Math.min(perChunk, bldBuf.total - start);
    const idx = new Uint16Array(n * 36);
    const face = [0, 1, 2, 0, 2, 3];
    for (let p = 0; p < n; p++) {
      for (let f = 0; f < 6; f++) {
        for (let k = 0; k < 6; k++) idx[(p * 6 + f) * 6 + k] = p * 24 + f * 4 + face[k];
      }
    }
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buf);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
    chunks.push({ start, n, idx: buf, count: n * 36 });
  }
  bldBuf.chunks = chunks;
})();

/** Кладёт коробку с поворотом по трём осям в общий массив. */
function writeBox(o, cx, cy, cz, hx, hy, hz, yaw, tilt, axis, col) {
  const cy1 = Math.cos(yaw), sy1 = Math.sin(yaw);
  const ct = Math.cos(tilt), st = Math.sin(tilt);
  const ax = Math.cos(axis), az = Math.sin(axis);
  const P = (x, y, z) => {
    let px = x * cy1 - z * sy1, pz = x * sy1 + z * cy1, py = y;
    if (tilt !== 0) {
      const along = px * ax + pz * az, perp = -px * az + pz * ax;
      const na = along * ct + py * st, ny = -along * st + py * ct;
      px = na * ax - perp * az; pz = na * az + perp * ax; py = ny;
    }
    return [cx + px, cy + py, cz + pz];
  };
  const v = [P(-hx,-hy,-hz), P(hx,-hy,-hz), P(hx,hy,-hz), P(-hx,hy,-hz),
             P(-hx,-hy,hz), P(hx,-hy,hz), P(hx,hy,hz), P(-hx,hy,hz)];
  const faces = [[0,1,2,3], [5,4,7,6], [4,0,3,7], [1,5,6,2], [3,2,6,7], [4,5,1,0]];
  let k = o * 24 * 3;
  for (const f of faces) {
    const a = v[f[0]], b = v[f[1]], c = v[f[2]];
    let nx = (b[1]-a[1])*(c[2]-a[2]) - (b[2]-a[2])*(c[1]-a[1]);
    let ny = (b[2]-a[2])*(c[0]-a[0]) - (b[0]-a[0])*(c[2]-a[2]);
    let nz = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl; ny /= nl; nz /= nl;
    for (const i of f) {
      bldBuf.pos[k] = v[i][0]; bldBuf.pos[k+1] = v[i][1]; bldBuf.pos[k+2] = v[i][2];
      bldBuf.nrm[k] = nx; bldBuf.nrm[k+1] = ny; bldBuf.nrm[k+2] = nz;
      bldBuf.col[k] = col[0]; bldBuf.col[k+1] = col[1]; bldBuf.col[k+2] = col[2];
      k += 3;
    }
  }
}

function rebuildBuildings() {
  let o = 0;
  for (const b of BUILDINGS) {
    for (const p of b.parts) {
      const dark = 1 - (p.fall ? 0.30 : 0) - b.hit * 0.18;
      const col = [p.col[0] * dark, p.col[1] * dark, p.col[2] * dark];
      const px = b.x + (p.ox || 0), py = b.y + p.dy + (p.oy || 0), pz = b.z + (p.oz || 0);
      writeBox(o++, px + p.dx, py, pz + p.dz, p.hx, p.hy, p.hz,
               b.yaw + (p.spin || 0), p.tilt || 0, p.axis || 0, col);
    }
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, bldBuf.gPos);
  gl.bufferData(gl.ARRAY_BUFFER, bldBuf.pos, gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, bldBuf.gNrm);
  gl.bufferData(gl.ARRAY_BUFFER, bldBuf.nrm, gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, bldBuf.gCol);
  gl.bufferData(gl.ARRAY_BUFFER, bldBuf.col, gl.DYNAMIC_DRAW);
  buildingsDirty = false;
}

/**
 * Волна дошла до здания: чем ближе к эпицентру и чем оно хлипче, тем
 * больше блоков срывает. Сорванный блок летит от взрыва и падает.
 */
function shockBuilding(b, power) {
  b.hit = Math.max(b.hit, clamp(power, 0, 1));
  const dirx = b.x - BLAST.pos[0], dirz = b.z - BLAST.pos[2];
  const dl = Math.hypot(dirx, dirz) || 1;
  const nx = dirx / dl, nz = dirz / dl;
  let any = false;
  for (let i = 0; i < b.parts.length; i++) {
    const p = b.parts[i];
    if (p.fall) continue;
    // верхние этажи срывает первыми
    const share = power * (0.35 + 0.75 * (i / Math.max(b.parts.length - 1, 1)));
    if (share < 0.42) continue;
    const kick = 5 + power * 26;
    p.fall = true; any = true;
    p.vx = nx * kick * (0.5 + Math.random()) + (Math.random() - 0.5) * 5;
    p.vz = nz * kick * (0.5 + Math.random()) + (Math.random() - 0.5) * 5;
    p.vy = 2 + Math.random() * power * 16;
    p.vt = (Math.random() - 0.5) * 2.4;      // угловая скорость наклона
    p.vs = (Math.random() - 0.5) * 2.0;
    p.axis = Math.random() * TAU;
    p.tilt = 0; p.spin = 0; p.ox = 0; p.oy = 0; p.oz = 0;
    p.rest = false;
  }
  if (any) {
    // пыль от рассыпающейся коробки
    for (let i = 0; i < 10; i++) {
      spawnPuff(b.x + (Math.random() - 0.5) * 18, b.y + Math.random() * 14, b.z + (Math.random() - 0.5) * 18,
        nx * 12 + (Math.random() - 0.5) * 8, 3 + Math.random() * 7, nz * 12 + (Math.random() - 0.5) * 8,
        6 + Math.random() * 8, 5, 6 + Math.random() * 4, [0.52, 0.49, 0.45], 0, 0.6, 0.5);
    }
  }
  return any;
}

/** Полёт и приземление сорванных блоков. */
function updateBuildings(dt) {
  let moving = false;
  for (const b of BUILDINGS) {
    for (const p of b.parts) {
      if (!p.fall || p.rest) continue;
      moving = true;
      p.vy -= 22 * dt;
      p.ox = (p.ox || 0) + p.vx * dt;
      p.oy = (p.oy || 0) + p.vy * dt;
      p.oz = (p.oz || 0) + p.vz * dt;
      p.tilt = (p.tilt || 0) + p.vt * dt;
      p.spin = (p.spin || 0) + p.vs * dt;
      const floor = gammaMeshH(b.x + p.dx + p.ox, b.z + p.dz + p.oz) - b.y + p.hy * 0.8;
      if (b.y + p.dy + p.oy <= b.y + floor) {
        p.oy = floor - p.dy;
        p.vx *= 0.28; p.vz *= 0.28; p.vy *= -0.16; p.vt *= 0.2; p.vs *= 0.2;
        if (Math.abs(p.vy) < 1.2) { p.rest = true; p.vy = 0; }
      }
    }
  }
  if (moving) buildingsDirty = true;
  return moving;
}

/* ---------------- золотой бассейн ---------------- */

function buildPool() {
  const m = meshBuilder();
  const P = G.pool;
  const gold = [1.00, 0.78, 0.24], goldDark = [0.60, 0.44, 0.11], goldLit = [1.00, 0.94, 0.62];
  const top = G.flat + 0.22;         // копинг чуть выше газона
  const bot = G.flat - 3.6;          // дно чаши
  const W = P.w, D = P.d, r = P.rim;
  // копинг: плоская золотая рама вокруг чаши
  m.box(P.x, top - 0.11, P.z - D - r / 2, W + r, 0.11, r / 2, 0, goldLit);
  m.box(P.x, top - 0.11, P.z + D + r / 2, W + r, 0.11, r / 2, 0, goldLit);
  m.box(P.x - W - r / 2, top - 0.11, P.z, r / 2, 0.11, D + r, 0, goldLit);
  m.box(P.x + W + r / 2, top - 0.11, P.z, r / 2, 0.11, D + r, 0, goldLit);
  // стенки чаши
  const wallH = (top - bot) / 2, wallY = (top + bot) / 2;
  m.box(P.x, wallY, P.z - D + 0.12, W, wallH, 0.12, 0, gold);
  m.box(P.x, wallY, P.z + D - 0.12, W, wallH, 0.12, 0, gold);
  m.box(P.x - W + 0.12, wallY, P.z, 0.12, wallH, D, 0, gold);
  m.box(P.x + W - 0.12, wallY, P.z, 0.12, wallH, D, 0, gold);
  // дно
  m.box(P.x, bot + 0.08, P.z, W, 0.08, D, 0, goldDark);
  // лесенка в углу
  for (let i = 0; i < 5; i++) {
    m.box(P.x + W - 2.6, top - 0.45 - i * 0.62, P.z + D - 1.6, 1.4, 0.08, 0.34, 0, goldLit);
  }
  // трамплин
  m.box(P.x - W - 3.2, top + 1.35, P.z, 3.2, 0.14, 1.1, 0, goldLit);
  m.box(P.x - W - 1.6, top + 0.68, P.z, 0.20, 0.68, 0.20, 0, goldDark);
  // лежаки вдоль бортика
  for (let i = -3; i <= 3; i++) {
    m.box(P.x + i * 16, top + 0.42, P.z + D + r + 3.6, 1.1, 0.10, 2.2, 0, [0.88, 0.86, 0.82]);
    m.box(P.x + i * 16, top + 0.78, P.z + D + r + 5.1, 1.1, 0.46, 0.11, 0.35, [0.88, 0.86, 0.82]);
  }
  return m.pack();
}

/** Плоскость воды бассейна — тот же шейдер, что и у моря. */
function buildPoolWater() {
  const P = G.pool, y = G.flat - 0.30;
  const pos = [], idx = [];
  const N = 18;
  for (let i = 0; i <= N; i++) {
    for (let j = 0; j <= N; j++) {
      pos.push(P.x - P.w + (2 * P.w) * i / N, y, P.z - P.d + (2 * P.d) * j / N);
    }
  }
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      const a = i * (N + 1) + j, b = a + N + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return { pos: buffer(new Float32Array(pos)),
           idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
}

/* ---------------- машина ---------------- */

const CAR = {
  x: G.car.x, z: G.car.z, y: 0, yaw: -0.8,
  speed: 0, steer: 0, inside: false, auto: 0,   // auto: 0 нет, 1 в город, -1 к площадке
  pedal: { gas: 0, brake: 0, left: 0, right: 0 },   // экранные кнопки
};

/** Щиток и руль — то, что видно с водительского места. */
function buildCarDash() {
  const m = meshBuilder();
  const dash = [0.14, 0.13, 0.14], trim = [0.55, 0.12, 0.10], chrome = [0.72, 0.72, 0.76];
  // щиток ниже линии взгляда, иначе он занимает пол-экрана на телефоне
  m.box(0, 0.94, -0.82, 0.80, 0.13, 0.22, 0, dash);
  m.box(0, 1.06, -0.92, 0.80, 0.04, 0.09, 0, trim);
  // руль
  const cx = -0.34, cy = 0.99, cz = -0.50;
  const ring = [];
  for (let i = 0; i <= 14; i++) {
    const a = (i / 14) * TAU;
    ring.push([cx + Math.cos(a) * 0.17, cy + Math.sin(a) * 0.17 * 0.82, cz + Math.sin(a) * 0.17 * 0.30]);
  }
  m.rope(ring, ring.map(() => 0.022), dash, 5);
  m.box(cx, cy, cz, 0.05, 0.05, 0.03, 0, chrome);
  // приборы
  for (const s of [-0.06, 0.06]) m.box(cx + s * 1.6, 1.02, cz - 0.20, 0.05, 0.04, 0.02, 0, [0.30, 0.60, 0.55]);
  return m.pack();
}

function buildCar() {
  const m = meshBuilder();
  const body = [0.66, 0.13, 0.10], bodyDark = [0.42, 0.09, 0.07];
  const glass = [0.16, 0.22, 0.28], chrome = [0.80, 0.80, 0.84], tyre = [0.10, 0.10, 0.11];
  // кузов: низ, капот, крыша
  m.box(0, 0.62, 0, 0.95, 0.30, 2.30, 0, body);
  m.box(0, 0.95, -0.95, 0.90, 0.16, 1.30, 0, bodyDark);
  m.box(0, 1.22, 0.10, 0.82, 0.42, 1.05, 0, glass);
  m.box(0, 1.52, 0.10, 0.86, 0.06, 1.10, 0, body);
  // бамперы и фары
  m.box(0, 0.55, -2.34, 0.94, 0.16, 0.10, 0, chrome);
  m.box(0, 0.55, 2.34, 0.94, 0.16, 0.10, 0, chrome);
  for (const s of [-1, 1]) {
    m.box(s * 0.62, 0.78, -2.28, 0.24, 0.14, 0.06, 0, [1.0, 0.96, 0.80]);
    m.box(s * 0.62, 0.72, 2.30, 0.20, 0.10, 0.06, 0, [0.72, 0.10, 0.08]);
  }
  // колёса
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      const cx = sx * 0.92, cz = sz * 1.45;
      for (let i = 0; i < 10; i++) {
        const a0 = (i / 10) * TAU, a1 = ((i + 1) / 10) * TAU;
        const R = 0.42, W = 0.16;
        const A = [cx - sx * W, 0.42 + Math.sin(a0) * R, cz + Math.cos(a0) * R];
        const B = [cx - sx * W, 0.42 + Math.sin(a1) * R, cz + Math.cos(a1) * R];
        const C = [cx + sx * W, 0.42 + Math.sin(a1) * R, cz + Math.cos(a1) * R];
        const D = [cx + sx * W, 0.42 + Math.sin(a0) * R, cz + Math.cos(a0) * R];
        m.quad(A, B, C, D, tyre);
        m.tri([cx + sx * W, 0.42, cz], C, D, chrome);
      }
    }
  }
  return m.pack();
}

/** Автомобиль: газ, руль, сцепление с землёй и автопилот по дороге. */
function updateCar(dt) {
  if (game.world !== 'gamma') return;
  const c = CAR;
  if (c.inside) {
    let gas = 0, turn = 0;
    if (keys.KeyW || keys.ArrowUp) gas += 1;
    if (keys.KeyS || keys.ArrowDown) gas -= 1;
    if (keys.KeyD || keys.ArrowRight) turn += 1;
    if (keys.KeyA || keys.ArrowLeft) turn -= 1;
    gas += -stick.dy; turn += stick.dx;
    // экранные педали: работают и пальцем, и мышью
    gas += CAR.pedal.gas - CAR.pedal.brake;
    turn += CAR.pedal.right - CAR.pedal.left;
    gas = clamp(gas, -1, 1); turn = clamp(turn, -1, 1);

    if (c.auto !== 0) {
      // автопилот ведёт по прямой к цели и сам тормозит на подъезде
      const tx = c.auto > 0 ? G.city.x : PAD.x, tz = c.auto > 0 ? G.city.z : PAD.z;
      const dx = tx - c.x, dz = tz - c.z;
      const dist = Math.hypot(dx, dz);
      const want = Math.atan2(dx, -dz);
      let diff = want - c.yaw;
      while (diff > Math.PI) diff -= TAU;
      while (diff < -Math.PI) diff += TAU;
      turn = clamp(diff * 2.2, -1, 1);
      gas = dist > 220 ? 1 : -0.7;
      if (dist < 40) { c.auto = 0; c.speed *= 0.3; toast('Приехали'); syncCarUI(); }
    }

    const maxSpeed = 64;
    // педаль тормоза против движения гасит куда резче, чем задний ход
    const braking = gas < 0 && c.speed > 0.5;
    c.speed += gas * (braking ? 62 : 26) * dt;
    c.speed *= Math.exp(-(0.42 + Math.abs(c.steer) * 0.9) * dt);
    c.speed = clamp(c.speed, -14, maxSpeed);
    c.steer = damp(c.steer, turn, 6, dt);
    c.yaw += c.steer * dt * 1.9 * clamp(Math.abs(c.speed) / 8, 0, 1) * Math.sign(c.speed || 1);
    c.x += Math.sin(c.yaw) * c.speed * dt;
    c.z += -Math.cos(c.yaw) * c.speed * dt;
    const lim = G.R * 0.95;
    const rr = Math.hypot(c.x, c.z);
    if (rr > lim) { c.x *= lim / rr; c.z *= lim / rr; c.speed *= 0.2; }
    // в воду не заезжаем
    if (gammaMeshH(c.x, c.z) < G.sea + 1.2) {
      c.x -= Math.sin(c.yaw) * c.speed * dt * 1.2;
      c.z += Math.cos(c.yaw) * c.speed * dt * 1.2;
      c.speed *= -0.15;
    }
  } else {
    c.speed = damp(c.speed, 0, 3, dt);
  }
  c.y = gammaMeshH(c.x, c.z);
  if (c.inside) {
    // камера водителя: чуть слева и сзади от центра салона
    const s = Math.sin(c.yaw), co = Math.cos(c.yaw);
    cam.x = c.x - s * 0.25 - co * 0.34;
    cam.z = c.z + co * 0.25 - s * 0.34;
    cam.y = c.y + 1.62;
  }
}

function carMatrix(out) {
  const c = CAR;
  const hx = gammaMeshH(c.x + Math.sin(c.yaw) * 2, c.z - Math.cos(c.yaw) * 2)
           - gammaMeshH(c.x - Math.sin(c.yaw) * 2, c.z + Math.cos(c.yaw) * 2);
  m4compose(out, c.x, c.y, c.z, c.yaw, Math.atan2(hx, 4), 0, 1);
  return out;
}

function carBoard() {
  if (game.world !== 'gamma' || game.rocket.inside) return false;
  if (CAR.inside) return false;
  if (Math.hypot(cam.x - CAR.x, cam.z - CAR.z) > 4.5) return false;
  CAR.inside = true;
  game.carFrom = [cam.x, cam.z];
  carSoundStart();
  toast('За рулём. W/S — газ и тормоз, A/D — руль');
  syncCarUI();
  return true;
}

function carExit() {
  if (!CAR.inside) return;
  CAR.inside = false;
  CAR.auto = 0;
  CAR.pedal.gas = CAR.pedal.brake = CAR.pedal.left = CAR.pedal.right = 0;
  carSoundStop();
  cam.x = CAR.x + Math.cos(CAR.yaw) * 2.6;
  cam.z = CAR.z + Math.sin(CAR.yaw) * 2.6;
  cam.y = gammaMeshH(cam.x, cam.z) + 1.66;
  toast('Вышли из машины');
  syncCarUI();
}

function syncCarUI() {
  const panel = document.getElementById('car-panel');
  if (!panel) return;
  panel.classList.toggle('show', CAR.inside);
  document.getElementById('app').classList.toggle('driving', CAR.inside);
  const info = document.getElementById('car-info');
  if (info && CAR.inside) {
    const toCity = Math.hypot(G.city.x - CAR.x, G.city.z - CAR.z);
    const back = CAR.speed < -0.5 ? ' назад' : '';
    info.textContent = `${Math.round(Math.abs(CAR.speed) * 3.6)} км/ч${back} · до города ${(toCity / 1000).toFixed(2)} км`
      + (CAR.auto ? ' · автопилот' : '');
  }
  const auto = document.getElementById('car-auto');
  if (auto) {
    const inCity = Math.hypot(CAR.x - G.city.x, CAR.z - G.city.z) < 700;
    auto.textContent = CAR.auto ? 'Автопилот: выкл' : (inCity ? 'К площадке' : 'В город');
  }
}

/* ---------------- сборка и отрисовка мира Гаммы ---------------- */

/* Ландшафт, роща и кварталы стоят дорого, поэтому собираем их при первом
   появлении на планете, а не на старте сцены. */
let GA = null;

function gammaAssets() {
  if (GA) return GA;
  buildTrees();
  GA = {
    terrain: buildGammaTerrain(),
    sea: buildSea(),
    roads: buildRoads(),
    pool: buildPool(),
    poolWater: buildPoolWater(),
    car: buildCar(),
    dash: buildCarDash(),
    sith: buildSith(),
    blade: buildBlade(),
    soil: texture(makeSoilTexture(), { wrap: gl.REPEAT }),
    grass: texture(makeGrassTexture(), { mips: true }),
    leaf: texture(makeLeafTexture(), { mips: true }),
  };
  rebuildBuildings();
  return GA;
}

/** Всё, что стоит на Гамме: море, бассейн, кварталы, роща, трава, машина, советник. */
function drawGamma(vp, eye, f, fogK) {
  const A = gammaAssets();
  const model = m4();

  // — море и вода бассейна
  gl.useProgram(seaProg.prog);
  gl.uniformMatrix4fv(seaProg.u.uVP, false, vp);
  gl.uniform3fv(seaProg.u.uCam, eye);
  gl.uniform3fv(seaProg.u.uSun, SUN);
  gl.uniform3fv(seaProg.u.uHaze, HAZE);
  gl.uniform3fv(seaProg.u.uLight, LIGHT);
  gl.uniform3fv(seaProg.u.uAmb, AMB);
  gl.uniform1f(seaProg.u.uTime, game.time);
  gl.uniform1f(seaProg.u.uFogK, fogK);
  gl.uniform1f(seaProg.u.uShallow, 0.35);
  attrib(seaProg.a.aPos, A.sea.pos, 3);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, A.sea.idx);
  gl.drawElements(gl.TRIANGLES, A.sea.count, gl.UNSIGNED_SHORT, 0);
  gl.uniform1f(seaProg.u.uShallow, 1.0);
  attrib(seaProg.a.aPos, A.poolWater.pos, 3);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, A.poolWater.idx);
  gl.drawElements(gl.TRIANGLES, A.poolWater.count, gl.UNSIGNED_SHORT, 0);

  // — сплошная геометрия: бассейн, машина, кварталы, стволы
  gl.useProgram(solidProg.prog);
  gl.uniformMatrix4fv(solidProg.u.uVP, false, vp);
  gl.uniform3fv(solidProg.u.uSun, SUN);
  gl.uniform3fv(solidProg.u.uHaze, HAZE);
  gl.uniform3fv(solidProg.u.uLight, LIGHT);
  gl.uniform3fv(solidProg.u.uAmb, AMB);
  gl.uniform3fv(solidProg.u.uCam, eye);
  gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
  gl.uniform1f(solidProg.u.uFogK, fogK);
  const solid = (mesh, mat) => {
    gl.uniformMatrix4fv(solidProg.u.uModel, false, mat || m4identity(model));
    attrib(solidProg.a.aPos, mesh.pos, 3);
    attrib(solidProg.a.aNormal, mesh.nrm, 3);
    attrib(solidProg.a.aColor, mesh.col, 3);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.idx);
    gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
  };
  solid(A.roads);
  solid(A.pool);
  solid(CAR.inside ? A.dash : A.car, carMatrix(model));
  solid(A.sith, SITH.model);

  // кварталы: один общий буфер, пересобираем только когда что-то падает
  if (buildingsDirty) rebuildBuildings();
  gl.uniformMatrix4fv(solidProg.u.uModel, false, m4identity(model));
  for (const ch of bldBuf.chunks) {
    const off = ch.start * 24 * 12;
    attrib(solidProg.a.aPos, bldBuf.gPos, 3, 0, off);
    attrib(solidProg.a.aNormal, bldBuf.gNrm, 3, 0, off);
    attrib(solidProg.a.aColor, bldBuf.gCol, 3, 0, off);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ch.idx);
    gl.drawElements(gl.TRIANGLES, ch.count, gl.UNSIGNED_SHORT, 0);
  }
  for (const c of treeChunks) solid(c.wood);

  // — клинок советника: аддитивное свечение поверх
  if (SITH.saber > 0.02) {
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.depthMask(false);
    gl.useProgram(flatProg.prog);
    gl.uniformMatrix4fv(flatProg.u.uVP, false, vp);
    gl.uniformMatrix4fv(flatProg.u.uModel, false, SITH.model);
    gl.uniform4f(flatProg.u.uColor, 1.0, 0.16, 0.10, SITH.saber);
    attrib(flatProg.a.aPos, A.blade.pos, 3);
    attrib(flatProg.a.aFade, A.blade.fade, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, A.blade.idx);
    gl.drawElements(gl.TRIANGLES, A.blade.count, gl.UNSIGNED_SHORT, 0);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
  }

  // — листва и трава: карты с прозрачностью
  gl.useProgram(foliageProg.prog);
  gl.uniformMatrix4fv(foliageProg.u.uVP, false, vp);
  gl.uniform3fv(foliageProg.u.uSun, SUN);
  gl.uniform3fv(foliageProg.u.uHaze, HAZE);
  gl.uniform3fv(foliageProg.u.uLight, LIGHT);
  gl.uniform3fv(foliageProg.u.uAmb, AMB);
  gl.uniform3fv(foliageProg.u.uCam, eye);
  gl.uniform1f(foliageProg.u.uTime, game.time);
  gl.uniform1f(foliageProg.u.uFogK, fogK);
  gl.uniform3f(foliageProg.u.uTint, 1, 1, 1);
  gl.uniform1f(foliageProg.u.uSway, game.reduced ? 0.004 : 0.02);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, A.leaf);
  gl.uniform1i(foliageProg.u.uTex, 0);
  for (const c of treeChunks) {
    attrib(foliageProg.a.aPos, c.leaf.pos, 3);
    attrib(foliageProg.a.aNormal, c.leaf.nrm, 3);
    attrib(foliageProg.a.aUv, c.leaf.uv, 2);
    attrib(foliageProg.a.aPhase, c.leaf.phase, 1);
    attrib(foliageProg.a.aColor, c.leaf.col, 3);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, c.leaf.idx);
    gl.drawElements(gl.TRIANGLES, c.leaf.count, gl.UNSIGNED_SHORT, 0);
  }
  if (grass.n > 0) {
    gl.bindTexture(gl.TEXTURE_2D, A.grass);
    gl.useProgram(grassProg.prog);
    gl.uniformMatrix4fv(grassProg.u.uVP, false, vp);
    gl.uniform3fv(grassProg.u.uSun, SUN);
    gl.uniform3fv(grassProg.u.uHaze, HAZE);
    gl.uniform3fv(grassProg.u.uLight, LIGHT);
    gl.uniform3fv(grassProg.u.uAmb, AMB);
    gl.uniform3fv(grassProg.u.uCam, eye);
    gl.uniform3fv(grassProg.u.uRight, [Math.cos(cam.yaw), 0, Math.sin(cam.yaw)]);
    gl.uniform1f(grassProg.u.uTime, game.time);
    gl.uniform1f(grassProg.u.uFogK, fogK);
    gl.uniform1i(grassProg.u.uTex, 0);
    attrib(grassProg.a.aCenter, grass.gCenter, 3);
    attrib(grassProg.a.aCorner, grass.gCorner, 2);
    attrib(grassProg.a.aUv, grass.gUv, 2);
    attrib(grassProg.a.aPhase, grass.gPhase, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, grass.gIdx);
    gl.drawElements(gl.TRIANGLES, grass.n * 6, gl.UNSIGNED_SHORT, 0);
  }
}

/* Трава: билборд, развёрнутый к камере, с покачиванием у верхушки. */
const grassProg = program(`
attribute vec3 aCenter;
attribute vec2 aCorner;
attribute vec2 aUv;
attribute float aPhase;
uniform mat4 uVP;
uniform vec3 uRight;
uniform float uTime;
varying vec2 vUv;
varying vec3 vW;
void main() {
  vec3 p = aCenter + uRight * aCorner.x + vec3(0.0, aCorner.y, 0.0);
  float s = sin(uTime * 1.9 + aPhase) + 0.5 * sin(uTime * 3.7 + aPhase * 1.7);
  p.xz += s * 0.06 * max(aCorner.y, 0.0);
  vUv = aUv; vW = p;
  gl_Position = uVP * vec4(p, 1.0);
}`, PRECISION + `
varying vec2 vUv;
varying vec3 vW;
uniform sampler2D uTex;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform vec3 uCam;
uniform float uFogK;
void main() {
  vec4 t = texture2D(uTex, vUv);
  if (t.a < 0.40) discard;
  float d = length(uCam - vW);
  if (d > 62.0) discard;              // дальше пучки всё равно в пиксель
  vec3 col = t.rgb * (0.62 * uAmb + 0.72 * uLight * max(uSun.y, 0.12));
  col = mix(col, uHaze, 1.0 - exp(-pow(d * uFogK, 2.0)));
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---------------- дорога и улицы ---------------- */

/**
 * Полотно от площадки к городу и сетка улиц в городе. Лента идёт по
 * рельефу с небольшим подъёмом над грунтом, поэтому не тонет в холмах.
 */
function buildRoads() {
  const pos = [], nrm = [], col = [], idx = [];
  const asphalt = [0.115, 0.112, 0.118];
  const worn = [0.155, 0.150, 0.152];
  const mark = [0.72, 0.68, 0.42];

  const strip = (x0, z0, x1, z1, half, color, dash, seg) => {
    const dx = x1 - x0, dz = z1 - z0;
    const len = Math.hypot(dx, dz);
    const ux = dx / len, uz = dz / len;
    const px = -uz, pz = ux;                  // поперёк полотна
    const steps = Math.max(2, Math.round(len / (seg || 24)));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const cx = x0 + dx * t, cz = z0 + dz * t;
      for (const s of [-1, 1]) {
        const vx = cx + px * half * s, vz = cz + pz * half * s;
        pos.push(vx, gammaMeshH(vx, vz) + 0.10, vz);
        nrm.push(0, 1, 0);
        // колея темнее по центру, обочина светлее
        const c = dash ? color : (Math.abs(s) > 0 ? color : worn);
        col.push(c[0], c[1], c[2]);
      }
    }
    const base = pos.length / 3 - (steps + 1) * 2;
    for (let i = 0; i < steps; i++) {
      if (dash && i % 2 === 1) continue;       // прерывистая разметка
      const a = base + i * 2;
      idx.push(a, a + 1, a + 3, a, a + 3, a + 2);
    }
  };

  // магистраль до города
  strip(PAD.x, PAD.z, G.city.x, G.city.z, 7.5, asphalt, false);
  strip(PAD.x, PAD.z, G.city.x, G.city.z, 0.22, mark, true, 5);   // штрихи по пять метров

  // улицы города: по чётным линиям сетки, там где нет кварталов
  const CB = 8, step = 62;
  for (let g = -CB; g <= CB; g++) {
    if ((g + 100) % 2 !== 0) continue;
    const span = step * CB;
    strip(G.city.x + g * step, G.city.z - span, G.city.x + g * step, G.city.z + span, 7, asphalt, false);
    strip(G.city.x - span, G.city.z + g * step, G.city.x + span, G.city.z + g * step, 7, asphalt, false);
  }
  // съезд к бассейну
  strip(PAD.x, PAD.z, G.pool.x + G.pool.w + 8, G.pool.z, 4.5, asphalt, false);

  return { pos: buffer(new Float32Array(pos)), nrm: buffer(new Float32Array(nrm)),
           col: buffer(new Float32Array(col)),
           idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
}
