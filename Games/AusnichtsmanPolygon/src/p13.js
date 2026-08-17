/* ============================================================
   Городская жизнь: кафе, бариста, посетители и невежливые прохожие
   ============================================================ */

/* Кафе стоит на углу у въезда в город, фасадом к дороге. */
const CAFE = (() => {
  const x = G.city.x - 3 * 62 - 26;
  const z = G.city.z - 3 * 62 - 26;
  return { x, z, yaw: 0.78, w: 11, d: 8, name: 'Кафе «Полутень»' };
})();
CAFE.y = gammaMeshH(CAFE.x, CAFE.z);
/* Точка у стойки, куда надо подойти за кофе. */
CAFE.order = [CAFE.x + Math.sin(CAFE.yaw) * 2.2, CAFE.z - Math.cos(CAFE.yaw) * 2.2];

/* ---------------- человек ---------------- */

/**
 * Простая фигура: ноги, корпус, руки, голова, волосы. Строится вокруг
 * пояса, как и советник, — так одна и та же матрица годится всем.
 * `kind`: 0 посетитель, 1 бариста, 2 задира.
 */
function buildPerson(kind, seed, seated) {
  const R = rngLite(seed);
  const m = meshBuilder();
  const skinTones = [[0.80, 0.66, 0.54], [0.68, 0.52, 0.40], [0.88, 0.75, 0.64], [0.55, 0.40, 0.31]];
  const skin = skinTones[(R() * skinTones.length) | 0];
  const hairTones = [[0.14, 0.10, 0.08], [0.36, 0.22, 0.11], [0.62, 0.50, 0.30], [0.30, 0.30, 0.32]];
  const hair = hairTones[(R() * hairTones.length) | 0];
  const shirtTones = kind === 2
    ? [[0.20, 0.20, 0.23], [0.28, 0.16, 0.16], [0.16, 0.18, 0.24]]
    : [[0.30, 0.42, 0.55], [0.55, 0.35, 0.30], [0.38, 0.46, 0.34], [0.52, 0.50, 0.46], [0.44, 0.34, 0.50]];
  const shirt = shirtTones[(R() * shirtTones.length) | 0];
  const pants = [0.20, 0.21, 0.25];
  const apron = [0.42, 0.28, 0.20];

  const tall = 0.92 + R() * 0.14;
  const S = (v) => v * tall;

  // ноги: у сидящего бедро уходит вперёд, голень вниз
  for (const sx of [-1, 1]) {
    if (seated) {
      m.rope([[sx * 0.13, S(-0.06), 0], [sx * 0.13, S(-0.10), 0.26], [sx * 0.13, S(-0.14), 0.44]],
             [0.10, 0.095, 0.085], pants, 6);
      m.rope([[sx * 0.13, S(-0.14), 0.44], [sx * 0.13, S(-0.52), 0.46], [sx * 0.13, S(-0.86), 0.42]],
             [0.085, 0.078, 0.070], pants, 6);
      m.box(sx * 0.13, S(-0.90), 0.47, 0.075, 0.035, 0.11, 0, [0.12, 0.11, 0.11]);
    } else {
      m.rope([[sx * 0.11, S(-0.90), 0], [sx * 0.12, S(-0.48), 0.01], [sx * 0.12, S(-0.06), 0]],
             [0.075, 0.085, 0.10], pants, 6);
      m.box(sx * 0.12, S(-0.92), 0.03, 0.075, 0.035, 0.11, 0, [0.12, 0.11, 0.11]);   // ботинок
    }
  }
  // корпус
  m.rope([[0, S(-0.10), 0], [0, S(0.16), 0.01], [0, S(0.40), 0]],
         [0.19, 0.21, 0.19], shirt, 8);
  m.blob(0, S(0.42), 0, 0.20, 0.09, 0.13, shirt, 9, 5);       // плечи
  if (kind === 1) {
    // фартук баристы
    m.box(0, S(0.02), 0.145, 0.17, 0.30, 0.02, 0, apron);
    m.box(0, S(0.36), 0.145, 0.09, 0.06, 0.02, 0, apron);
  }
  // руки: слегка разведены, локоть намечен изломом
  for (const sx of [-1, 1]) {
    const out = 0.06 + R() * 0.05;
    m.rope([[sx * 0.21, S(0.38), 0], [sx * (0.26 + out), S(0.10), 0.03], [sx * (0.24 + out), S(-0.18), 0.09]],
           [0.072, 0.058, 0.048], shirt, 6);
    m.blob(sx * (0.24 + out), S(-0.23), 0.10, 0.052, 0.058, 0.042, skin, 6, 4);
  }
  // шея и голова
  m.rope([[0, S(0.44), 0], [0, S(0.53), 0]], [0.055, 0.055], skin, 6);
  m.blob(0, S(0.65), 0.005, 0.115, 0.135, 0.115, skin, 12, 8);
  // нос и уши, чтобы лицо читалось
  m.blob(0, S(0.635), 0.115, 0.022, 0.030, 0.028, skin, 6, 4);
  for (const sx of [-1, 1]) m.blob(sx * 0.113, S(0.655), -0.005, 0.018, 0.032, 0.022, skin, 5, 4);
  // глаза
  for (const sx of [-1, 1]) {
    m.blob(sx * 0.045, S(0.675), 0.098, 0.020, 0.014, 0.012, [0.96, 0.96, 0.94], 5, 4);
    m.blob(sx * 0.045, S(0.675), 0.107, 0.009, 0.009, 0.006, [0.13, 0.11, 0.10], 5, 4);
  }
  // причёска: шапка волос плюс несколько прядей
  m.blob(0, S(0.705), -0.012, 0.122, 0.098, 0.122, hair, 12, 7);
  const long = kind === 1 || R() < 0.45;
  if (long) {
    for (let i = 0; i < 7; i++) {
      const a = -0.9 + (i / 6) * 1.8;
      m.rope([[Math.sin(a) * 0.11, S(0.70), -0.06 - Math.cos(a) * 0.05],
              [Math.sin(a) * 0.13, S(0.50), -0.10 - Math.cos(a) * 0.04],
              [Math.sin(a) * 0.12, S(0.34), -0.08 - Math.cos(a) * 0.03]],
             [0.030, 0.026, 0.018], hair, 5);
    }
  }
  return m.pack();
}

/* ---------------- кафе ---------------- */

function buildCafe() {
  const m = meshBuilder();
  const C = CAFE;
  const co = Math.cos(C.yaw), si = Math.sin(C.yaw);
  // локальные координаты: x вправо, z вглубь зала
  const P = (x, y, z) => [C.x + x * co - z * si, C.y + y, C.z + x * si + z * co];
  const box = (x, y, z, hx, hy, hz, col) => {
    const c = P(x, y, z);
    m.box(c[0], c[1], c[2], hx, hy, hz, C.yaw, col);
  };

  const wall = [0.60, 0.56, 0.50];
  const wallDark = [0.34, 0.31, 0.28];
  const wood = [0.36, 0.24, 0.15];
  const woodLit = [0.52, 0.36, 0.22];
  const steel = [0.66, 0.66, 0.70];
  const glassC = [0.30, 0.42, 0.46];
  const W = C.w, D = C.d;

  // пол и потолок
  box(0, 0.06, 0, W, 0.06, D, [0.30, 0.26, 0.24]);
  box(0, 3.3, 0, W + 0.4, 0.16, D + 0.4, wallDark);
  // задняя и боковые стены, фасад открыт
  box(0, 1.7, D, W, 1.7, 0.16, wall);
  box(-W, 1.7, 0, 0.16, 1.7, D, wall);
  box(W, 1.7, 0, 0.16, 1.7, D, wall);
  // низкий парапет спереди и вывеска над ним
  box(-W * 0.62, 0.45, -D, W * 0.38, 0.45, 0.14, wallDark);
  box(W * 0.62, 0.45, -D, W * 0.38, 0.45, 0.14, wallDark);
  box(0, 3.05, -D - 0.1, W * 0.55, 0.30, 0.10, [0.50, 0.16, 0.12]);
  for (let i = 0; i < 5; i++) box(-2.4 + i * 1.2, 3.05, -D - 0.22, 0.16, 0.13, 0.03, [0.96, 0.88, 0.66]);
  // столбы фасада
  for (const sx of [-1, 1]) box(sx * W * 0.94, 1.7, -D + 0.2, 0.16, 1.7, 0.16, wallDark);

  // стойка: тумба, столешница, подстойка
  box(0, 0.55, D * 0.42, W * 0.72, 0.55, 0.42, wood);
  box(0, 1.13, D * 0.42, W * 0.76, 0.05, 0.50, woodLit);
  box(0, 0.20, D * 0.42 - 0.55, W * 0.72, 0.06, 0.16, wallDark);   // подножка
  // задняя полка с посудой
  box(0, 1.05, D - 0.5, W * 0.80, 0.05, 0.28, wood);
  box(0, 1.85, D - 0.5, W * 0.80, 0.05, 0.28, wood);
  for (let i = 0; i < 12; i++) {
    const x = -W * 0.7 + i * (W * 1.4 / 11);
    box(x, 1.20, D - 0.5, 0.055, 0.10, 0.055, [0.86, 0.84, 0.80]);
    if (i % 2) box(x, 2.02, D - 0.5, 0.05, 0.14, 0.05, glassC);
  }
  // кофемашина: корпус, группы, бункер
  box(-W * 0.30, 1.42, D * 0.72, 0.55, 0.24, 0.30, steel);
  box(-W * 0.30, 1.72, D * 0.72, 0.42, 0.06, 0.24, [0.30, 0.30, 0.33]);
  for (const sx of [-1, 1]) {
    box(-W * 0.30 + sx * 0.28, 1.14, D * 0.72 - 0.26, 0.06, 0.10, 0.05, [0.24, 0.24, 0.26]);
    box(-W * 0.30 + sx * 0.28, 1.05, D * 0.72 - 0.26, 0.05, 0.02, 0.04, [0.18, 0.14, 0.10]);
  }
  box(W * 0.10, 1.48, D * 0.72, 0.14, 0.30, 0.14, [0.22, 0.22, 0.24]);   // кофемолка
  box(W * 0.10, 1.80, D * 0.72, 0.10, 0.10, 0.10, glassC);

  // табуреты у стойки
  for (let i = -2; i <= 2; i++) {
    const x = i * 1.5;
    box(x, 0.40, D * 0.42 - 1.25, 0.055, 0.40, 0.055, steel);
    box(x, 0.82, D * 0.42 - 1.25, 0.24, 0.05, 0.24, woodLit);
  }
  // столики со стульями
  for (const [tx, tz] of [[-W * 0.55, -D * 0.35], [W * 0.55, -D * 0.35], [W * 0.55, D * 0.02]]) {
    box(tx, 0.36, tz, 0.07, 0.36, 0.07, steel);
    box(tx, 0.73, tz, 0.62, 0.05, 0.62, woodLit);
    for (const [ox, oz] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      box(tx + ox * 1.05, 0.24, tz + oz * 1.05, 0.20, 0.24, 0.20, wood);
      box(tx + ox * 1.05 - ox * 0.18, 0.62, tz + oz * 1.05 - oz * 0.18, ox ? 0.04 : 0.20, 0.24, oz ? 0.04 : 0.20, wood);
    }
    // чашки на столе
    box(tx - 0.18, 0.80, tz + 0.10, 0.04, 0.03, 0.04, [0.92, 0.90, 0.86]);
    box(tx + 0.16, 0.80, tz - 0.12, 0.04, 0.03, 0.04, [0.92, 0.90, 0.86]);
  }
  // подвесные лампы
  for (const lx of [-W * 0.5, 0, W * 0.5]) {
    m.rope([P(lx, 3.2, -D * 0.2), P(lx, 2.55, -D * 0.2)], [0.012, 0.012], wallDark, 4);
    const c = P(lx, 2.45, -D * 0.2);
    m.blob(c[0], c[1], c[2], 0.17, 0.12, 0.17, [0.95, 0.86, 0.62], 9, 5);
  }
  return m.pack();
}

/* ---------------- жители ---------------- */

const PEOPLE = [];
let peopleMeshes = null;

function seedPeople() {
  if (PEOPLE.length) return;
  const C = CAFE;
  const co = Math.cos(C.yaw), si = Math.sin(C.yaw);
  const at = (x, z) => [C.x + x * co - z * si, C.z + x * si + z * co];

  // бариста за стойкой, лицом в зал
  {
    const [x, z] = at(-C.w * 0.05, C.d * 0.62);
    PEOPLE.push({ kind: 1, x, z, home: [x, z], yaw: C.yaw + Math.PI, mesh: 0,
                  role: 'barista', say: 0, step: 0, state: 'idle' });
  }
  // трое у стойки на табуретах
  for (let i = 0; i < 3; i++) {
    const [x, z] = at((i - 1) * 1.5, C.d * 0.42 - 1.25);
    PEOPLE.push({ kind: 0, x, z, home: [x, z], yaw: C.yaw, mesh: 1 + i, sit: -0.02,
                  role: 'bar', say: 0, step: 0, state: 'idle' });
  }
  // двое за столиком
  for (const [i, off] of [[0, [-C.w * 0.55 - 1.05, -C.d * 0.35]], [1, [-C.w * 0.55 + 1.05, -C.d * 0.35]]]) {
    const [x, z] = at(off[0], off[1]);
    PEOPLE.push({ kind: 0, x, z, home: [x, z], yaw: C.yaw + (i ? -1.5 : 1.5), mesh: 4 + i, sit: -0.14,
                  role: 'table', say: 0, step: 0, state: 'idle' });
  }
}
seedPeople();

function buildPeopleMeshes() {
  if (peopleMeshes) return peopleMeshes;
  peopleMeshes = [];
  // 0 — бариста стоя, 1..5 — гости сидя, 6..8 — задиры стоя
  peopleMeshes.push(buildPerson(1, 4000, false));
  for (let i = 1; i < 6; i++) peopleMeshes.push(buildPerson(0, 4000 + i * 137, true));
  for (let i = 0; i < 3; i++) peopleMeshes.push(buildPerson(2, 9000 + i * 211, false));
  return peopleMeshes;
}

/* Разговоры у стойки: реплики всплывают над головой говорящего. */
const CAFE_TALK = [
  ['bar', 'Вчера опять полыхнуло на востоке. Стёкла дрожали.'],
  ['bar', 'Говорят, это испытания. А я думаю — просто кому-то скучно.'],
  ['bar', 'Мне двойной. И чтоб пенка держалась до вечера.'],
  ['bar', 'Ты слышал гром? Я думал, гроза, а небо чистое.'],
  ['table', 'Из окна было видно весь столб. Красиво и страшно.'],
  ['table', 'Пыль потом три дня оседала.'],
  ['table', 'Пойдём после смены на набережную, там тише.'],
  ['barista', 'Ваш эспрессо. Осторожно, горячий.'],
  ['barista', 'Зёрна свежие, вчера привезли с побережья.'],
  ['barista', 'Если снова тряхнёт — чашки на стойке не оставляйте.'],
];

let cafeTalkAt = 4;
let cafeSpeaker = null;

/* ---------------- задиры ---------------- */

const THUGS = [];
let thugAt = 30;

const THUG_LINES = ['Эй, ты откуда такой?', 'Чужак, кошелёк покажи.',
                    'А ну стой, разговор есть.', 'Ты чего тут ходишь?'];

function inCity(x, z) { return Math.hypot(x - G.city.x, z - G.city.z) < 720; }

/** Раз в полминуты кто-нибудь решает подойти невежливо. */
function spawnThug() {
  if (THUGS.length >= 3) return;
  const a = Math.random() * TAU;
  const r = 34 + Math.random() * 16;
  const x = cam.x + Math.cos(a) * r, z = cam.z + Math.sin(a) * r;
  THUGS.push({ x, z, yaw: 0, mesh: 6 + ((Math.random() * 3) | 0),
               state: 'come', t: 0, step: 0, fall: 0, vx: 0, vz: 0, said: false });
  return true;
}

/**
 * Задиры идут к игроку. Советник, если он рядом, встаёт между и
 * отбивает: нападающий отлетает, падает и убегает.
 */
function updateThugs(dt) {
  if (game.world !== 'gamma') { THUGS.length = 0; return; }
  const walking = !CAR.inside && !game.rocket.inside;

  thugAt -= dt;
  if (thugAt <= 0) {
    thugAt = 34 + Math.random() * 40;
    if (walking && inCity(cam.x, cam.z)) spawnThug();
  }

  for (let i = THUGS.length - 1; i >= 0; i--) {
    const t = THUGS[i];
    t.t += dt;
    const dx = cam.x - t.x, dz = cam.z - t.z;
    const d = Math.hypot(dx, dz) || 1;

    if (t.state === 'come') {
      t.yaw = damp(t.yaw, Math.atan2(dx, -dz), 6, dt);
      const sp = 2.4;
      t.x += (dx / d) * sp * dt; t.z += (dz / d) * sp * dt;
      t.step += dt * 9;
      if (!t.said && d < 16) {
        t.said = true;
        peopleSay(t, THUG_LINES[(Math.random() * THUG_LINES.length) | 0]);
      }
      // советник перехватывает раньше, чем задира дойдёт
      if (SITH.follow && d < 9 && Math.hypot(SITH.x - cam.x, SITH.z - cam.z) < 26) {
        sithRepel(t);
        t.state = 'fly';
        const k = 11;
        t.vx = -(dx / d) * k; t.vz = -(dz / d) * k;
        t.t = 0;
      } else if (d < 1.7) {
        // защиты нет — толкают
        t.state = 'flee'; t.t = 0;
        HIT.vx += (dx / d) * -9; HIT.vz += (dz / d) * -9;
        BLAST.shake = Math.max(BLAST.shake, 0.55);
        toast('Вас толкнули');
        peopleSay(t, 'Не мешайся.');
      }
    } else if (t.state === 'fly') {
      t.x += t.vx * dt; t.z += t.vz * dt;
      t.vx *= Math.exp(-2.6 * dt); t.vz *= Math.exp(-2.6 * dt);
      t.fall = Math.min(1, t.fall + dt * 3.4);
      if (t.t > 1.6) { t.state = 'rise'; t.t = 0; }
    } else if (t.state === 'rise') {
      t.fall = Math.max(0, t.fall - dt * 1.5);
      if (t.fall <= 0) { t.state = 'flee'; t.t = 0; if (Math.random() < 0.6) peopleSay(t, 'Понял, понял…'); }
    } else if (t.state === 'flee') {
      t.yaw = damp(t.yaw, Math.atan2(-dx, dz), 5, dt);
      t.x -= (dx / d) * 4.6 * dt; t.z -= (dz / d) * 4.6 * dt;
      t.step += dt * 13;
      if (t.t > 9 || d > 90) THUGS.splice(i, 1);
    }
  }
}

/** Советник встаёт между игроком и задирой и делает выпад. */
function sithRepel(t) {
  /* Встаём не ровно посередине, а ближе к задире и чуть вбок: иначе
     советник закрывает собой всю сцену и драки не видно. */
  const dx = t.x - cam.x, dz = t.z - cam.z;
  const d = Math.hypot(dx, dz) || 1;
  const mx = cam.x + dx * 0.66 - (dz / d) * 0.9;
  const mz = cam.z + dz * 0.66 + (dx / d) * 0.9;
  SITH.x = mx; SITH.z = mz;
  SITH.guard = 2.2;
  SITH.target = t;
  SITH.saber = 1;
  sithSay(['Не сегодня.', 'Идите своей дорогой.', 'Я предупреждал.',
           'Отойдите от него.'][(Math.random() * 4) | 0]);
  // искры от клинка
  for (let i = 0; i < 14; i++) {
    spawnPuff(mx + (Math.random() - 0.5) * 0.8, gammaMeshH(mx, mz) + 1.2 + Math.random() * 0.6,
      mz + (Math.random() - 0.5) * 0.8,
      (Math.random() - 0.5) * 7, 1 + Math.random() * 4, (Math.random() - 0.5) * 7,
      0.10 + Math.random() * 0.12, 0.05, 0.45 + Math.random() * 0.3,
      [1.0, 0.30, 0.20], 1, 1.6, -3);
  }
  soundSaber();
}

/* Короткий гул клинка. */
function soundSaber() {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;
  const t0 = ctx.currentTime;
  const o = ctx.createOscillator();
  o.type = 'sawtooth';
  o.frequency.setValueAtTime(150, t0);
  o.frequency.exponentialRampToValueAtTime(70, t0 + 0.35);
  const f = ctx.createBiquadFilter();
  f.type = 'bandpass'; f.frequency.value = 420; f.Q.value = 2.4;
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.16, t0 + 0.03);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.5);
  o.connect(f).connect(g).connect(out);
  o.start(t0); o.stop(t0 + 0.55);
}

/* ---------------- реплики над головами ---------------- */

let bubbleFor = null, bubbleUntil = 0;

function peopleSay(who, text) {
  bubbleFor = who;
  bubbleUntil = game.proper + 3.2 + text.length * 0.035;
  const el = document.getElementById('bubble');
  if (el) el.textContent = text;
}

/** Пузырь ставим по экранной проекции головы говорящего. */
function updateBubble() {
  const el = document.getElementById('bubble');
  if (!el) return;
  const who = bubbleFor;
  if (!who || game.proper > bubbleUntil) { el.classList.remove('show'); bubbleFor = null; return; }
  const x = who.x, z = who.z;
  const y = gammaMeshH(x, z) + (who.sit ? 1.55 : 1.95) + 0.25;
  const cx = vp[0] * x + vp[4] * y + vp[8] * z + vp[12];
  const cy = vp[1] * x + vp[5] * y + vp[9] * z + vp[13];
  const cw = vp[3] * x + vp[7] * y + vp[11] * z + vp[15];
  if (cw < 0.2) { el.classList.remove('show'); return; }
  const r = canvas.getBoundingClientRect();
  el.style.left = `${r.left + (cx / cw * 0.5 + 0.5) * r.width}px`;
  el.style.top = `${r.top + (1 - (cy / cw * 0.5 + 0.5)) * r.height}px`;
  el.classList.add('show');
}

/* ---------------- кофе ---------------- */

const COFFEE = { cups: 0, holding: 0 };

const BARISTA_LINES = [
  'Держите. Двойной, как обычно у нас берут.',
  'Свежий помол. Не обожгитесь.',
  'С вас улыбка. Остальное потом.',
  'Ещё один? Смелый вы человек.',
];

function nearCafe() {
  return game.world === 'gamma' && !CAR.inside && !game.rocket.inside
    && Math.hypot(cam.x - CAFE.order[0], cam.z - CAFE.order[1]) < 3.4;
}

function buyCoffee() {
  if (!nearCafe()) return false;
  COFFEE.cups++;
  COFFEE.holding = 1;
  const barista = PEOPLE.find((p) => p.role === 'barista');
  if (barista) peopleSay(barista, BARISTA_LINES[(COFFEE.cups - 1) % BARISTA_LINES.length]);
  toast(`Кофе взят · чашек ${COFFEE.cups}`);
  soundCoffee();
  return true;
}

/* Шипение пара и стук чашки. */
function soundCoffee() {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;
  const t0 = ctx.currentTime;
  const len = Math.floor(ctx.sampleRate * 1.4);
  const b = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * 0.5;
  const src = ctx.createBufferSource();
  src.buffer = b;
  const f = ctx.createBiquadFilter();
  f.type = 'bandpass'; f.frequency.setValueAtTime(2600, t0); f.Q.value = 1.1;
  f.frequency.exponentialRampToValueAtTime(1400, t0 + 1.2);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.10, t0 + 0.12);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.3);
  src.connect(f).connect(g).connect(out);
  src.start(t0); src.stop(t0 + 1.4);
  // стук чашки о блюдце
  const o = ctx.createOscillator();
  o.type = 'triangle'; o.frequency.value = 1250;
  const og = ctx.createGain();
  og.gain.setValueAtTime(0.0001, t0 + 1.25);
  og.gain.exponentialRampToValueAtTime(0.09, t0 + 1.28);
  og.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.5);
  o.connect(og).connect(out);
  o.start(t0 + 1.24); o.stop(t0 + 1.55);
}

/* ---------------- обновление жителей ---------------- */

function updatePeople(dt) {
  if (game.world !== 'gamma') return;
  const heard = Math.hypot(cam.x - CAFE.x, cam.z - CAFE.z) < 34;

  cafeTalkAt -= dt;
  if (cafeTalkAt <= 0) {
    cafeTalkAt = 5 + Math.random() * 7;
    if (heard) {
      const line = CAFE_TALK[(Math.random() * CAFE_TALK.length) | 0];
      const pool = PEOPLE.filter((p) => p.role === line[0]);
      if (pool.length) {
        cafeSpeaker = pool[(Math.random() * pool.length) | 0];
        peopleSay(cafeSpeaker, line[1]);
      }
    }
  }
  for (const p of PEOPLE) {
    p.step += dt * (p.role === 'barista' ? 1.6 : 1.1);
    // бариста поглядывает на гостя, если тот у стойки
    if (p.role === 'barista' && nearCafe()) {
      p.yaw = damp(p.yaw, Math.atan2(cam.x - p.x, -(cam.z - p.z)), 3, dt);
    }
  }
  COFFEE.holding = Math.max(0, COFFEE.holding - dt / 90);
  updateThugs(dt);
}

/* ---------------- отрисовка ---------------- */

function drawCity(solid, model) {
  const A = gammaAssets();
  solid(A.cafe);
  const meshes = buildPeopleMeshes();
  for (const p of PEOPLE) {
    const y = gammaMeshH(p.x, p.z) + 0.92 - (p.sit || 0);
    const sway = Math.sin(p.step) * 0.02;
    m4compose(model, p.x, y, p.z, p.yaw, sway, 0, 1);
    solid(meshes[p.mesh], model);
  }
  for (const t of THUGS) {
    const y = gammaMeshH(t.x, t.z) + 0.92;
    // падение: заваливаем фигуру набок и опускаем к земле
    const tilt = t.fall * 1.45;
    m4compose(model, t.x, y - t.fall * 0.55, t.z, t.yaw, tilt,
              Math.sin(t.step) * 0.05 * (1 - t.fall), 1);
    solid(meshes[t.mesh], model);
  }
}
