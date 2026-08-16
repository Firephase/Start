/* ============================================================
   Чёрная дыра, ветряк и поилка
   ============================================================ */

/** Чёрная дыра висит за фигурами. */
const BH = {
  pos: [-17, 4.6, -40],
  rs: 2.15,        // радиус тени, метры
  rg: 12.0,        // гравитационный радиус для формулы замедления времени
  maxDil: 20,      // предел, до которого пускаем разойтись часам
};
// Барьер стоит ровно там, где множитель достигает предела: упёршись в него,
// вы стоите при ×20, а не проскакиваете точку.
BH.block = BH.rg / (1 - 1 / (BH.maxDil * BH.maxDil));

/** Коэффициент, во сколько раз далёкие часы идут быстрее наших. */
function dilationAt(x, y, z) {
  const r = Math.max(Math.hypot(x - BH.pos[0], y - BH.pos[1], z - BH.pos[2]), BH.block);
  // пол под корнем задаётся пределом: иначе он сам режет множитель раньше времени
  const floor = 1 / (BH.maxDil * BH.maxDil);
  const f = 1 / Math.sqrt(Math.max(floor, 1 - BH.rg / r));
  return Number.isFinite(f) ? Math.min(BH.maxDil, Math.max(1, f)) : 1;
}

/** Ветряк и круглый бак с водой. */
const MILL = { x: 24, z: -25, h: 6.4, facing: 0.62 };
MILL.y = terrainH(MILL.x, MILL.z);
const TANK = { x: MILL.x + 3.4, z: MILL.z + 1.6, r: 1.75, h: 0.86 };
TANK.y = terrainH(TANK.x, TANK.z);
TANK.top = TANK.y + TANK.h - 0.14;

/* ---------------- статичные части ---------------- */

function addWindmill(api) {
  const { pushTri } = api;
  const R = rng(31337);

  /** Прямоугольный брус между двумя точками. */
  function beam(a, b, w, color) {
    const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    const len = Math.hypot(dx, dy, dz) || 1;
    const ax = [dx / len, dy / len, dz / len];
    // два поперечных орта
    let up = Math.abs(ax[1]) > 0.9 ? [1, 0, 0] : [0, 1, 0];
    let s1 = [ax[1] * up[2] - ax[2] * up[1], ax[2] * up[0] - ax[0] * up[2], ax[0] * up[1] - ax[1] * up[0]];
    const l1 = Math.hypot(...s1) || 1; s1 = s1.map((v) => (v / l1) * w);
    let s2 = [ax[1] * s1[2] - ax[2] * s1[1], ax[2] * s1[0] - ax[0] * s1[2], ax[0] * s1[1] - ax[1] * s1[0]];
    const l2 = Math.hypot(...s2) || 1; s2 = s2.map((v) => (v / l2) * w);

    const q = [];
    for (const p of [a, b]) {
      for (const [i, j] of [[1, 1], [-1, 1], [-1, -1], [1, -1]]) {
        q.push([p[0] + s1[0] * i + s2[0] * j, p[1] + s1[1] * i + s2[1] * j, p[2] + s1[2] * i + s2[2] * j]);
      }
    }
    const faces = [[0,1,2,3], [7,6,5,4], [0,4,5,1], [1,5,6,2], [2,6,7,3], [3,7,4,0]];
    for (const f of faces) {
      pushTri(q[f[0]], q[f[1]], q[f[2]], color);
      pushTri(q[f[0]], q[f[2]], q[f[3]], color);
    }
  }

  /** Цилиндр с крышкой — бак и трубы. */
  function cylinder(cx, cy, cz, rad, h, color, sides = 20, cap = true) {
    const lo = [], hi = [];
    for (let j = 0; j < sides; j++) {
      const a = (j / sides) * TAU;
      lo.push([cx + Math.cos(a) * rad, cy, cz + Math.sin(a) * rad]);
      hi.push([cx + Math.cos(a) * rad, cy + h, cz + Math.sin(a) * rad]);
    }
    for (let j = 0; j < sides; j++) {
      const k = (j + 1) % sides;
      pushTri(lo[j], hi[j], lo[k], color);
      pushTri(lo[k], hi[j], hi[k], color);
    }
    if (cap) for (let j = 1; j < sides - 1; j++) pushTri(hi[0], hi[j], hi[j + 1], color);
  }

  const steel = [0.52, 0.53, 0.55];
  const rust = [0.44, 0.30, 0.22];
  const wood = [0.46, 0.36, 0.26];

  // четыре ноги решётчатой башни
  const base = 1.5, top = 0.42, H = MILL.h;
  const legs = [[1, 1], [1, -1], [-1, -1], [-1, 1]];
  const legPt = (i, t) => {
    const s = lerp(base, top, t);
    return [MILL.x + legs[i][0] * s, MILL.y - 0.3 + t * H, MILL.z + legs[i][1] * s];
  };
  for (let i = 0; i < 4; i++) beam(legPt(i, 0), legPt(i, 1), 0.055, steel);

  // горизонтальные обвязки и раскосы
  for (const t of [0.22, 0.45, 0.68, 0.9]) {
    for (let i = 0; i < 4; i++) beam(legPt(i, t), legPt((i + 1) % 4, t), 0.032, steel);
  }
  for (const [t0, t1] of [[0.0, 0.22], [0.22, 0.45], [0.45, 0.68], [0.68, 0.9]]) {
    for (let i = 0; i < 4; i++) beam(legPt(i, t0), legPt((i + 1) % 4, t1), 0.026, steel);
  }

  // площадка, ось и хвост-стабилизатор
  const hub = [MILL.x, MILL.y - 0.3 + H, MILL.z];
  const fx = Math.sin(MILL.facing), fz = -Math.cos(MILL.facing);
  beam([hub[0] - fx * 0.5, hub[1], hub[2] - fz * 0.5], [hub[0] + fx * 0.9, hub[1], hub[2] + fz * 0.9], 0.09, rust);
  const tailA = [hub[0] - fx * 0.6, hub[1], hub[2] - fz * 0.6];
  const tailB = [hub[0] - fx * 2.3, hub[1] + 0.12, hub[2] - fz * 2.3];
  beam(tailA, tailB, 0.045, steel);
  const px = -fz, pz = fx;   // поперёк хвоста
  const vane = [
    [tailB[0], tailB[1] - 0.42, tailB[2]],
    [tailB[0], tailB[1] + 0.52, tailB[2]],
    [tailB[0] - px * 1.15, tailB[1] + 0.46, tailB[2] - pz * 1.15],
    [tailB[0] - px * 1.15, tailB[1] - 0.30, tailB[2] - pz * 1.15],
  ];
  pushTri(vane[0], vane[1], vane[2], rust);
  pushTri(vane[0], vane[2], vane[3], rust);

  // бак с водой, обод и подводящая труба
  cylinder(TANK.x, TANK.y - 0.1, TANK.z, TANK.r, TANK.h, [0.46, 0.42, 0.38], 22, false);
  cylinder(TANK.x, TANK.y + TANK.h - 0.2, TANK.z, TANK.r + 0.06, 0.1, [0.55, 0.50, 0.45], 22, false);
  beam([hub[0], MILL.y + 0.2, hub[2]], [hub[0], MILL.y + H * 0.55, hub[2]], 0.05, rust);
  beam([hub[0], MILL.y + 0.35, hub[2]], [TANK.x, TANK.y + TANK.h + 0.25, TANK.z], 0.045, rust);

  // деревянный настил у бака, чтобы подойти
  for (let i = 0; i < 3; i++) {
    const zz = TANK.z + 2.1 + i * 0.45;
    beam([TANK.x - 1.1, terrainH(TANK.x - 1.1, zz) + 0.05, zz],
         [TANK.x + 1.1, terrainH(TANK.x + 1.1, zz) + 0.05, zz], 0.09, wood);
  }

  // камни вокруг бака
  for (let j = 0; j < 9; j++) {
    const a = (j / 9) * TAU + 0.4;
    const rr = TANK.r + 0.9 + R() * 0.5;
    const x = TANK.x + Math.cos(a) * rr, z = TANK.z + Math.sin(a) * rr;
    api.boulder(x, terrainH(x, z) - 0.05, z, 0.2 + R() * 0.18, 0.22,
      [0.5 + R() * 0.07, 0.39 + R() * 0.05, 0.31 + R() * 0.04], 6, 2);
  }
}

/* ---------------- вращающееся колесо ---------------- */

function buildRotor() {
  const pos = [], nrm = [], col = [], idx = [];
  const pushTri = (a, b, c, color) => {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    for (const p of [a, b, c]) {
      idx.push(pos.length / 3);
      pos.push(p[0], p[1], p[2]);
      nrm.push(nx / l, ny / l, nz / l);
      col.push(color[0], color[1], color[2]);
    }
  };

  const N = 18, r0 = 0.34, r1 = 1.55, tilt = 0.42;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * TAU;
    const ca = Math.cos(a), sa = Math.sin(a);
    const tx = -sa, ty = ca;                       // касательная — вдоль неё лопасть шире
    const w0 = 0.11, w1 = 0.20;
    const z0 = -tilt * w0, z1 = tilt * w1;         // разворот лопасти к ветру
    const p = (r, w, zz) => [ca * r + tx * w, sa * r + ty * w, zz];
    const shade = 0.62 + 0.2 * ((i % 3) / 2);
    const c = [0.70 * shade, 0.71 * shade, 0.74 * shade];
    pushTri(p(r0, -w0, z0), p(r1, -w1, z0), p(r1, w1, z1), c);
    pushTri(p(r0, -w0, z0), p(r1, w1, z1), p(r0, w0, z1), c);
  }

  // ступица и обод
  const hubC = [0.40, 0.28, 0.20];
  for (let i = 0; i < 14; i++) {
    const a0 = (i / 14) * TAU, a1 = ((i + 1) / 14) * TAU;
    pushTri([0, 0, 0.06], [Math.cos(a0) * 0.3, Math.sin(a0) * 0.3, 0.02],
            [Math.cos(a1) * 0.3, Math.sin(a1) * 0.3, 0.02], hubC);
  }
  for (let i = 0; i < 40; i++) {
    const a0 = (i / 40) * TAU, a1 = ((i + 1) / 40) * TAU;
    const rr = r1 + 0.03, t = 0.035;
    const A = [Math.cos(a0) * rr, Math.sin(a0) * rr, -t], B = [Math.cos(a1) * rr, Math.sin(a1) * rr, -t];
    const C = [Math.cos(a1) * rr, Math.sin(a1) * rr, t], D = [Math.cos(a0) * rr, Math.sin(a0) * rr, t];
    pushTri(A, B, C, hubC); pushTri(A, C, D, hubC);
  }

  return {
    pos: buffer(new Float32Array(pos)),
    nrm: buffer(new Float32Array(nrm)),
    col: buffer(new Float32Array(col)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/* ---------------- вода в баке ---------------- */

function buildWater() {
  const pos = [], idx = [];
  const N = 40;
  pos.push(TANK.x, TANK.top, TANK.z);
  for (let i = 0; i <= N; i++) {
    const a = (i / N) * TAU;
    pos.push(TANK.x + Math.cos(a) * (TANK.r - 0.1), TANK.top, TANK.z + Math.sin(a) * (TANK.r - 0.1));
  }
  for (let i = 1; i <= N; i++) idx.push(0, i, i + 1);
  return {
    pos: buffer(new Float32Array(pos)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/* ---------------- ладони от первого лица ---------------- */

/**
 * Кисть по фотографии: ладонь и пальцы — сплюснутые конические сегменты,
 * длины взяты с руки владельца (средний длиннее всех, мизинец заметно короче,
 * большой отставлен низко), кожа бледно-розовая, из рукава торчит серо-зелёный трикотаж.
 */
function buildHand(mirror) {
  const pos = [], nrm = [], col = [], idx = [];
  const s = mirror ? -1 : 1;

  const tri = (a, b, c, color) => {
    if (mirror) { const t = b; b = c; c = t; }
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    for (const p of [a, b, c]) {
      idx.push(pos.length / 3);
      pos.push(p[0] * s, p[1], p[2]);
      nrm.push((nx / l) * s, ny / l, nz / l);
      col.push(color[0], color[1], color[2]);
    }
  };

  /**
   * Сегментированная «колбаса» по ломаной: на каждом узле эллиптическое
   * сечение (rx — поперёк, ry — толщина), концы закрываются веером.
   */
  function limb(nodes, rx, ry, color, sides = 9, capEnd = true) {
    const rings = [];
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[Math.max(0, i - 1)], b = nodes[Math.min(nodes.length - 1, i + 1)];
      let dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      const dl = Math.hypot(dx, dy, dz) || 1; dx /= dl; dy /= dl; dz /= dl;
      // боковой орт: пальцы почти не уходят из горизонта, up = (0,1,0) устойчив
      let sx = dy * 0 - dz * 1, sy = dz * 0 - dx * 0, sz = dx * 1 - dy * 0;
      const sl = Math.hypot(sx, sy, sz) || 1; sx /= sl; sy /= sl; sz /= sl;
      const ux = sy * dz - sz * dy, uy = sz * dx - sx * dz, uz2 = sx * dy - sy * dx;
      const ring = [];
      for (let j = 0; j < sides; j++) {
        const t = (j / sides) * TAU;
        const c = Math.cos(t) * rx[i], k = Math.sin(t) * ry[i];
        ring.push([nodes[i][0] + sx * c + ux * k, nodes[i][1] + sy * c + uy * k, nodes[i][2] + sz * c + uz2 * k]);
      }
      rings.push(ring);
    }
    for (let i = 0; i < rings.length - 1; i++) {
      for (let j = 0; j < sides; j++) {
        const k = (j + 1) % sides;
        tri(rings[i][j], rings[i + 1][j], rings[i][k], color);
        tri(rings[i][k], rings[i + 1][j], rings[i + 1][k], color);
      }
    }
    if (capEnd) {
      const last = rings[rings.length - 1], tip = nodes[nodes.length - 1];
      const dz = [tip[0] - nodes[nodes.length - 2][0], tip[1] - nodes[nodes.length - 2][1], tip[2] - nodes[nodes.length - 2][2]];
      const dl = Math.hypot(...dz) || 1;
      const apex = [tip[0] + dz[0] / dl * rx[rx.length - 1] * 0.9,
                    tip[1] + dz[1] / dl * rx[rx.length - 1] * 0.9,
                    tip[2] + dz[2] / dl * rx[rx.length - 1] * 0.9];
      for (let j = 0; j < sides; j++) tri(last[j], apex, last[(j + 1) % sides], color);
    }
    const first = rings[0];
    for (let j = 1; j < sides - 1; j++) tri(first[0], first[j + 1], first[j], color);
  }

  // тона сняты с фотографии: бледная розовая кожа, кончики чуть краснее
  const skin = [0.885, 0.700, 0.655];
  const skinPalm = [0.905, 0.720, 0.680];
  const tipC = [0.855, 0.605, 0.570];
  const sleeve = [0.415, 0.440, 0.395];

  // ладонь: от запястья к костяшкам расширяется и утончается
  limb(
    [[0, 0, 0.070], [0, 0.001, 0.030], [0, 0.002, -0.012], [0, 0.002, -0.050]],
    [0.030, 0.036, 0.043, 0.044],
    [0.0165, 0.0170, 0.0155, 0.0135],
    skinPalm, 12, false
  );

  // предплечье и рукав свитера
  limb([[0, -0.002, 0.062], [0, -0.004, 0.115]], [0.031, 0.034], [0.026, 0.029], skin, 12, false);
  limb([[0, -0.004, 0.110], [0, -0.006, 0.215]], [0.038, 0.041], [0.033, 0.036], sleeve, 12, false);

  // четыре пальца: длина, разлёт и лёгкий подгиб как на снимке
  const fingers = [
    { x: -0.0345, len: 0.074, spread: -0.27, curl: 0.15, r: 0.0104 },  // указательный
    { x: -0.0115, len: 0.082, spread: -0.05, curl: 0.13, r: 0.0106 },  // средний
    { x:  0.0115, len: 0.077, spread:  0.15, curl: 0.15, r: 0.0100 },  // безымянный
    { x:  0.0335, len: 0.061, spread:  0.39, curl: 0.19, r: 0.0089 },  // мизинец
  ];
  for (const f of fingers) {
    const seg = [0.40, 0.34, 0.26].map((k) => k * f.len);
    const nodes = [[f.x, 0.002, -0.048]];
    let dirY = -0.02, ang = f.spread;
    for (let i = 0; i < 3; i++) {
      const prev = nodes[nodes.length - 1];
      dirY -= f.curl * 0.42;
      nodes.push([
        prev[0] + Math.sin(ang) * seg[i],
        prev[1] + dirY * seg[i],
        prev[2] - Math.cos(ang) * seg[i],
      ]);
      ang += f.spread * 0.10;
    }
    limb(nodes, [f.r, f.r * 0.96, f.r * 0.88, f.r * 0.74],
      [f.r * 0.88, f.r * 0.86, f.r * 0.80, f.r * 0.68], skin, 8, true);
    // подушечка кончика чуть румянее
    limb([nodes[2], nodes[3]], [f.r * 0.90, f.r * 0.75], [f.r * 0.82, f.r * 0.70], tipC, 8, true);
  }

  // большой палец: посажен низко у запястья и сильно отставлен
  limb(
    [[-0.036, -0.004, 0.026], [-0.058, -0.010, -0.004], [-0.075, -0.016, -0.030], [-0.086, -0.022, -0.050]],
    [0.0135, 0.0122, 0.0108, 0.0090],
    [0.0125, 0.0112, 0.0098, 0.0082],
    skin, 9, true
  );

  return {
    pos: buffer(new Float32Array(pos)),
    nrm: buffer(new Float32Array(nrm)),
    col: buffer(new Float32Array(col)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/** Матрица «в системе камеры»: смещение задано в метрах вперёд/вправо/вверх. */
function m4viewLocal(out, eye, right, up, fwd, off, ry, rx, rz, scale) {
  const B = m4();
  B[0] = right[0]; B[1] = right[1]; B[2] = right[2]; B[3] = 0;
  B[4] = up[0];    B[5] = up[1];    B[6] = up[2];    B[7] = 0;
  B[8] = -fwd[0];  B[9] = -fwd[1];  B[10] = -fwd[2]; B[11] = 0;
  B[12] = eye[0];  B[13] = eye[1];  B[14] = eye[2];  B[15] = 1;
  const L = m4();
  m4compose(L, off[0], off[1], off[2], ry, rx, rz, scale);
  return m4mul(out, B, L);
}

/* ============================================================
   Нормаль к средней линии
   ============================================================ */

/** Точка поверхности — та же формула, что в шейдере лент. */
function bandPoint(u, v, k, R) {
  const cu = Math.cos(u), su = Math.sin(u), a = k * u * 0.5;
  const fx = Math.sin(a), fy = Math.cos(a);
  return [cu * R + v * fx * cu, v * fy, su * R + v * fx * su];
}

/** Единичная нормаль к поверхности на средней линии (v = 0). */
function bandNormal(u, k, R) {
  const e = 1e-3;
  const p = bandPoint(u, 0, k, R);
  const pu = bandPoint(u + e, 0, k, R);
  const pv = bandPoint(u, e, k, R);
  const ax = pu[0] - p[0], ay = pu[1] - p[1], az = pu[2] - p[2];
  const bx = pv[0] - p[0], by = pv[1] - p[1], bz = pv[2] - p[2];
  const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
  const l = Math.hypot(nx, ny, nz) || 1;
  return [nx / l, ny / l, nz / l];
}

/** Стрелка: гранёный стержень плюс конус. Пишет в переданные массивы. */
function pushArrow(arr, base, dir, len, rad, uVal, sides = 7) {
  const { pos, nrm, us, idx } = arr;
  let t = Math.abs(dir[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  let tx = dir[1] * t[2] - dir[2] * t[1], ty = dir[2] * t[0] - dir[0] * t[2], tz = dir[0] * t[1] - dir[1] * t[0];
  const tl = Math.hypot(tx, ty, tz) || 1; tx /= tl; ty /= tl; tz /= tl;
  const bx = dir[1] * tz - dir[2] * ty, by = dir[2] * tx - dir[0] * tz, bz = dir[0] * ty - dir[1] * tx;

  const shaft = len * 0.72, headR = rad * 2.6;
  const at = (h, r, j) => {
    const a = (j / sides) * TAU, c = Math.cos(a) * r, s = Math.sin(a) * r;
    return [base[0] + dir[0] * h + tx * c + bx * s,
            base[1] + dir[1] * h + ty * c + by * s,
            base[2] + dir[2] * h + tz * c + bz * s];
  };
  const tip = [base[0] + dir[0] * len, base[1] + dir[1] * len, base[2] + dir[2] * len];

  const tri = (a, b, c) => {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    for (const p of [a, b, c]) {
      idx.push(pos.length / 3);
      pos.push(p[0], p[1], p[2]);
      nrm.push(nx / l, ny / l, nz / l);
      us.push(uVal);
    }
  };

  for (let j = 0; j < sides; j++) {
    const k = (j + 1) % sides;
    tri(at(0, rad, j), at(shaft, rad, j), at(0, rad, k));
    tri(at(0, rad, k), at(shaft, rad, j), at(shaft, rad, k));
    tri(at(shaft, headR, j), tip, at(shaft, headR, k));
    tri(at(shaft, headR, j), at(shaft, headR, k), at(shaft, rad * 0.6, j));
  }
}

function packArrows(arr) {
  return {
    pos: buffer(new Float32Array(arr.pos)),
    nrm: buffer(new Float32Array(arr.nrm)),
    us: buffer(new Float32Array(arr.us)),
    idx: buffer(new Uint16Array(arr.idx), gl.ELEMENT_ARRAY_BUFFER),
    count: arr.idx.length,
  };
}

/** Щетинка нормалей вдоль всей средней линии; появляется по мере черчения. */
function buildHairs(k, R) {
  const arr = { pos: [], nrm: [], us: [], idx: [] };
  const N = 26;
  for (let i = 0; i < N; i++) {
    const u = (i / N) * TAU;
    pushArrow(arr, bandPoint(u, 0, k, R), bandNormal(u, k, R), 0.17, 0.0095, i / N, 5);
  }
  return packArrows(arr);
}

/**
 * Единичная стрелка вдоль +Y: длина 1 и радиус 1, потому что реальные
 * размеры задаёт матрица m4arrow. Радиус здесь тоже должен быть единичным,
 * иначе он умножится дважды и стрелка выродится в нитку.
 */
function buildUnitArrow() {
  const arr = { pos: [], nrm: [], us: [], idx: [] };
  pushArrow(arr, [0, 0, 0], [0, 1, 0], 1, 1, -1, 9);
  return packArrows(arr);
}

/** Матрица, ставящая единичную стрелку в точку p вдоль направления n. */
function m4arrow(out, p, n, len, rad) {
  let t = Math.abs(n[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  let tx = n[1] * t[2] - n[2] * t[1], ty = n[2] * t[0] - n[0] * t[2], tz = n[0] * t[1] - n[1] * t[0];
  const tl = Math.hypot(tx, ty, tz) || 1; tx /= tl; ty /= tl; tz /= tl;
  const bx = n[1] * tz - n[2] * ty, by = n[2] * tx - n[0] * tz, bz = n[0] * ty - n[1] * tx;
  out[0] = tx * rad; out[1] = ty * rad; out[2] = tz * rad; out[3] = 0;
  out[4] = n[0] * len; out[5] = n[1] * len; out[6] = n[2] * len; out[7] = 0;
  out[8] = bx * rad; out[9] = by * rad; out[10] = bz * rad; out[11] = 0;
  out[12] = p[0]; out[13] = p[1]; out[14] = p[2]; out[15] = 1;
  return out;
}
