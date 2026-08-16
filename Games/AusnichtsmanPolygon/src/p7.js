/* ============================================================
   Палатка: навес, кот, фонарь и блокнот
   ============================================================ */

const TENT = { x: 32, z: 27, yaw: -0.86 };
TENT.y = terrainH(TENT.x, TENT.z);
/** Перевод локальных координат палатки в мировые. */
TENT.at = (x, z) => [
  TENT.x + x * Math.cos(TENT.yaw) - z * Math.sin(TENT.yaw),
  TENT.z + x * Math.sin(TENT.yaw) + z * Math.cos(TENT.yaw),
];

/** Гость садится у входа лицом вглубь палатки, кот — на подушке напротив. */
{
  const s = TENT.at(0.15, -1.02);
  TENT.seat = [s[0], TENT.y + 0.96, s[1]];
  const c = TENT.at(-0.62, 0.42);
  TENT.cat = [c[0], TENT.y + 0.20, c[1]];
  const look = TENT.at(0.02, 0.55);
  TENT.lookAt = [look[0], look[1]];
}

/** Общая мастерская для мешей палатки: треугольники, коробки, «капли». */
function meshBuilder() {
  const pos = [], nrm = [], col = [], idx = [];

  const tri = (a, b, c, color) => {
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

  const quad = (a, b, c, d, color) => { tri(a, b, c, color); tri(a, c, d, color); };

  const box = (cx, cy, cz, hx, hy, hz, yaw, color) => {
    const co = Math.cos(yaw), si = Math.sin(yaw);
    const P = (x, y, z) => [cx + x * co - z * si, cy + y, cz + x * si + z * co];
    const v = [P(-hx,-hy,-hz), P(hx,-hy,-hz), P(hx,hy,-hz), P(-hx,hy,-hz),
               P(-hx,-hy,hz), P(hx,-hy,hz), P(hx,hy,hz), P(-hx,hy,hz)];
    quad(v[0], v[1], v[2], v[3], color); quad(v[5], v[4], v[7], v[6], color);
    quad(v[4], v[0], v[3], v[7], color); quad(v[1], v[5], v[6], v[2], color);
    quad(v[3], v[2], v[6], v[7], color); quad(v[4], v[5], v[1], v[0], color);
  };

  /** Эллипсоид — тело и голова кота. */
  const blob = (cx, cy, cz, rx, ry, rz, color, seg = 10, ring = 7) => {
    const P = (i, j) => {
      const th = (i / seg) * TAU, ph = (j / ring) * Math.PI - Math.PI / 2;
      return [cx + Math.cos(ph) * Math.cos(th) * rx, cy + Math.sin(ph) * ry, cz + Math.cos(ph) * Math.sin(th) * rz];
    };
    for (let j = 0; j < ring; j++) {
      for (let i = 0; i < seg; i++) {
        const a = P(i, j), b = P(i + 1, j), c = P(i + 1, j + 1), d = P(i, j + 1);
        quad(a, b, c, d, color);
      }
    }
  };

  /** Сегментированная колбаса — хвост и лапы. */
  const rope = (nodes, radii, color, sides = 7) => {
    const rings = [];
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[Math.max(0, i - 1)], b = nodes[Math.min(nodes.length - 1, i + 1)];
      let dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      const dl = Math.hypot(dx, dy, dz) || 1; dx /= dl; dy /= dl; dz /= dl;
      let sx = -dz, sy = 0, sz = dx;
      const sl = Math.hypot(sx, sy, sz) || 1; sx /= sl; sy /= sl; sz /= sl;
      const ux = sy * dz - sz * dy, uy = sz * dx - sx * dz, uz = sx * dy - sy * dx;
      const ring = [];
      for (let k = 0; k < sides; k++) {
        const t = (k / sides) * TAU, c = Math.cos(t) * radii[i], s = Math.sin(t) * radii[i];
        ring.push([nodes[i][0] + sx * c + ux * s, nodes[i][1] + sy * c + uy * s, nodes[i][2] + sz * c + uz * s]);
      }
      rings.push(ring);
    }
    for (let i = 0; i < rings.length - 1; i++) {
      for (let k = 0; k < sides; k++) {
        const m = (k + 1) % sides;
        tri(rings[i][k], rings[i + 1][k], rings[i][m], color);
        tri(rings[i][m], rings[i + 1][k], rings[i + 1][m], color);
      }
    }
  };

  const pack = () => ({
    pos: buffer(new Float32Array(pos)),
    nrm: buffer(new Float32Array(nrm)),
    col: buffer(new Float32Array(col)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  });

  return { tri, quad, box, blob, rope, pack };
}

/** Двускатная брезентовая палатка с ковром, ящиком и фонарём. */
function buildTent() {
  const m = meshBuilder();
  const co = Math.cos(TENT.yaw), si = Math.sin(TENT.yaw);
  const P = (x, y, z) => [TENT.x + x * co - z * si, TENT.y + y, TENT.z + x * si + z * co];

  const canvasOut = [0.68, 0.62, 0.48];
  const canvasIn = [0.80, 0.72, 0.56];
  const pole = [0.42, 0.32, 0.22];
  const rug = [0.52, 0.24, 0.20];
  const rugTrim = [0.72, 0.58, 0.32];
  const crate = [0.48, 0.37, 0.25];

  const W = 1.55, H = 1.95, L = 1.75;   // полуширина, высота конька, полудлина

  // скаты: снаружи и изнутри слегка разного тона
  for (const s of [-1, 1]) {
    m.quad(P(s * W, 0, -L), P(0, H, -L), P(0, H, L), P(s * W, 0, L), canvasOut);
    m.quad(P(s * W * 0.97, 0.02, -L * 0.97), P(s * W * 0.97, 0.02, L * 0.97),
           P(0, H - 0.04, L * 0.97), P(0, H - 0.04, -L * 0.97), canvasIn);
  }
  // задняя стенка и приоткрытые пологи спереди
  m.tri(P(-W, 0, L), P(0, H, L), P(W, 0, L), canvasOut);
  m.tri(P(-W, 0, L), P(W, 0, L), P(0, H, L), canvasIn);
  for (const s of [-1, 1]) {
    m.quad(P(s * W, 0, -L), P(s * W * 0.42, 0, -L - 0.30), P(s * W * 0.34, H * 0.62, -L - 0.24), P(0, H, -L), canvasOut);
  }

  // конёк и стойки
  m.box(...P(0, H, 0), 0.045, 0.045, L + 0.12, TENT.yaw, pole);
  for (const z of [-L, L]) {
    m.rope([P(0, 0, z), P(0, H, z)], [0.055, 0.045], pole);
  }
  // колышки и растяжки
  for (const s of [-1, 1]) for (const z of [-L * 0.8, L * 0.8]) {
    m.rope([P(s * W, 0.02, z), P(s * (W + 0.55), -0.05, z)], [0.02, 0.012], pole);
  }

  // ковёр с каймой
  m.box(...P(0, 0.015, 0), W * 0.92, 0.015, L * 0.9, TENT.yaw, rug);
  m.box(...P(0, 0.028, 0), W * 0.62, 0.012, L * 0.6, TENT.yaw, rugTrim);

  // лежанка-подушка и сложенный плед
  m.blob(...P(-W * 0.45, 0.14, L * 0.28), 0.52, 0.13, 0.42, [0.40, 0.30, 0.42], 12, 6);
  m.box(...P(-W * 0.5, 0.30, L * 0.05), 0.34, 0.08, 0.26, TENT.yaw + 0.2, [0.30, 0.36, 0.34]);

  // ящик под блокнот
  m.box(...P(W * 0.52, 0.22, L * 0.14), 0.34, 0.22, 0.26, TENT.yaw + 0.15, crate);
  m.box(...P(W * 0.52, 0.44, L * 0.14), 0.35, 0.012, 0.27, TENT.yaw + 0.15, [0.55, 0.43, 0.29]);

  // блокнот на ящике: обложка, страницы, ляссе и карандаш
  const bx = W * 0.52, by = 0.455, bz = L * 0.14;
  m.box(...P(bx, by + 0.018, bz), 0.16, 0.018, 0.115, TENT.yaw - 0.25, [0.35, 0.20, 0.16]);
  m.box(...P(bx, by + 0.032, bz), 0.148, 0.010, 0.104, TENT.yaw - 0.25, [0.90, 0.86, 0.76]);
  m.box(...P(bx + 0.02, by + 0.040, bz - 0.02), 0.012, 0.004, 0.10, TENT.yaw - 0.25, [0.72, 0.24, 0.22]);
  m.rope([P(bx - 0.10, by + 0.05, bz + 0.13), P(bx + 0.12, by + 0.05, bz + 0.10)], [0.010, 0.006], [0.85, 0.70, 0.25]);

  // фонарь под коньком
  const lx = 0, ly = H - 0.42, lz = -L * 0.45;
  m.rope([P(lx, H - 0.05, lz), P(lx, ly + 0.12, lz)], [0.008, 0.008], pole);
  m.box(...P(lx, ly, lz), 0.075, 0.11, 0.075, TENT.yaw, [0.30, 0.28, 0.26]);
  m.box(...P(lx, ly + 0.13, lz), 0.055, 0.02, 0.055, TENT.yaw, [0.36, 0.33, 0.30]);

  TENT.lamp = P(lx, ly, lz);
  return m.pack();
}

/** Кот сидит на подушке: тело, голова, уши, лапы и обёрнутый хвост. */
function buildCat() {
  const m = meshBuilder();
  const fur = [0.62, 0.44, 0.26];
  const furDark = [0.48, 0.32, 0.18];
  const belly = [0.80, 0.70, 0.56];
  const nose = [0.82, 0.52, 0.52];

  // круп и грудь сидящего кота
  m.blob(0, 0.16, 0.06, 0.20, 0.17, 0.22, fur, 12, 8);
  m.blob(0, 0.26, -0.10, 0.15, 0.20, 0.15, fur, 12, 8);
  m.blob(0, 0.20, -0.17, 0.10, 0.13, 0.08, belly, 10, 6);

  // голова, мордочка, уши
  m.blob(0, 0.46, -0.14, 0.125, 0.115, 0.115, fur, 12, 8);
  m.blob(0, 0.43, -0.22, 0.062, 0.050, 0.045, belly, 10, 6);
  m.blob(0, 0.435, -0.255, 0.018, 0.014, 0.014, nose, 8, 5);
  for (const s of [-1, 1]) {
    m.tri([s * 0.045, 0.55, -0.15], [s * 0.115, 0.54, -0.13], [s * 0.085, 0.66, -0.12], fur);
    m.tri([s * 0.055, 0.55, -0.155], [s * 0.105, 0.545, -0.14], [s * 0.082, 0.635, -0.125], [0.88, 0.66, 0.62]);
  }

  // передние лапы
  for (const s of [-1, 1]) {
    m.rope([[s * 0.075, 0.30, -0.16], [s * 0.080, 0.12, -0.22], [s * 0.082, 0.035, -0.26]],
           [0.048, 0.042, 0.045], fur);
    m.blob(s * 0.082, 0.032, -0.285, 0.050, 0.028, 0.042, belly, 8, 5);
  }

  // хвост, обёрнутый вокруг лап
  m.rope([
    [0.12, 0.10, 0.20], [0.22, 0.06, 0.05], [0.20, 0.04, -0.15],
    [0.06, 0.035, -0.29], [-0.11, 0.035, -0.30],
  ], [0.055, 0.050, 0.045, 0.040, 0.032], furDark);

  // полоски на спине
  for (let i = 0; i < 4; i++) {
    m.box(0, 0.31 - i * 0.005, 0.02 + i * 0.06, 0.055, 0.012, 0.014, 0, furDark);
  }
  return m.pack();
}

/** Светящиеся детали: глаза кота и пламя фонаря — рисуются без освещения. */
function buildGlow() {
  const arr = { pos: [], nrm: [], us: [], idx: [] };
  const dot = (cx, cy, cz, r) => {
    const seg = 7;
    for (let j = 0; j < seg; j++) {
      for (let i = 0; i < seg; i++) {
        const P = (a, b) => {
          const th = (a / seg) * TAU, ph = (b / seg) * Math.PI - Math.PI / 2;
          return [cx + Math.cos(ph) * Math.cos(th) * r, cy + Math.sin(ph) * r, cz + Math.cos(ph) * Math.sin(th) * r];
        };
        const A = P(i, j), B = P(i + 1, j), C = P(i + 1, j + 1), D = P(i, j + 1);
        for (const [p, q, s] of [[A, B, C], [A, C, D]]) {
          for (const v of [p, q, s]) {
            arr.idx.push(arr.pos.length / 3);
            arr.pos.push(v[0], v[1], v[2]);
            arr.nrm.push(0, 1, 0);
            arr.us.push(-1);
          }
        }
      }
    }
  };
  dot(0, 0, 0, 1);   // единичный шарик, размер задаёт матрица
  return packArrows(arr);
}
