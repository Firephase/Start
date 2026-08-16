/* ============================================================
   Ракета, полёт в космос, планета и квантовые пары у горизонта
   ============================================================ */

const PAD = { x: 14, z: 9 };
PAD.y = terrainH(PAD.x, PAD.z);

const ASCENT_TIME = 120;          // подъём до потолка — ровно две минуты
const CEILING = 20000;            // потолок подъёма, метры
const DESCENT_TIME = 90;

/* Астрономия сцены, всё в метрах.
   Земля радиусом 3000 км, квазар в двух миллионах километров,
   его радиус 50 000 км. Останавливаемся в 50 000 км от поверхности. */
const PLANET_R = 3.0e6;
// направление на «домашнюю» точку планеты — над ней висит стартовая площадка
const PLANET_HOME = [0, Math.sin(0.42), Math.cos(0.42)];
const QUASAR_DIST = 2.0e9;
const QUASAR_R = 5.0e7;
const QUASAR_STOP = QUASAR_DIST - QUASAR_R - 5.0e7;   // 1.9 млн км пути
const LENS_START = 2.0e8;         // ближе 200 000 км начинается искривление
const ACC = 981;                  // 100 g — предел ускорения
const VMAX = 2.0e7;               // потолок скорости, 20 000 км/с

/* Полёт — состояния: pad → ascent → hold (сколько угодно) → cruise → home. */
const ROCKET = {
  phase: 'pad',
  flying: false,
  stealth: false,
  t: 0,
  alt: 0,               // высота над площадкой, метры
  cruise: 0,            // пройдено в сторону квазара, метры (только для вида)
  vel: 0,
  cruiseVel: 0,
  gforce: 1,
  thrust: 0,
  warp: 1,              // ускорение времени: 46 минут иначе не пролетишь
  dest: 'quasar',       // куда нацелен крейсер: квазар, Гамма или обратно домой
  pos: [PAD.x, PAD.y, PAD.z],
  up: [0, 1, 0],
  model: m4(),
  cockpit: [PAD.x, PAD.y + 6.9, PAD.z],
  seatPush: 0,
};

let spaceAmount = 0;
let planetFade = 0;
let quasarZoom = 1;     // во сколько раз квазар крупнее, чем с Земли
let quasarLens = 0;     // сила искривления: ноль дальше 200 000 км

const airDensity = (alt) => Math.exp(-Math.max(alt, 0) / 7000);

/** Расстояние от корабля до центра квазара. */
const quasarRange = () => QUASAR_DIST - ROCKET.cruise;

function rocketStart() { ROCKET.phase = 'ascent'; ROCKET.flying = true; ROCKET.t = 0; }
function rocketToQuasar() { if (ROCKET.phase === 'hold') { ROCKET.phase = 'cruise'; ROCKET.t = 0; } }
function rocketHold() { if (ROCKET.phase === 'cruise') { ROCKET.phase = 'hold'; ROCKET.t = 0; } }
function rocketHome() {
  if (ROCKET.phase === 'pad' || ROCKET.phase === 'ascent') return;
  ROCKET.phase = 'home'; ROCKET.t = 0;
}

function rocketReset() {
  ROCKET.phase = 'pad'; ROCKET.flying = false;
  ROCKET.t = 0; ROCKET.alt = 0; ROCKET.cruise = 0;
  ROCKET.vel = 0; ROCKET.cruiseVel = 0; ROCKET.thrust = 0; ROCKET.gforce = 1; ROCKET.warp = 1;
  spaceAmount = 0; planetFade = 0; quasarZoom = 1; quasarLens = 0; gammaAng = 0;
  if (destOptions().indexOf(ROCKET.dest) < 0) ROCKET.dest = destOptions()[0];
}

/**
 * Один шаг разгона-торможения: жмём 100 g, пока хватает пути, потом
 * тормозим ровно так, чтобы прийти с нулевой скоростью. Перелёт и остаток
 * короче шага гасим сразу — иначе корабль вечно качается около отметки.
 */
function cruiseStep(target, dt) {
  const p = ROCKET;
  const rest = target - p.cruise;
  const dir = Math.sign(rest) || 1;
  const brake = (p.cruiseVel * p.cruiseVel) / (2 * ACC);
  const a = Math.abs(rest) <= brake ? -Math.sign(p.cruiseVel) * ACC : dir * ACC;
  p.cruiseVel = clamp(p.cruiseVel + a * dt, -VMAX, VMAX);
  p.cruise += p.cruiseVel * dt;
  const left = target - p.cruise;
  if (Math.abs(left) <= Math.max(1e4, Math.abs(p.cruiseVel) * dt) || Math.sign(left) !== dir) {
    p.cruise = target; p.cruiseVel = 0;
    return true;
  }
  return false;
}

/**
 * Тот же профиль, но шаг дробится: на ускорении времени кадр покрывает
 * десятки тысяч километров, и квазар прыгал бы рывками. Ограничиваем
 * перемещение за подшаг двумя процентами оставшегося расстояния.
 */
function cruiseTowards(target, dt) {
  const p = ROCKET;
  let left = dt;
  for (let i = 0; i < 64 && left > 1e-4; i++) {
    const span = Math.max((destStop() - p.cruise) * 0.02, 2.0e5);
    const v = Math.abs(p.cruiseVel);
    const step = v > 1 ? Math.min(left, span / v) : left;
    if (cruiseStep(target, step)) return true;
    left -= step;
  }
  return false;
}

/**
 * Сколько ещё лететь по профилю «разгон 100 g — торможение 100 g»:
 * разгоняемся до пика vp, потом гасим ровно в ноль у цели.
 */
function cruiseEta(rest, v) {
  if (rest <= (v * v) / (2 * ACC)) return v / ACC;
  const vp = Math.min(Math.sqrt(ACC * rest + v * v / 2), VMAX);
  return (2 * vp - v) / ACC + Math.max(0, rest - (2 * vp * vp - v * v) / (2 * ACC)) / vp;
}

function updateRocket(dtReal) {
  const p = ROCKET;
  const dt = dtReal * (p.phase === 'cruise' || (p.phase === 'home' && p.cruise > 1) ? p.warp : 1);
  p.t += dt;
  const prevVel = p.vel, prevCruise = p.cruiseVel;

  if (p.phase === 'pad') {
    p.alt = 0; p.cruise = 0; p.vel = 0; p.cruiseVel = 0; p.thrust = 0;
  } else if (p.phase === 'ascent') {
    const u = clamp(p.t / ASCENT_TIME, 0, 1);
    p.alt = CEILING * u * u * (3 - 2 * u);
    p.vel = CEILING * 6 * u * (1 - u) / ASCENT_TIME;
    p.thrust = clamp(1.15 * (1 - u * 0.65), 0, 1);
    if (u >= 1) { p.phase = 'hold'; p.t = 0; p.vel = 0; p.thrust = 0.05; }
  } else if (p.phase === 'hold') {
    p.alt = CEILING; p.vel = 0;
    p.cruiseVel = damp(p.cruiseVel, 0, 0.7, dtReal);
    p.thrust = damp(p.thrust, 0.04, 1.5, dtReal);
  } else if (p.phase === 'cruise') {
    p.alt = CEILING;
    const done = cruiseTowards(destStop(), dt);
    p.thrust = done ? 0.05 : 1;
    if (done) {
      if (p.dest === 'quasar') { p.phase = 'hold'; toast('Пришли к квазару'); }
      else arriveAtWorld(p.dest);          // у планеты сразу идём на посадку
    }
  } else if (p.phase === 'home') {
    if (p.cruise > 1) {
      p.alt = CEILING;
      p.thrust = 1;
      if (cruiseTowards(0, dt)) p.t = 0;
    } else {
      p.cruise = 0; p.cruiseVel = 0;
      const u = clamp(p.t / DESCENT_TIME, 0, 1);
      p.alt = CEILING * (1 - u * u * (3 - 2 * u));
      p.vel = -CEILING * 6 * u * (1 - u) / DESCENT_TIME;
      p.thrust = clamp(0.25 + u * 0.75, 0, 1);
      if (u >= 1) { rocketReset(); toast('Посадка'); }
    }
  }

  // перегрузка: на крейсере это честные 100 g, на подъёме — своё ускорение
  const accel = ((p.vel - prevVel) + (p.cruiseVel - prevCruise)) / Math.max(dt, 1e-3);
  // на земле к тяге добавляется вес, в космосе перегрузка — это чистое ускорение
  const gRaw = Math.abs(accel) / 9.81 + (1 - spaceAmount);
  p.gforce = damp(p.gforce, clamp(gRaw, 0, 101), 3, dtReal);
  p.seatPush = damp(p.seatPush, clamp((Math.min(p.gforce, 3) - 1) * 0.09, -0.05, 0.18), 4, dtReal);

  /* Корабль в мире не улетает: два миллиарда метров не помещаются в
     точность float32 — картинку начинало трясти. Крейсер живёт отдельным
     числом, а в сцене мы висим на потолке подъёма. */
  p.pos[0] = PAD.x;
  p.pos[1] = PAD.y + p.alt;
  p.pos[2] = PAD.z;

  const toQuasar = p.phase === 'cruise' || (p.cruise > 1 ? 1 : 0);
  const aim = damp(p.aimBlend || 0, toQuasar ? 1 : 0, 0.8, dtReal);
  p.aimBlend = aim;
  const ux = lerp(0, SUN[0], aim), uy = lerp(1, SUN[1], aim), uz = lerp(0, SUN[2], aim);
  const ul = Math.hypot(ux, uy, uz) || 1;
  p.up[0] = ux / ul; p.up[1] = uy / ul; p.up[2] = uz / ul;

  m4arrow(p.model, p.pos, p.up, 1, 1);
  for (let i = 0; i < 3; i++) p.cockpit[i] = p.pos[i] + p.up[i] * (6.9 - p.seatPush);

  spaceAmount = smoothstep(15000, 20000, p.alt);
  planetFade = smoothstep(500, 1500, p.alt);

  // квазар растёт по угловому размеру: asin(R / расстояние)
  const toQ = p.dest === 'quasar';
  const range = Math.max(toQ ? quasarRange() : QUASAR_DIST, QUASAR_R * 1.05);
  const angNow = Math.asin(clamp(QUASAR_R / range, 0, 0.999));
  const angFar = Math.asin(QUASAR_R / QUASAR_DIST);
  quasarZoom = clamp(angNow / angFar, 1, 60);
  // рябь пространства — только ближе 200 000 км
  quasarLens = smoothstep(LENS_START, QUASAR_R * 2.2, range);
  // соседняя планета в своей стороне неба растёт по тому же закону
  gammaAng = Math.asin(clamp(GAMMA.R / Math.max(gammaRange(), GAMMA.R * 1.02), 0, 0.9995));
}

/* ---------------- геометрия ракеты и площадки ---------------- */

/**
 * Корпус, плавники, сопло и рёбра фонаря кабины (стекла нет — видно наружу).
 * `mode = 'full'` — вид снаружи; `mode = 'cockpit'` — то, что остаётся, когда
 * сидишь внутри: фонарь, панель, кресло. Глухой бак не рисуем, иначе пилот
 * смотрит вниз и видит собственную обшивку вместо Земли.
 */
function buildRocket(mode) {
  const inside = mode === 'cockpit';
  const m = meshBuilder();
  const hull = [0.82, 0.84, 0.88];
  const hullDark = [0.55, 0.57, 0.62];
  const red = [0.78, 0.26, 0.20];
  const dark = [0.24, 0.24, 0.28];
  const glassRib = [0.40, 0.42, 0.48];

  const tube = (y0, y1, r0, r1, color, seg = 16) => {
    for (let i = 0; i < seg; i++) {
      const a0 = (i / seg) * TAU, a1 = ((i + 1) / seg) * TAU;
      const A = [Math.cos(a0) * r0, y0, Math.sin(a0) * r0];
      const B = [Math.cos(a1) * r0, y0, Math.sin(a1) * r0];
      const C = [Math.cos(a1) * r1, y1, Math.sin(a1) * r1];
      const D = [Math.cos(a0) * r1, y1, Math.sin(a0) * r1];
      m.quad(A, B, C, D, color);
    }
  };

  if (!inside) {
    tube(-0.2, 0.5, 1.25, 1.15, dark);        // юбка
    tube(0.5, 4.6, 1.15, 1.15, hull);         // бак
    tube(4.6, 5.0, 1.15, 1.05, red);          // поясок
    tube(5.0, 6.2, 1.05, 0.95, hull);         // приборный отсек
    tube(6.2, 6.5, 0.95, 0.92, hullDark);     // обод фонаря

    // сопло
    tube(-1.1, -0.2, 0.55, 1.05, dark);
    tube(-1.35, -1.1, 0.75, 0.55, [0.35, 0.22, 0.16]);
  } else {
    // прозрачный пол: только тонкий обод под ногами
    tube(6.44, 6.52, 0.94, 0.92, hullDark);
  }

  // рёбра фонаря: восемь дуг к вершине
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * TAU;
    const nodes = [];
    for (let k = 0; k <= 5; k++) {
      const t = k / 5, ph = t * Math.PI * 0.5;
      nodes.push([Math.cos(a) * 0.92 * Math.cos(ph), 6.5 + Math.sin(ph) * 2.0, Math.sin(a) * 0.92 * Math.cos(ph)]);
    }
    m.rope(nodes, [0.045, 0.040, 0.035, 0.030, 0.026, 0.022], glassRib, 5);
  }
  // кольцевые рёбра фонаря
  for (const ph of [0.30, 0.62]) {
    const nodes = [];
    for (let k = 0; k <= 16; k++) {
      const a = (k / 16) * TAU;
      nodes.push([Math.cos(a) * 0.92 * Math.cos(ph), 6.5 + Math.sin(ph) * 2.0, Math.sin(a) * 0.92 * Math.cos(ph)]);
    }
    m.rope(nodes, nodes.map(() => 0.022), glassRib, 5);
  }
  // шпиль
  m.rope([[0, 8.5, 0], [0, 9.4, 0]], [0.06, 0.012], hullDark, 6);

  // приборная панель: низкий поясок у самого обода, чтобы не загораживать вид
  for (let i = 0; i < 5; i++) {
    const a = -0.9 + i * 0.45;
    m.box(Math.cos(a) * 0.84, 6.50, Math.sin(a) * 0.84, 0.10, 0.03, 0.05, -a, [0.18, 0.19, 0.22]);
  }
  m.rope([[Math.cos(-1.1) * 0.86, 6.55, Math.sin(-1.1) * 0.86], [Math.cos(1.1) * 0.86, 6.55, Math.sin(1.1) * 0.86]],
         [0.05, 0.05], hullDark, 6);

  // кресло пилота: спинка, подголовник, подлокотники и подушка
  const seat = [0.26, 0.27, 0.31];
  const pad = [0.34, 0.30, 0.28];
  m.box(0, 6.16, 0.30, 0.34, 0.05, 0.26, 0, seat);          // сиденье
  m.box(0, 6.62, 0.52, 0.34, 0.42, 0.05, 0, seat);          // спинка
  m.box(0, 7.08, 0.50, 0.17, 0.11, 0.06, 0, pad);           // подголовник
  for (const s of [-1, 1]) m.box(s * 0.38, 6.42, 0.28, 0.05, 0.05, 0.24, 0, seat);
  m.box(0, 6.20, 0.30, 0.30, 0.03, 0.22, 0, pad);           // подушка
  if (inside) m.box(0, 6.32, 0.30, 0.08, 0.14, 0.08, 0, seat);   // нога кресла

  // четыре плавника
  if (!inside) for (let i = 0; i < 4; i++) {
    const a = (i / 4) * TAU + 0.4;
    const ca = Math.cos(a), sa = Math.sin(a);
    const A = [ca * 1.1, 0.2, sa * 1.1], B = [ca * 1.1, 2.6, sa * 1.1];
    const C = [ca * 2.5, -0.5, sa * 2.5];
    m.tri(A, B, C, red); m.tri(A, C, B, red);
  }
  return m.pack();
}

/** Стартовая площадка с фермой — попадает в общую статику. */
function addPad(api) {
  const m = { tri: (a, b, c, col) => api.pushTri(a, b, c, col) };
  const steel = [0.42, 0.43, 0.47];
  const plate = [0.34, 0.33, 0.32];
  const P = (x, y, z) => [PAD.x + x, PAD.y + y, PAD.z + z];

  // бетонная площадка
  for (let i = 0; i < 12; i++) {
    const a0 = (i / 12) * TAU, a1 = ((i + 1) / 12) * TAU;
    m.tri(P(0, 0.06, 0), P(Math.cos(a0) * 4.2, 0.06, Math.sin(a0) * 4.2), P(Math.cos(a1) * 4.2, 0.06, Math.sin(a1) * 4.2), plate);
    m.tri(P(Math.cos(a0) * 4.2, 0.06, Math.sin(a0) * 4.2), P(Math.cos(a0) * 4.2, -0.2, Math.sin(a0) * 4.2),
          P(Math.cos(a1) * 4.2, 0.06, Math.sin(a1) * 4.2), [0.28, 0.27, 0.26]);
  }
  // ферма обслуживания
  const legs = [[3.2, 3.2], [3.2, 1.6], [4.6, 3.2], [4.6, 1.6]];
  for (let k = 0; k < 4; k++) {
    const [lx, lz] = legs[k];
    for (let s = 0; s < 7; s++) {
      const y0 = s * 1.3, y1 = y0 + 1.3;
      const w = 0.06;
      m.tri(P(lx - w, y0, lz), P(lx + w, y0, lz), P(lx + w, y1, lz), steel);
      m.tri(P(lx - w, y0, lz), P(lx + w, y1, lz), P(lx - w, y1, lz), steel);
      m.tri(P(lx, y0, lz - w), P(lx, y0, lz + w), P(lx, y1, lz + w), steel);
      m.tri(P(lx, y0, lz - w), P(lx, y1, lz + w), P(lx, y1, lz - w), steel);
    }
  }
  for (let s = 1; s <= 6; s++) {
    const y = s * 1.5;
    m.tri(P(3.2, y, 3.2), P(4.6, y, 3.2), P(4.6, y, 1.6), steel);
    m.tri(P(3.2, y, 3.2), P(4.6, y, 1.6), P(3.2, y, 1.6), steel);
  }
}

/* ---------------- планета и соседи ---------------- */

/** Единичная сфера с UV — для планеты и её соседей. */
function buildSphere(seg = 40, ring = 24) {
  const pos = [], uv = [], idx = [];
  for (let j = 0; j <= ring; j++) {
    const ph = (j / ring) * Math.PI - Math.PI / 2;
    for (let i = 0; i <= seg; i++) {
      const th = (i / seg) * TAU;
      pos.push(Math.cos(ph) * Math.cos(th), Math.sin(ph), Math.cos(ph) * Math.sin(th));
      uv.push(i / seg, j / ring);
    }
  }
  for (let j = 0; j < ring; j++) {
    for (let i = 0; i < seg; i++) {
      const a = j * (seg + 1) + i, b = a + seg + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return {
    pos: buffer(new Float32Array(pos)),
    uv: buffer(new Float32Array(uv)),
    idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER),
    count: idx.length,
  };
}

/* ---------------- карта планеты ----------------
   Печём равнопромежуточную карту 2048×1024 прямо на видеокарте: на
   процессоре такой размер с домен-варпом занял бы несколько секунд.
   В RGB — цвет биома с рельефной подсветкой, в альфе — высота суши
   (ноль на воде): по ней шейдер планеты дорисовывает мелкие детали. */

/* Высота суши как функция направления. Домен-варп даёт рваные,
   непохожие на шум берега; хребтовый слой поднимает горные цепи. */
const PLANET_HEIGHT = `
uniform vec3 uHome;
uniform float uSeed;
uniform float uSea;
uniform float uLandBias;

float elevation(vec3 d) {
  vec3 sd = d + vec3(uSeed);
  vec3 warp = vec3(fbm3(sd * 1.30 + vec3(3.10)),
                   fbm3(sd * 1.30 + vec3(9.70)),
                   fbm3(sd * 1.30 + vec3(17.30))) - 0.5;
  float base = fbm6(sd * 1.85 + warp * 1.45);
  // материк под стартовой площадкой, чтобы с высоты был берег и лес
  base += 0.14 * smoothstep(0.28, 0.99, dot(d, uHome));
  base += uLandBias;
  // горные цепи только на суше и тем выше, чем дальше от уровня моря
  float mount = ridged(sd * 2.9 + warp * 0.8);
  base += smoothstep(uSea, uSea + 0.16, base) * (mount - 0.55) * 0.26;
  return base;
}
`;

/**
 * Рисует карту планеты в текстуру. `style` — 0 живой мир, 1 выжженный
 * полигон. Возвращает объект с готовой мип-текстурой.
 */
function makePlanetTexture(opts) {
  const o = Object.assign({ seed: 0, style: 0, sea: 0.50, home: [0, Math.sin(0.42), Math.cos(0.42)],
                            landBias: 0 }, opts || {});
  const max = gl.getParameter(gl.MAX_TEXTURE_SIZE);
  const W = max >= 2048 ? 2048 : 1024, H = W >> 1;

  const prog = program(`
attribute vec2 aPos;
varying vec2 vUv;
void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`,
    PRECISION + PLANET_NOISE + PLANET_HEIGHT + `
varying vec2 vUv;
uniform float uStyle;

void main() {
  float lon = (vUv.x - 0.5) * 6.2831853;
  float lat = (vUv.y - 0.5) * 3.1415927;
  float cl = cos(lat);
  vec3 d = vec3(cl * cos(lon), sin(lat), cl * sin(lon));

  float e = elevation(d);
  float land = smoothstep(uSea - 0.004, uSea + 0.004, e);      // мягкая береговая линия
  float hi = max(e - uSea, 0.0) / 0.34;                        // высота над уровнем моря, 0..1+

  // рельефная подсветка: наклон поверхности по двум сдвигам направления
  vec3 tx = normalize(cross(d, vec3(0.0, 1.0, 0.0)) + vec3(1e-4));
  vec3 ty = cross(d, tx);
  float dx = elevation(normalize(d + tx * 0.004)) - elevation(normalize(d - tx * 0.004));
  float dy = elevation(normalize(d + ty * 0.004)) - elevation(normalize(d - ty * 0.004));
  float relief = clamp(0.5 + (dx * 1.9 - dy * 1.1) * 15.0, 0.0, 1.0);

  // климат: тепло падает к полюсам и с высотой, влага — своё поле,
  // прибитое к побережьям. Оба поля непрерывны, значит и биомы тоже.
  // широта давит на тепло резко к полюсам: умеренный пояс широкий,
  // шапки начинаются около шестидесятой параллели
  float temp = 1.0 - pow(abs(d.y), 3.5) * 1.75 - hi * 0.62
             + (fbm3(d * 2.6 + vec3(31.0)) - 0.5) * 0.26;
  float moist = fbm6(d * 2.15 + vec3(57.0)) * 0.82
              + (1.0 - smoothstep(0.0, 0.09, e - uSea)) * 0.26
              + (0.5 - abs(d.y)) * 0.10
              - 0.34 * smoothstep(0.50, 0.99, dot(d, uHome));   // дома — сухая Невада

  /* --- вода --- */
  float depth = clamp((uSea - e) / 0.26, 0.0, 1.0);
  vec3 abyss   = vec3(0.008, 0.048, 0.135);
  vec3 ocean   = vec3(0.020, 0.115, 0.290);
  vec3 shelf   = vec3(0.055, 0.290, 0.470);
  vec3 lagoon  = vec3(0.180, 0.560, 0.610);
  vec3 water = mix(lagoon, shelf, smoothstep(0.02, 0.10, depth));
  water = mix(water, ocean, smoothstep(0.10, 0.34, depth));
  water = mix(water, abyss, smoothstep(0.34, 0.86, depth));
  // рябь открытой воды, чтобы океан не был плоской заливкой
  water *= 0.93 + 0.14 * fbm3(d * 46.0 + vec3(5.0));
  // припай: у полюсов океан замерзает, край рваный
  float seaIce = smoothstep(0.06, -0.10, temp + (fbm3(d * 7.0 + vec3(3.0)) - 0.5) * 0.20);
  water = mix(water, vec3(0.855, 0.895, 0.930), seaIce);

  /* --- суша: биомы смешиваются по теплу и влаге --- */
  vec3 sand    = vec3(0.760, 0.680, 0.450);
  vec3 desert  = vec3(0.720, 0.560, 0.330);
  vec3 steppe  = vec3(0.560, 0.530, 0.290);
  vec3 grass   = vec3(0.330, 0.470, 0.210);
  vec3 forest  = vec3(0.130, 0.330, 0.140);
  vec3 jungle  = vec3(0.075, 0.300, 0.105);
  vec3 taiga   = vec3(0.150, 0.290, 0.215);
  vec3 tundra  = vec3(0.450, 0.450, 0.390);
  vec3 rock    = vec3(0.420, 0.395, 0.365);
  vec3 snow    = vec3(0.930, 0.945, 0.965);

  float wet = smoothstep(0.34, 0.62, moist);
  vec3 warmBiome = mix(desert, mix(grass, jungle, smoothstep(0.55, 0.85, moist)), wet);
  vec3 midBiome  = mix(steppe, forest, wet);
  vec3 coldBiome = mix(tundra, taiga, wet);
  vec3 ground = mix(coldBiome, midBiome, smoothstep(0.06, 0.34, temp));
  ground = mix(ground, warmBiome, smoothstep(0.40, 0.68, temp));

  // растительная пятнистость — рощи и проплешины, а не ровный цвет
  float patch = fbm6(d * 11.0 + vec3(77.0));
  ground *= 0.86 + 0.30 * patch;

  // голые склоны и снежные шапки — по высоте и теплу, без ступенек
  float bare = smoothstep(0.52, 0.95, hi) * smoothstep(0.30, 0.62, 1.0 - patch * 0.6);
  ground = mix(ground, rock * (0.80 + 0.40 * patch), bare);
  float snowLine = smoothstep(0.16, -0.10, temp);
  ground = mix(ground, snow, snowLine);

  // реки: узкие гребни хребтового шума на суше, сходящие к морю
  float riv = ridged(d * 5.4 + vec3(101.0));
  float river = smoothstep(0.955, 0.995, riv) * smoothstep(0.02, 0.16, e - uSea)
              * (1.0 - snowLine) * smoothstep(0.30, 0.55, moist);
  ground = mix(ground, mix(shelf, lagoon, 0.5), river * 0.85);

  // пляж — там, где суша только-только вышла из воды
  float beach = (1.0 - smoothstep(0.0, 0.012, e - uSea)) * (1.0 - snowLine);
  ground = mix(ground, sand, beach * 0.85);

  /* --- выжженный полигон: та же география, мёртвая палитра --- */
  if (uStyle > 0.5) {
    float g = dot(ground, vec3(0.36, 0.48, 0.16));
    vec3 ash = mix(vec3(0.215, 0.190, 0.170), vec3(0.520, 0.455, 0.395), g);
    ash = mix(ash, vec3(0.400, 0.235, 0.155), smoothstep(0.30, 0.75, patch) * 0.45);
    ground = ash;
    water = mix(vec3(0.115, 0.105, 0.095), vec3(0.230, 0.215, 0.185), 1.0 - depth);
  }

  vec3 col = mix(water, ground, land);
  // рельеф подсвечиваем только на суше — на воде он выглядел бы царапинами
  col *= mix(1.0, 0.72 + 0.56 * relief, land * 0.85);

  // в альфе — «сухость»: ноль на воде, 0.25 у уреза, единица на вершинах
  gl_FragColor = vec4(col, land * (0.25 + 0.75 * clamp(hi, 0.0, 1.0)));
}`);

  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, W, H, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);

  const fb = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);

  const quad = buffer(new Float32Array([-1, -1, 3, -1, -1, 3]));
  gl.viewport(0, 0, W, H);
  gl.disable(gl.DEPTH_TEST);
  gl.disable(gl.BLEND);
  gl.useProgram(prog.prog);
  attrib(prog.a.aPos, quad, 2);
  gl.uniform3fv(prog.u.uHome, o.home);
  gl.uniform1f(prog.u.uSeed, o.seed);
  gl.uniform1f(prog.u.uSea, o.sea);
  gl.uniform1f(prog.u.uLandBias, o.landBias);
  gl.uniform1f(prog.u.uStyle, o.style);
  gl.drawArrays(gl.TRIANGLES, 0, 3);

  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.deleteFramebuffer(fb);
  gl.deleteBuffer(quad);
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.enable(gl.DEPTH_TEST);
  return tex;
}

/** Соседи по системе: направление на небе, угловой размер, цвет, кольцо. */
const NEIGHBOURS = [
  { dir: [0.62, 0.28, -0.73], ang: 0.055, col: [0.78, 0.56, 0.34], ring: true },
  { dir: [-0.80, 0.16, -0.58], ang: 0.030, col: [0.52, 0.62, 0.80], ring: false },
  { dir: [0.24, 0.42, 0.87], ang: 0.020, col: [0.74, 0.38, 0.30], ring: false },
  { dir: [-0.35, 0.62, 0.70], ang: 0.013, col: [0.70, 0.72, 0.74], ring: false },
];

/* ---------------- мусор, падающий в дыру ---------------- */

const DEBRIS = [];
for (let i = 0; i < 7; i++) {
  DEBRIS.push({ r: 12 + Math.random() * 26, a: Math.random() * TAU, tilt: (Math.random() - 0.5) * 1.1,
                spin: 0.4 + Math.random() * 0.8, size: 0.22 + Math.random() * 0.35, stretch: 1 });
}

function updateDebris(dt) {
  for (const d of DEBRIS) {
    const fall = 1.6 + 26 / Math.max(d.r, 2);          // ближе к дыре — быстрее
    d.r -= dt * fall;
    d.a += dt * d.spin * (1 + 22 / Math.max(d.r, 2));
    // приливная растяжка: обратно пропорциональна расстоянию до горизонта
    d.stretch = clamp(1 + 26 / Math.max(d.r - BH.rs * 0.85, 0.35), 1, 26);
    if (d.r <= BH.rs * 1.02) {
      d.r = 30 + Math.random() * 18;
      d.a = Math.random() * TAU;
      d.tilt = (Math.random() - 0.5) * 1.1;
      d.size = 0.22 + Math.random() * 0.35;
    }
  }
}

/** Положение обломка и матрица с вытягиванием вдоль радиуса. */
function debrisMatrix(d, out) {
  const ct = Math.cos(d.tilt), st = Math.sin(d.tilt);
  const x = Math.cos(d.a) * d.r * ct, y = st * d.r, z = Math.sin(d.a) * d.r * ct;
  const p = [BH.pos[0] + x, BH.pos[1] + y, BH.pos[2] + z];
  const l = Math.hypot(x, y, z) || 1;
  const n = [-x / l, -y / l, -z / l];                   // «вниз» — к дыре
  // длина растёт, поперечник сжимается — объём примерно сохраняется
  m4arrow(out, p, n, d.size * d.stretch, d.size / Math.sqrt(d.stretch));
  return out;
}

/* ---------------- рождение и аннигиляция пар ---------------- */

const PAIRS = { list: [], pos: null, col: null, buf: null, cbuf: null, n: 0 };
const PAIR_MAX = 30;

const PAIR_KINDS = [
  { a: [1.0, 0.95, 0.72], b: [1.0, 0.95, 0.72], life: 0.9 },   // фотоны
  { a: [0.42, 0.78, 1.0], b: [1.0, 0.45, 0.42], life: 1.2 },   // электрон и позитрон
  { a: [0.72, 0.50, 1.0], b: [1.0, 0.62, 0.35], life: 0.8 },   // мюонная пара
  { a: [0.50, 1.0, 0.66], b: [1.0, 0.52, 0.86], life: 0.7 },   // кварк и антикварк
];

function initPairs() {
  PAIRS.pos = new Float32Array(PAIR_MAX * 2 * 3);
  PAIRS.col = new Float32Array(PAIR_MAX * 2 * 4);
  PAIRS.buf = gl.createBuffer();
  PAIRS.cbuf = gl.createBuffer();
}

function spawnPair() {
  const kind = PAIR_KINDS[Math.floor(Math.random() * PAIR_KINDS.length)];
  const th = Math.random() * TAU, ph = Math.acos(2 * Math.random() - 1);
  const r = BH.rs * (1.02 + Math.random() * 0.30);
  const o = [Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th)];
  // ось разлёта — поперёк радиуса
  let ax = [-o[1], o[0], o[2] * 0.3];
  const al = Math.hypot(ax[0], ax[1], ax[2]) || 1;
  ax = [ax[0] / al, ax[1] / al, ax[2] / al];
  PAIRS.list.push({
    o, ax, r, kind,
    t: 0,
    life: kind.life * (0.7 + Math.random() * 0.7),
    // изредка один партнёр уходит наружу, второй проваливается за горизонт
    hawking: Math.random() < 0.22,
  });
}

function updatePairs(dt, camDist) {
  if (camDist > 55) { PAIRS.n = 0; PAIRS.list.length = 0; return; }
  const want = Math.round(lerp(PAIR_MAX, 6, smoothstep(18, 55, camDist)));
  while (PAIRS.list.length < want) spawnPair();

  let k = 0;
  for (let i = PAIRS.list.length - 1; i >= 0; i--) {
    const p = PAIRS.list[i];
    p.t += dt;
    if (p.t > p.life || PAIRS.list.length > want) { PAIRS.list.splice(i, 1); continue; }

    const u = p.t / p.life;
    const sep = p.hawking ? u * 0.85 : Math.sin(u * Math.PI) * 0.34;   // разлетелись и сошлись
    const fade = p.hawking ? (1 - u) : Math.sin(u * Math.PI);
    const rr = p.r * (p.hawking ? 1 + u * 0.35 : 1);

    for (const s of [1, -1]) {
      if (k >= PAIR_MAX * 2) break;
      // партнёр, падающий за горизонт, притормаживает и краснеет — гравитационное смещение
      const pull = p.hawking && s < 0 ? -u * 0.35 : 0;
      const rad = rr + pull;
      const j = k * 3;
      PAIRS.pos[j] = BH.pos[0] + p.o[0] * rad + p.ax[0] * sep * s;
      PAIRS.pos[j + 1] = BH.pos[1] + p.o[1] * rad + p.ax[1] * sep * s;
      PAIRS.pos[j + 2] = BH.pos[2] + p.o[2] * rad + p.ax[2] * sep * s;
      const c = s > 0 ? p.kind.a : p.kind.b;
      const q = k * 4;
      PAIRS.col[q] = c[0]; PAIRS.col[q + 1] = c[1]; PAIRS.col[q + 2] = c[2];
      PAIRS.col[q + 3] = fade;
      k++;
    }
  }
  PAIRS.n = k;
  if (!k) return;
  gl.bindBuffer(gl.ARRAY_BUFFER, PAIRS.buf);
  gl.bufferData(gl.ARRAY_BUFFER, PAIRS.pos.subarray(0, k * 3), gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, PAIRS.cbuf);
  gl.bufferData(gl.ARRAY_BUFFER, PAIRS.col.subarray(0, k * 4), gl.DYNAMIC_DRAW);
}
