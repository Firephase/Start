/* ============================================================
   Полигон Гамма: вторая планета, перелёт, посадка и ядерные испытания
   ============================================================ */

/** Соседняя планета: висит в своей стороне неба, лететь 400 000 км. */
const GAMMA = {
  dir: (() => { const v = [0.61, 0.30, 0.73]; const l = Math.hypot(v[0], v[1], v[2]);
                return [v[0] / l, v[1] / l, v[2] / l]; })(),
  dist: 4.0e8,
  R: 2.4e6,
  home: [Math.sin(0.9), Math.sin(-0.18), Math.cos(0.9) * Math.cos(0.18)],
  name: 'Полигон Гамма',
};
GAMMA.stop = GAMMA.dist - GAMMA.R - 3.0e5;   // зависаем в трёхстах километрах

/* Куда летим и на чём стоим. Оба мира пользуются одним ландшафтом:
   меняются палитра, небо и набор объектов. */
const WORLDS = {
  earth: { title: 'Невада · три поверхности', ground: [1.00, 1.00, 1.00], haze: [1.00, 1.00, 1.00] },
  gamma: { title: 'Полигон Гамма · испытания', ground: [0.74, 0.62, 0.57], haze: [0.86, 0.76, 0.70] },
};

let gammaAng = 0;        // угловой радиус Гаммы с борта, радианы
let gammaTex = null;     // карта Гаммы, печётся при первом взгляде

/** Расстояние от корабля до центра Гаммы. */
const gammaRange = () => GAMMA.dist - (ROCKET.dest === 'quasar' ? 0 : ROCKET.cruise);

/** Куда целится крейсер сейчас. */
function destStop() { return ROCKET.dest === 'quasar' ? QUASAR_STOP : GAMMA.stop; }

/** Человеческое имя цели. */
function destName() {
  if (ROCKET.dest === 'quasar') return 'квазар';
  return ROCKET.dest === 'gamma' ? GAMMA.name : 'Земля';
}

/** Список доступных целей зависит от того, где мы стоим. */
function destOptions() {
  return game.world === 'earth' ? ['quasar', 'gamma'] : ['quasar', 'earth'];
}

function cycleDest() {
  const opts = destOptions();
  const i = opts.indexOf(ROCKET.dest);
  ROCKET.dest = opts[(i + 1) % opts.length];
}

/** Следы испытаний остаются на своей планете и не летят с нами. */
function clearTests() {
  BLAST.live = false; BLAST.bomb = null; BLAST.t = 0; BLAST.ring = 0;
  BLAST.flash = 0; BLAST.shake = 0;
  PARTS.length = 0;
  FIRES.length = 0;
  for (const c of CRATERS) { gl.deleteBuffer(c.pos); gl.deleteBuffer(c.fade); gl.deleteBuffer(c.idx); }
  CRATERS.length = 0;
  bombReadyAt = 0;
  if (fireSnd.src) { try { fireSnd.src.stop(); } catch (e) {} fireSnd.src = null; fireSnd.gain = null; }
}

/** Прилетели к другой планете — меняем мир под ногами и садимся. */
function arriveAtWorld(world) {
  clearTests();
  if (world === 'gamma') SITH.greeted = false;
  game.world = world;
  ROCKET.cruise = 0;
  ROCKET.cruiseVel = 0;
  ROCKET.phase = 'home';
  ROCKET.t = 0;
  ROCKET.dest = world === 'earth' ? 'gamma' : 'earth';
  applyWorld();
  toast(world === 'gamma' ? 'Полигон Гамма — идём на посадку' : 'Земля — идём на посадку');
}

/** Заголовок, палитра и набор объектов под текущий мир. */
function applyWorld() {
  const w = WORLDS[game.world];
  const sub = document.getElementById('plaque-sub');
  if (sub) sub.textContent = w.title.toUpperCase();
  syncBombUI();
}

/* ---------------- материя взрыва ---------------- */

/* Мягкие билборды: из них и огненный шар, и дым, и пыль, и пожары.
   Один буфер перестраивается каждый кадр — частиц меньше тысячи. */
const puffProg = program(`
attribute vec3 aCenter;
attribute vec2 aCorner;
attribute float aSize;
attribute vec4 aColor;
uniform mat4 uVP;
uniform vec3 uRight;
uniform vec3 uUp;
varying vec2 vC;
varying vec4 vCol;
void main() {
  vC = aCorner; vCol = aColor;
  vec3 p = aCenter + uRight * (aCorner.x * aSize) + uUp * (aCorner.y * aSize);
  gl_Position = uVP * vec4(p, 1.0);
}`, PRECISION + `
varying vec2 vC;
varying vec4 vCol;
void main() {
  float r2 = dot(vC, vC);
  if (r2 > 1.0) discard;
  // плотная середина и мягкий край: из ватных пятен облако не собирается
  float a = 1.0 - smoothstep(0.30, 1.0, sqrt(r2));
  gl_FragColor = vec4(vCol.rgb, vCol.a * a);
}`);

/* Плоские кольца и пятна по земле: ударная волна и воронка. */
const flatProg = program(`
attribute vec3 aPos;
attribute float aFade;
uniform mat4 uVP;
uniform mat4 uModel;
varying float vF;
void main() { vF = aFade; gl_Position = uVP * uModel * vec4(aPos, 1.0); }`, PRECISION + `
varying float vF;
uniform vec4 uColor;
void main() { gl_FragColor = vec4(uColor.rgb, uColor.a * vF); }`);

const PUFF_MAX = 900;
const puffBuf = {
  center: new Float32Array(PUFF_MAX * 4 * 3),
  corner: new Float32Array(PUFF_MAX * 4 * 2),
  size: new Float32Array(PUFF_MAX * 4),
  color: new Float32Array(PUFF_MAX * 4 * 4),
  idx: new Uint16Array(PUFF_MAX * 6),
  gCenter: gl.createBuffer(), gCorner: gl.createBuffer(),
  gSize: gl.createBuffer(), gColor: gl.createBuffer(), gIdx: gl.createBuffer(),
};
for (let i = 0; i < PUFF_MAX; i++) {
  const c = i * 8, o = i * 4;
  puffBuf.corner[c + 0] = -1; puffBuf.corner[c + 1] = -1;
  puffBuf.corner[c + 2] = 1;  puffBuf.corner[c + 3] = -1;
  puffBuf.corner[c + 4] = 1;  puffBuf.corner[c + 5] = 1;
  puffBuf.corner[c + 6] = -1; puffBuf.corner[c + 7] = 1;
  const k = i * 6;
  puffBuf.idx[k] = o; puffBuf.idx[k + 1] = o + 1; puffBuf.idx[k + 2] = o + 2;
  puffBuf.idx[k + 3] = o; puffBuf.idx[k + 4] = o + 2; puffBuf.idx[k + 5] = o + 3;
}
gl.bindBuffer(gl.ARRAY_BUFFER, puffBuf.gCorner);
gl.bufferData(gl.ARRAY_BUFFER, puffBuf.corner, gl.STATIC_DRAW);
gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, puffBuf.gIdx);
gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, puffBuf.idx, gl.STATIC_DRAW);

/** Один пул на всё: у частицы есть признак «светится» — рисуем в два прохода. */
const PARTS = [];

function spawnPuff(x, y, z, vx, vy, vz, size, grow, life, col, glow, drag = 0.62, buoy = 0) {
  if (PARTS.length >= PUFF_MAX) PARTS.shift();
  PARTS.push({ x, y, z, vx, vy, vz, size, grow, life, age: 0, col, glow, drag, buoy,
               spin: Math.random() * TAU });
}

function updateParts(dt) {
  for (let i = PARTS.length - 1; i >= 0; i--) {
    const p = PARTS[i];
    p.age += dt;
    if (p.age >= p.life) { PARTS.splice(i, 1); continue; }
    const k = Math.exp(-p.drag * dt);
    p.vx *= k; p.vz *= k;
    p.vy = (p.vy + p.buoy * dt) * k;
    p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt;
    p.size += p.grow * dt;
  }
}

/* ---------------- пожары и воронки ---------------- */

const FIRES = [];
const CRATERS = [];

/* ---------------- сам взрыв ---------------- */

const BLAST = {
  live: false,
  t: 0,
  pos: [0, 0, 0],
  ring: 0,          // радиус ударной волны, метры
  ringV: 340,
  bomb: null,       // {p, v} пока летит
  flash: 0,         // засветка экрана, 0..1
  shake: 0,
  soundAt: -1,      // когда до нас дойдёт звук
  dist: 0,
};

const BOMB_COOLDOWN = 12;
let bombReadyAt = 0;

/** Можно ли сейчас бросать: только на полигоне, пешком и не подряд. */
function bombAllowed() {
  return game.world === 'gamma' && game.mode === 'walk' && !game.tent.inside
    && !BLAST.bomb && game.proper >= bombReadyAt;
}

function dropBomb() {
  if (!bombAllowed()) return;
  /* Изделие уходит на мишенное поле — оно в полутора километрах от
     площадки и в четырёх от города. Скорость подбираем так, чтобы
     баллистика привела заряд ровно в цель за назначенное время. */
  const tx = G.zero.x + (Math.random() - 0.5) * 260;
  const tz = G.zero.z + (Math.random() - 0.5) * 260;
  const sx = CAR.inside ? CAR.x : cam.x, sz = CAR.inside ? CAR.z : cam.z;
  const sy = (CAR.inside ? CAR.y + 1.4 : cam.y) + 0.4;
  const ty = groundH(tx, tz) + 140;                 // воздушный подрыв
  const dist = Math.hypot(tx - sx, tz - sz);
  const T = clamp(dist / 380, 4, 11);
  BLAST.bomb = {
    p: [sx, sy, sz],
    v: [(tx - sx) / T, (ty - sy) / T + 0.5 * 9.81 * T, (tz - sz) / T],
    t: 0, fuse: T, trail: 0,
  };
  bombReadyAt = game.proper + BOMB_COOLDOWN;
  toast(`Изделие пошло — цель в ${(dist / 1000).toFixed(1)} км`);
  syncBombUI();
}

/** Детонация: тепловая вспышка, огненный шар, гриб, волна, пожары. */
function detonate(x, y, z) {
  BLAST.live = true;
  BLAST.t = 0;
  BLAST.pos[0] = x; BLAST.pos[1] = y; BLAST.pos[2] = z;
  BLAST.ring = 6; BLAST.ringV = 340;
  const px = CAR.inside ? CAR.x : cam.x, pz = CAR.inside ? CAR.z : cam.z;
  BLAST.dist = Math.hypot(px - x, cam.y - y, pz - z);
  BLAST.soundAt = BLAST.dist / 340;
  BLAST.hitDone = false;
  // тепловая вспышка: вблизи слепит полностью, из города — резкая засветка
  BLAST.flash = clamp(3400 / Math.max(BLAST.dist, 260), 0.55, 1);
  BLAST.flashHold = 0.22 + 0.55 * BLAST.flash;

  // воронка: тёмное пятно по рельефу, живёт до конца сеанса
  CRATERS.push(makeCrater(x, z, 210));
  if (CRATERS.length > 4) { const old = CRATERS.shift(); gl.deleteBuffer(old.pos); gl.deleteBuffer(old.fade); }

  // пожары вокруг: гуще к центру, реже к краю
  for (let i = 0; i < 70; i++) {
    const a = Math.random() * TAU;
    const r = 60 + Math.pow(Math.random(), 0.55) * 620;
    const fx = x + Math.cos(a) * r, fz = z + Math.sin(a) * r;
    FIRES.push({ x: fx, z: fz, y: groundH(fx, fz), r: 2.4 + Math.random() * 6.0,
                 life: 55 + Math.random() * 70, age: 0, seed: Math.random() * 100,
                 next: Math.random() * 0.2 });
  }
  if (FIRES.length > 220) FIRES.splice(0, FIRES.length - 220);

  soundNuke(BLAST.soundAt, BLAST.dist);
  syncBombUI();
}

/** Пятно выжженной земли: диск по рельефу, к краю сходит на нет. */
function makeCrater(cx, cz, R) {
  const seg = 40, rings = 5;
  const pos = [], fade = [], idx = [];
  pos.push(cx, groundH(cx, cz) + 0.16, cz); fade.push(1);
  for (let r = 1; r <= rings; r++) {
    const rr = R * r / rings;
    for (let i = 0; i < seg; i++) {
      const a = (i / seg) * TAU;
      const px = cx + Math.cos(a) * rr * (0.86 + 0.28 * Math.sin(a * 3.1 + r));
      const pz = cz + Math.sin(a) * rr * (0.86 + 0.28 * Math.cos(a * 2.7 - r));
      pos.push(px, groundH(px, pz) + 0.16, pz);
      fade.push(r === rings ? 0 : 1 - Math.pow(r / rings, 2.2) * 0.75);
    }
  }
  for (let i = 0; i < seg; i++) idx.push(0, 1 + i, 1 + (i + 1) % seg);
  for (let r = 0; r < rings - 1; r++) {
    const a0 = 1 + r * seg, a1 = 1 + (r + 1) * seg;
    for (let i = 0; i < seg; i++) {
      const j = (i + 1) % seg;
      idx.push(a0 + i, a1 + i, a1 + j, a0 + i, a1 + j, a0 + j);
    }
  }
  return { x: cx, z: cz, r: R, pos: buffer(new Float32Array(pos)), fade: buffer(new Float32Array(fade)),
           idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
}

/** Кольцо ударной волны строим заново каждый кадр — оно ползёт по рельефу. */
const shockRing = { pos: gl.createBuffer(), fade: gl.createBuffer(), idx: null, count: 0,
                    p: new Float32Array(64 * 3 * 3), f: new Float32Array(64 * 3) };
(() => {
  const seg = 64, idx = [];
  for (let i = 0; i < seg; i++) {
    const j = (i + 1) % seg;
    idx.push(i * 3, j * 3, j * 3 + 1, i * 3, j * 3 + 1, i * 3 + 1);
    idx.push(i * 3 + 1, j * 3 + 1, j * 3 + 2, i * 3 + 1, j * 3 + 2, i * 3 + 2);
  }
  shockRing.idx = buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER);
  shockRing.count = idx.length;
})();

function updateShockRing() {
  const seg = 64, R = BLAST.ring, w = Math.max(R * 0.09, 4);
  const cx = BLAST.pos[0], cz = BLAST.pos[2];
  for (let i = 0; i < seg; i++) {
    const a = (i / seg) * TAU, ca = Math.cos(a), sa = Math.sin(a);
    const rs = [R - w, R, R + w];
    for (let k = 0; k < 3; k++) {
      const x = cx + ca * rs[k], z = cz + sa * rs[k];
      const o = (i * 3 + k) * 3;
      shockRing.p[o] = x; shockRing.p[o + 1] = groundH(x, z) + 0.35; shockRing.p[o + 2] = z;
      shockRing.f[i * 3 + k] = k === 1 ? 1 : 0;
    }
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, shockRing.pos);
  gl.bufferData(gl.ARRAY_BUFFER, shockRing.p, gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, shockRing.fade);
  gl.bufferData(gl.ARRAY_BUFFER, shockRing.f, gl.DYNAMIC_DRAW);
}

/**
 * Один кадр жизни взрыва. Времена подобраны под «настоящую» картину:
 * доли секунды — белый шар, секунды — подъём и остывание, минуты — пожары.
 */
function updateBlast(dt) {
  // бомба в полёте
  if (BLAST.bomb) {
    const b = BLAST.bomb;
    b.t += dt;
    b.v[1] -= 9.81 * dt;
    for (let i = 0; i < 3; i++) b.p[i] += b.v[i] * dt;
    // инверсионный след, чтобы изделие было видно в полёте
    b.trail -= dt;
    if (b.trail <= 0) {
      b.trail = 0.045;
      spawnPuff(b.p[0], b.p[1], b.p[2], 0, 1.2, 0, 2.4, 3.6, 3.2, [0.78, 0.76, 0.74], 0, 0.3, 0.4);
    }
    const g = groundH(b.p[0], b.p[2]);
    if (b.t >= b.fuse || b.p[1] <= g + 0.5) {
      detonate(b.p[0], Math.max(b.p[1], g + 0.5), b.p[2]);
      BLAST.bomb = null;
    }
  }

  if (BLAST.live) {
    const t0 = BLAST.t;
    BLAST.t += dt;
    const t = BLAST.t;

    // ударная волна: тормозится об воздух, ниже скорости звука не падает
    BLAST.ringV = Math.max(700 * Math.exp(-t * 0.30), 60);
    BLAST.ring += BLAST.ringV * dt;

    // приход фронта: тряска, отброс, оглушение, разрушения
    if (!BLAST.hitDone && t >= BLAST.soundAt) {
      BLAST.hitDone = true;
      BLAST.shake = clamp(700 / Math.max(BLAST.dist, 60), 0.05, 1.8);
      shockArrival();
    }
    BLAST.shake = damp(BLAST.shake, 0, 1.1, dt);

    spawnBlastParts(t0, t, dt);
    if (t > 64) BLAST.live = false;      // столб рассеивается за минуту
  }
  if (BLAST.flashHold > 0) BLAST.flashHold -= dt;   // сначала слепит без спада
  else BLAST.flash = damp(BLAST.flash, 0, 2.4, dt);

  // пожары: язык пламени и струйка дыма
  for (let i = FIRES.length - 1; i >= 0; i--) {
    const f = FIRES[i];
    f.age += dt;
    if (f.age >= f.life) { FIRES.splice(i, 1); continue; }
    f.next -= dt;
    if (f.next <= 0) {
      f.next = 0.10 + Math.random() * 0.13;
      const fade = 1 - smoothstep(f.life - 14, f.life, f.age);
      const s = f.r * (0.55 + Math.random() * 0.7) * fade;
      spawnPuff(f.x + (Math.random() - 0.5) * f.r, f.y + 0.5, f.z + (Math.random() - 0.5) * f.r,
        (Math.random() - 0.5) * 0.7, 2.4 + Math.random() * 2.2, (Math.random() - 0.5) * 0.7,
        s, s * 0.8, 0.75, [1.0, 0.52, 0.14], 1, 1.1, 4.5);
      if (Math.random() < 0.55) {
        spawnPuff(f.x, f.y + 2.4, f.z, (Math.random() - 0.5) * 1.2, 2.2, (Math.random() - 0.5) * 1.2,
          f.r * 1.4, f.r * 1.5, 5.5 + Math.random() * 3, [0.20, 0.18, 0.17], 0, 0.5, 1.1);
      }
    }
  }

  updateParts(dt);
}

/** Частицы: только пыль у земли и вал за ударной волной. Сам гриб —
    не рой частиц, а форма, которую мы строим каждый кадр (см. pushMushroom). */
function spawnBlastParts(t0, t, dt) {
  const [x, y, z] = BLAST.pos;
  const rnd = (a) => (Math.random() - 0.5) * a;

  // выброс грунта: первые доли секунды из воронки летит порода
  if (t < 0.9 && Math.random() < dt * 90) {
    const a = Math.random() * TAU, sp = 40 + Math.random() * 90;
    spawnPuff(x + rnd(20), y + 2, z + rnd(20),
      Math.cos(a) * sp, 30 + Math.random() * 70, Math.sin(a) * sp,
      2.5 + Math.random() * 4, 3, 2.2 + Math.random() * 1.6,
      [0.42, 0.33, 0.26], 0, 0.35, -9);
  }

  // юбка пыли у подножия: её поднимает отражённая волна
  if (t < 7 && Math.random() < dt * 30) {
    const a = Math.random() * TAU, rr = 30 + Math.random() * 90;
    const px = x + Math.cos(a) * rr, pz = z + Math.sin(a) * rr;
    spawnPuff(px, groundH(px, pz) + 4 + Math.random() * 14, pz,
      Math.cos(a) * 9, 5 + Math.random() * 7, Math.sin(a) * 9,
      20 + Math.random() * 22, 6, 9 + Math.random() * 6,
      [0.40, 0.34, 0.29], 0, 0.5, 0.6);
  }

  // пылевой вал бежит по земле следом за фронтом
  if (t < 10 && Math.random() < dt * 26) {
    const rr = BLAST.ring * 0.66;
    const a = Math.random() * TAU;
    const px = x + Math.cos(a) * rr, pz = z + Math.sin(a) * rr;
    spawnPuff(px, groundH(px, pz) + 3 + Math.random() * 12, pz,
      Math.cos(a) * 26, 4 + Math.random() * 6, Math.sin(a) * 26,
      14 + rr * 0.05, 7, 7 + Math.random() * 5, [0.44, 0.38, 0.32], 0, 0.7, 0.8);
  }
}

/* ---------------- форма гриба ----------------
   Шар, ножка и шляпка — это один и тот же поднимающийся объём: сначала
   раскалённый, потом остывающий в пыль. Считаем его каждый кадр из
   постоянной таблицы «комков», поэтому облако держит форму, а не мерцает. */

const MUSH = { cap: [], stem: [], collar: [], fluff: [] };
(() => {
  let s = 12345;
  const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  for (let i = 0; i < 46; i++) {
    // шляпка: комки на сплюснутом эллипсоиде, гуще по краю
    const a = rnd() * TAU, r = Math.sqrt(0.20 + rnd() * 0.80);
    MUSH.cap.push({ a, r, h: (rnd() - 0.42) * 0.9, s: 0.30 + rnd() * 0.36, w: rnd() * TAU });
  }
  for (let i = 0; i < 20; i++) {
    MUSH.stem.push({ u: i / 19, a: rnd() * TAU, r: 0.45 + rnd() * 0.55,
                     s: 0.55 + rnd() * 0.45, w: rnd() * TAU });
  }
  for (let i = 0; i < 16; i++) {
    MUSH.collar.push({ a: rnd() * TAU, r: 0.85 + rnd() * 0.5, s: 0.35 + rnd() * 0.3, w: rnd() * TAU });
  }
  // мелкие комки по краю шляпки — от них силуэт становится «цветной капустой»
  for (let i = 0; i < 44; i++) {
    const a = rnd() * TAU, ce = rnd() * 1.7 - 0.7;
    MUSH.fluff.push({ a, ce, s: 0.11 + rnd() * 0.11, w: rnd() * TAU });
  }
})();

/* Размеры подобраны так, чтобы с трёхсот метров гриб целиком помещался
   в кадр: выше — уже приходится задирать голову и форма теряется. */
const capHeight = (t) => 40 + 70 * (1 - Math.exp(-t * 1.10)) + 720 * (1 - Math.exp(-t * 0.095));
const capRadius = (t) => 22 + 110 * (1 - Math.exp(-t * 1.90)) + 240 * (1 - Math.exp(-t * 0.15));
const stemRadius = (t) => 18 + 62 * (1 - Math.exp(-t * 0.24));

/**
 * Кладёт комки облака в список на отрисовку. Каждый комок идёт двумя
 * слоями: светящимся (доля heat) и пылевым — так остывание видно плавно,
 * без переключения режима смешивания.
 */
function pushMushroom(out, t) {
  const [bx, by, bz] = BLAST.pos;
  const heat = Math.exp(-t * 0.85);
  const life = 1 - smoothstep(34, 62, t);           // облако постепенно расходится
  if (life <= 0.002) return;

  const hotCol = [1.0, 0.30 + 0.66 * smoothstep(0.5, 0.95, heat), 0.05 + 0.82 * smoothstep(0.62, 0.98, heat)];
  const swirl = t * 0.30;

  /* Пыль красим по направлению комка от оси столба: та сторона, что
     смотрит на квазар, светлее — только так у облака появляется объём. */
  const put = (x, y, z, size, hotK, dustK, nx, ny, nz) => {
    if (hotK > 0.004) out.push({ x, y, z, size, col: hotCol, a: hotK, glow: 1 });
    if (dustK > 0.004) {
      const l = Math.hypot(nx, ny, nz) || 1;
      const lit = 0.66 + 0.40 * clamp((nx * SUN[0] + ny * SUN[1] + nz * SUN[2]) / l, -0.55, 1);
      out.push({ x, y, z, size, col: [0.47 * lit, 0.41 * lit, 0.35 * lit], a: dustK, glow: 0 });
    }
  };

  const R = capRadius(t), Y = by + capHeight(t);
  const rise = smoothstep(0.0, 1.6, t);             // пока шар у земли, ножки нет

  // шляпка
  for (const b of MUSH.cap) {
    const a = b.a + swirl * (0.6 + b.r * 0.5);
    const rr = R * b.r;
    const ox = Math.cos(a) * rr, oy = b.h * R * 0.46 + R * 0.35, oz = Math.sin(a) * rr;
    put(bx + ox, Y + b.h * R * 0.46 + Math.sin(b.w + t * 0.7) * R * 0.05, bz + oz,
        R * b.s, heat * 0.90 * life, (1 - heat * 0.8) * 0.62 * life, ox, oy, oz);
  }
  // «юбка» под шляпкой — характерный воротник
  for (const b of MUSH.collar) {
    const a = b.a + swirl * 0.4;
    const rr = R * b.r * 0.86;
    put(bx + Math.cos(a) * rr, Y - R * 0.52, bz + Math.sin(a) * rr,
        R * b.s, heat * 0.55 * life, (1 - heat * 0.8) * 0.50 * life,
        Math.cos(a), -0.5, Math.sin(a));
  }
  // бахрома по краю шляпки
  for (const b of MUSH.fluff) {
    const a = b.a + swirl * 0.8 + Math.sin(b.w + t * 0.5) * 0.10;
    const ce = clamp(b.ce + Math.sin(b.w * 2.0 + t * 0.4) * 0.10, -1, 1);
    const hr = Math.sqrt(Math.max(1 - ce * ce, 0));
    const ox = Math.cos(a) * R * hr, oy = ce * R * 0.55, oz = Math.sin(a) * R * hr;
    put(bx + ox, Y + oy, bz + oz, R * b.s,
        heat * 0.55 * life, (1 - heat * 0.8) * 0.42 * life, ox, oy + R * 0.2, oz);
  }

  // ножка
  const sr = stemRadius(t);
  for (const b of MUSH.stem) {
    const h = by + b.u * (capHeight(t) - R * 0.5);
    const taper = 0.55 + 0.45 * (1 - b.u);
    const a = b.a + swirl * 1.5 + b.u * 2.2;
    const hk = heat * (1 - b.u * 0.75) * rise;
    put(bx + Math.cos(a) * sr * b.r * taper, h, bz + Math.sin(a) * sr * b.r * taper,
        sr * b.s * 1.6 * taper, hk * 0.80 * life, (1 - hk) * 0.48 * life * rise,
        Math.cos(a), 0.15, Math.sin(a));
  }
}

/* ---------------- звук испытания ---------------- */

/**
 * Звук приходит с задержкой: сначала видишь вспышку, потом слышишь.
 * Собираем щелчок фронта, удар и долгий раскат.
 */
function soundNuke(delay, dist) {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;
  const t0 = ctx.currentTime + Math.min(delay, 12);
  const near = clamp(180 / Math.max(dist, 60), 0.18, 1);

  const noise = (secs) => {
    const len = Math.max(1, Math.floor(ctx.sampleRate * secs));
    const b = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = b.getChannelData(0);
    let lp = 0;
    for (let i = 0; i < len; i++) { lp = lp * 0.86 + (Math.random() * 2 - 1) * 0.14; d[i] = lp * 3.2; }
    const s = ctx.createBufferSource();
    s.buffer = b;
    return s;
  };

  // 1) фронт: резкий щелчок
  const crack = noise(0.4);
  const cf = ctx.createBiquadFilter();
  cf.type = 'highpass'; cf.frequency.value = 700;
  const cg = ctx.createGain();
  cg.gain.setValueAtTime(0.0001, t0);
  cg.gain.exponentialRampToValueAtTime(0.85 * near, t0 + 0.012);
  cg.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.32);
  crack.connect(cf).connect(cg).connect(out);
  crack.start(t0); crack.stop(t0 + 0.45);

  // 2) удар: низкая волна, которую чувствуешь животом
  const thump = ctx.createOscillator();
  thump.type = 'sine';
  thump.frequency.setValueAtTime(78, t0);
  thump.frequency.exponentialRampToValueAtTime(24, t0 + 1.5);
  const tg = ctx.createGain();
  tg.gain.setValueAtTime(0.0001, t0);
  tg.gain.exponentialRampToValueAtTime(0.9 * near, t0 + 0.05);
  tg.gain.exponentialRampToValueAtTime(0.0001, t0 + 2.6);
  thump.connect(tg).connect(out);
  thump.start(t0); thump.stop(t0 + 2.8);

  // 3) раскат: длинный низкий гул с медленным затуханием
  const roll = noise(9);
  const rf = ctx.createBiquadFilter();
  rf.type = 'lowpass';
  rf.frequency.setValueAtTime(900, t0);
  rf.frequency.exponentialRampToValueAtTime(110, t0 + 7);
  const rg = ctx.createGain();
  rg.gain.setValueAtTime(0.0001, t0);
  rg.gain.exponentialRampToValueAtTime(0.62 * near, t0 + 0.25);
  rg.gain.exponentialRampToValueAtTime(0.09 * near, t0 + 3.5);
  rg.gain.exponentialRampToValueAtTime(0.0001, t0 + 8.5);
  roll.connect(rf).connect(rg).connect(out);
  roll.start(t0); roll.stop(t0 + 9);
}

/* Треск пожаров: живёт, пока что-то горит. */
const fireSnd = { src: null, gain: null };

function fireLevel() {
  if (!audio.ctx) return;
  let heat = 0;
  for (const f of FIRES) {
    const d = Math.hypot(cam.x - f.x, cam.z - f.z);
    heat += f.r / Math.max(d, 6);
  }
  heat = clamp(heat * 0.09, 0, 0.5);
  if (heat > 0.004 && !fireSnd.src && audio.on) {
    const ctx = audio.ctx;
    const len = ctx.sampleRate * 3;
    const b = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = b.getChannelData(0);
    for (let i = 0; i < len; i++) {
      // редкие щелчки поверх шипения — это и слышно как костёр
      d[i] = (Math.random() * 2 - 1) * 0.22 + (Math.random() < 0.0012 ? (Math.random() * 2 - 1) : 0);
    }
    const s = ctx.createBufferSource();
    s.buffer = b; s.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = 'bandpass'; f.frequency.value = 1500; f.Q.value = 0.6;
    const g = ctx.createGain();
    g.gain.value = 0.0001;
    s.connect(f).connect(g).connect(audio.master || ctx.destination);
    s.start();
    fireSnd.src = s; fireSnd.gain = g;
  }
  if (fireSnd.gain) fireSnd.gain.gain.setTargetAtTime(Math.max(heat, 0.0001), audio.ctx.currentTime, 0.4);
  if (fireSnd.src && heat < 0.004) {
    try { fireSnd.src.stop(); } catch (e) {}
    fireSnd.src = null; fireSnd.gain = null;
  }
}

/* ---------------- отрисовка испытания ---------------- */

/**
 * Порядок: выжженная земля, кольцо волны, дым, потом свечение.
 * Всё после неба — иначе аддитивные частицы не с чем складывать.
 */
function drawBlast(vp, eye, f) {
  const nothing = !BLAST.live && PARTS.length === 0 && CRATERS.length === 0;
  if (nothing) return;

  gl.enable(gl.BLEND);
  gl.depthMask(false);

  // — воронки
  if (CRATERS.length) {
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(flatProg.prog);
    gl.uniformMatrix4fv(flatProg.u.uVP, false, vp);
    gl.uniformMatrix4fv(flatProg.u.uModel, false, m4identity(m4()));
    gl.uniform4f(flatProg.u.uColor, 0.055, 0.045, 0.040, 0.88);
    for (const c of CRATERS) {
      attrib(flatProg.a.aPos, c.pos, 3);
      attrib(flatProg.a.aFade, c.fade, 1);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, c.idx);
      gl.drawElements(gl.TRIANGLES, c.count, gl.UNSIGNED_SHORT, 0);
    }
  }

  // — фронт ударной волны
  if (BLAST.live && BLAST.ring < 3200) {
    updateShockRing();
    const a = clamp(1 - BLAST.ring / 3200, 0, 1) * clamp(2.6 - BLAST.t * 0.28, 0, 1);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.useProgram(flatProg.prog);
    gl.uniformMatrix4fv(flatProg.u.uVP, false, vp);
    gl.uniformMatrix4fv(flatProg.u.uModel, false, m4identity(m4()));
    gl.uniform4f(flatProg.u.uColor, 0.95, 0.85, 0.70, a * 0.75);
    attrib(flatProg.a.aPos, shockRing.pos, 3);
    attrib(flatProg.a.aFade, shockRing.fade, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, shockRing.idx);
    gl.drawElements(gl.TRIANGLES, shockRing.count, gl.UNSIGNED_SHORT, 0);
  }

  // — облако и частицы: собираем в один список, рисуем в два прохода
  const quads = [];
  for (const p of PARTS) {
    const u = p.age / p.life;
    const a = p.glow ? (1 - u) * (1 - u) * 0.8 : Math.min(u * 5, 1) * (1 - u) * 0.42;
    if (a > 0.004) quads.push({ x: p.x, y: p.y, z: p.z, size: p.size, col: p.col, a, glow: p.glow });
  }
  if (BLAST.live) pushMushroom(quads, BLAST.t);

  if (quads.length) {
    const right = [f[2], 0, -f[0]];
    const rl = Math.hypot(right[0], right[2]) || 1;
    right[0] /= rl; right[2] /= rl;
    const up = [right[2] * f[1] - right[1] * f[2], right[0] * f[2] - right[2] * f[0],
                right[1] * f[0] - right[0] * f[1]];
    const ul = Math.hypot(up[0], up[1], up[2]) || 1;
    up[0] /= ul; up[1] /= ul; up[2] /= ul;

    gl.useProgram(puffProg.prog);
    gl.uniformMatrix4fv(puffProg.u.uVP, false, vp);
    gl.uniform3fv(puffProg.u.uRight, right);
    gl.uniform3fv(puffProg.u.uUp, up);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, puffBuf.gIdx);
    attrib(puffProg.a.aCorner, puffBuf.gCorner, 2);

    for (let pass = 0; pass < 2; pass++) {
      let n = 0;
      for (const p of quads) {
        if (p.glow !== pass) continue;
        const a = p.a;
        const o3 = n * 12, o1 = n * 4, o4 = n * 16;
        for (let k = 0; k < 4; k++) {
          puffBuf.center[o3 + k * 3] = p.x;
          puffBuf.center[o3 + k * 3 + 1] = p.y;
          puffBuf.center[o3 + k * 3 + 2] = p.z;
          puffBuf.size[o1 + k] = p.size;
          puffBuf.color[o4 + k * 4] = p.col[0];
          puffBuf.color[o4 + k * 4 + 1] = p.col[1];
          puffBuf.color[o4 + k * 4 + 2] = p.col[2];
          puffBuf.color[o4 + k * 4 + 3] = a;
        }
        if (++n >= PUFF_MAX) break;
      }
      if (!n) continue;
      gl.blendFunc(gl.SRC_ALPHA, pass ? gl.ONE : gl.ONE_MINUS_SRC_ALPHA);
      gl.bindBuffer(gl.ARRAY_BUFFER, puffBuf.gCenter);
      gl.bufferData(gl.ARRAY_BUFFER, puffBuf.center.subarray(0, n * 12), gl.DYNAMIC_DRAW);
      gl.vertexAttribPointer(puffProg.a.aCenter, 3, gl.FLOAT, false, 0, 0);
      gl.enableVertexAttribArray(puffProg.a.aCenter);
      gl.bindBuffer(gl.ARRAY_BUFFER, puffBuf.gSize);
      gl.bufferData(gl.ARRAY_BUFFER, puffBuf.size.subarray(0, n * 4), gl.DYNAMIC_DRAW);
      gl.vertexAttribPointer(puffProg.a.aSize, 1, gl.FLOAT, false, 0, 0);
      gl.enableVertexAttribArray(puffProg.a.aSize);
      gl.bindBuffer(gl.ARRAY_BUFFER, puffBuf.gColor);
      gl.bufferData(gl.ARRAY_BUFFER, puffBuf.color.subarray(0, n * 16), gl.DYNAMIC_DRAW);
      gl.vertexAttribPointer(puffProg.a.aColor, 4, gl.FLOAT, false, 0, 0);
      gl.enableVertexAttribArray(puffProg.a.aColor);
      gl.drawElements(gl.TRIANGLES, n * 6, gl.UNSIGNED_SHORT, 0);
    }
  }

  gl.depthMask(true);
  gl.disable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
}

/* ---------------- кнопка сброса ---------------- */

let bombShown = '';

function syncBombUI() {
  const btn = document.getElementById('bomb-btn');
  if (!btn) return;
  const here = game.world === 'gamma' && !game.rocket.inside && !game.tent.inside;
  const wait = Math.max(0, bombReadyAt - game.proper);
  const label = BLAST.bomb ? 'Летит…' : wait > 0.1 ? `Перезарядка ${wait.toFixed(0)} с` : 'Сбросить бомбу';
  const sig = here + '|' + label;
  if (sig === bombShown) return;          // без нужды в DOM не лезем
  bombShown = sig;
  btn.classList.toggle('show', here);
  btn.disabled = !bombAllowed();
  btn.textContent = label;
}
