/* ============================================================
   Советник у площадки, разговор с ним и усиленное испытание
   ============================================================ */

/* ---------------- фигура в балахоне ---------------- */

/* Модель строится вокруг пояса: так сальто крутится вокруг центра тела,
   а не вокруг пяток. */
function buildSith() {
  const m = meshBuilder();
  const cloth = [0.055, 0.050, 0.062];
  const clothLit = [0.115, 0.105, 0.125];
  const skin = [0.72, 0.66, 0.58];
  const hilt = [0.28, 0.28, 0.30];
  const hiltLit = [0.62, 0.62, 0.66];

  // балахон: конус от подола к плечам
  const seg = 14;
  for (let i = 0; i < seg; i++) {
    const a0 = (i / seg) * TAU, a1 = ((i + 1) / seg) * TAU;
    const rb = 0.52, rt = 0.30;
    const A = [Math.cos(a0) * rb, -0.92, Math.sin(a0) * rb];
    const B = [Math.cos(a1) * rb, -0.92, Math.sin(a1) * rb];
    const C = [Math.cos(a1) * rt, 0.42, Math.sin(a1) * rt];
    const D = [Math.cos(a0) * rt, 0.42, Math.sin(a0) * rt];
    m.quad(A, B, C, D, i % 2 ? cloth : clothLit);
    // подол
    m.tri([0, -0.94, 0], B, A, cloth);
  }
  // плечи и мантия поверх
  m.blob(0, 0.44, 0, 0.36, 0.20, 0.28, cloth, 10, 6);
  for (const s of [-1, 1]) {
    m.rope([[s * 0.28, 0.46, 0], [s * 0.33, 0.10, 0.06], [s * 0.30, -0.30, 0.14]],
           [0.13, 0.11, 0.09], cloth, 6);
  }
  // капюшон: конус над головой, внутри пусто и темно
  m.blob(0, 0.72, -0.02, 0.23, 0.26, 0.24, cloth, 12, 7);
  for (let i = 0; i < 12; i++) {
    const a0 = (i / 12) * TAU, a1 = ((i + 1) / 12) * TAU;
    const r = 0.27;
    m.quad([Math.cos(a0) * r, 0.52, Math.sin(a0) * r - 0.02],
           [Math.cos(a1) * r, 0.52, Math.sin(a1) * r - 0.02],
           [Math.cos(a1) * 0.10, 0.98, Math.sin(a1) * 0.10 - 0.06],
           [Math.cos(a0) * 0.10, 0.98, Math.sin(a0) * 0.10 - 0.06],
           i % 3 ? cloth : clothLit);
  }
  // подбородок в тени капюшона
  m.blob(0, 0.63, 0.15, 0.10, 0.075, 0.06, skin, 8, 5);
  m.blob(0, 0.70, 0.19, 0.055, 0.035, 0.03, [0.30, 0.26, 0.24], 6, 4);

  // кисти
  m.blob(0.34, -0.30, 0.16, 0.065, 0.075, 0.055, skin, 7, 5);
  m.blob(-0.32, -0.28, 0.14, 0.060, 0.070, 0.050, skin, 7, 5);

  // рукоять меча в правой руке
  m.rope([[0.40, -0.34, 0.24], [0.40, -0.06, 0.24]], [0.030, 0.030], hilt, 7);
  m.rope([[0.40, -0.09, 0.24], [0.40, -0.03, 0.24]], [0.036, 0.032], hiltLit, 7);
  return m.pack();
}

/** Клинок: светящееся ядро и ореол вокруг. Рисуем аддитивно. */
function buildBlade() {
  const pos = [], fade = [], idx = [];
  const tube = (r, f, y0, y1) => {
    const seg = 8, base = pos.length / 3;
    for (let i = 0; i <= seg; i++) {
      const a = (i / seg) * TAU;
      pos.push(0.40 + Math.cos(a) * r, y0, 0.24 + Math.sin(a) * r);
      pos.push(0.40 + Math.cos(a) * r, y1, 0.24 + Math.sin(a) * r);
      fade.push(f, f);
    }
    for (let i = 0; i < seg; i++) {
      const a = base + i * 2;
      idx.push(a, a + 1, a + 3, a, a + 3, a + 2);
    }
    // торец
    const cap = pos.length / 3;
    pos.push(0.40, y1, 0.24); fade.push(f);
    for (let i = 0; i < seg; i++) idx.push(cap, base + i * 2 + 1, base + (i + 1) * 2 + 1);
  };
  tube(0.022, 1.0, -0.02, 1.28);      // ядро
  tube(0.055, 0.30, -0.02, 1.30);     // ореол
  return { pos: buffer(new Float32Array(pos)), fade: buffer(new Float32Array(fade)),
           idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
}

const SITH = {
  x: G.sith.x, z: G.sith.z, yaw: 0,
  y: 0,               // высота пояса над землёй
  flip: 0,            // фаза сальто, 0..1
  flipAt: 12,         // когда сделает следующее
  greeted: false,
  model: m4(),
  saber: 0.3,         // выдвинутость клинка
  talk: 0,            // сколько ещё говорит
};

/**
 * Стоит, покачивается, крутит клинок и время от времени делает сальто
 * назад. Во время разговора поворачивается к собеседнику.
 */
function updateSith(dt) {
  if (game.world !== 'gamma') { SITH.flip = 0; return; }
  const s = SITH;
  const gy = gammaMeshH(s.x, s.z);
  const dx = cam.x - s.x, dz = cam.z - s.z;
  const near = Math.hypot(dx, dz) < 30;
  if (near) s.yaw = damp(s.yaw, Math.atan2(dx, -dz), 3, dt);

  s.saber = damp(s.saber, near || s.flip > 0 ? 1 : 0.15, 2.2, dt);
  s.talk = Math.max(0, s.talk - dt);

  s.flipAt -= dt;
  if (s.flip === 0 && s.flipAt <= 0 && near) { s.flip = 0.0001; s.flipAt = 14 + Math.random() * 16; }
  if (s.flip > 0) {
    s.flip += dt / 1.15;                      // сальто длится чуть больше секунды
    if (s.flip >= 1) s.flip = 0;
  }
  const f = s.flip;
  const jump = f > 0 ? Math.sin(f * Math.PI) * 2.4 : 0;
  const spin = f > 0 ? -f * TAU : 0;
  const bob = Math.sin(game.proper * 1.1) * 0.03 + (s.talk > 0 ? Math.sin(game.proper * 9) * 0.02 : 0);
  s.y = gy + 0.98 + jump + bob;
  m4compose(s.model, s.x, s.y, s.z, s.yaw, spin, 0, 1);
}

/* ---------------- разговор ---------------- */

const SITH_LINES = [
  { k: ['привет', 'здоров', 'хай', 'ку', 'hello', 'дароу'],
    a: ['Приветствую. Полигон в вашем распоряжении.',
        'Наконец-то. Я ждал вас дольше, чем следовало.'] },
  { k: ['кто ты', 'кто вы', 'имя', 'как тебя', 'представ'],
    a: ['Я ваш советник. Имя моё вам ничего не даст, а вот совет — многое.',
        'Тот, кто стоит за плечом и подсказывает. Этого достаточно.'] },
  { k: ['бомб', 'взрыв', 'испытан', 'ядер', 'заряд'],
    a: ['Кнопка справа. Заряд уйдёт на мишенное поле — оно в полутора километрах.',
        'Смотрите не на вспышку, а на то, что от построек останется.',
        'Из города зрелище безопаснее. И, признаться, красивее.'] },
  { k: ['сальто', 'прыг', 'кувырок', 'акробат'],
    a: ['Извольте.', 'Смотрите внимательно, повторять не буду.'] },
  { k: ['меч', 'клинок', 'сабл', 'светов'],
    a: ['Красный. Другие цвета я нахожу сентиментальными.',
        'Клинок — это довод. Обычно последний.'] },
  { k: ['город', 'уехать', 'машин', 'ехать', 'авто'],
    a: ['Машина у площадки. Пять километров по прямой — и вы в городе.',
        'В машине жмите газ и не сворачивайте с дороги. Или включите автопилот.'] },
  { k: ['бассейн', 'золот', 'вода', 'купать'],
    a: ['Золото — не роскошь, а напоминание, кому здесь принадлежит вода.',
        'Бассейн западнее площадки. Полотенца не предусмотрены.'] },
  { k: ['море', 'океан', 'берег', 'пляж'],
    a: ['Море к западу. Дальше него нет ничего интересного.'] },
  { k: ['дерев', 'лес', 'роща', 'трава'],
    a: ['Роща здесь недолговечна. Вы сами скоро поймёте почему.'] },
  { k: ['земля', 'домой', 'вернут', 'ракет', 'улет'],
    a: ['Ракета ждёт. Выберите цель «Земля» и не оглядывайтесь.'] },
  { k: ['квазар', 'дыр', 'чёрн', 'черн'],
    a: ['Квазар — это чужая гравитация. К ней стоит подходить с уважением.'] },
  { k: ['сила', 'ситх', 'джедай', 'орден', 'тьм', 'темн'],
    a: ['Сила — это не мистика. Это умение довести дело до конца.',
        'Джедаи проповедуют равновесие. Равновесие — это когда обе чаши пусты.'] },
  { k: ['зачем', 'смысл', 'почему'],
    a: ['Затем, что вы можете. Остальные оправдания придумают потом.'] },
  { k: ['помощ', 'что делать', 'как', 'подскаж'],
    a: ['Бомба — кнопка справа или клавиша B. Машина — подойти и нажать E.',
        'Хотите зрелище — уезжайте в город и запускайте оттуда.'] },
  { k: ['спасиб', 'благодар'],
    a: ['Не благодарите. Я записываю.'] },
  { k: ['пока', 'прощай', 'до свид'],
    a: ['Идите. Я останусь — мне здесь спокойно.'] },
];

const SITH_DEFAULT = [
  'Занятная мысль. Но у нас испытания.',
  'Возможно. А возможно, вы просто тянете время.',
  'Я слышал. И сделал вид, что не услышал.',
  'Сформулируйте иначе — и, быть может, я отвечу.',
  'Полигон не любит долгих разговоров.',
];

let sithReplyIdx = 0;

function sithReply(text) {
  const t = text.toLowerCase();
  for (const g of SITH_LINES) {
    if (g.k.some((k) => t.includes(k))) {
      if (g.k.includes('сальто') && SITH.flip === 0) SITH.flip = 0.0001;
      return g.a[(sithReplyIdx++) % g.a.length];
    }
  }
  return SITH_DEFAULT[(sithReplyIdx++) % SITH_DEFAULT.length];
}

function sithSay(text) {
  const box = document.getElementById('sith-say');
  if (!box) return;
  box.textContent = text;
  box.classList.add('show');
  SITH.talk = Math.min(6, 1.6 + text.length * 0.045);
  clearTimeout(sithSay.timer);
  sithSay.timer = setTimeout(() => box.classList.remove('show'), SITH.talk * 1000);
}

function sithGreet() {
  if (SITH.greeted) return;
  SITH.greeted = true;
  SITH.flip = 0.0001;
  sithSay('Добро пожаловать на Гамму. Я ваш советник. Спрашивайте — или начинайте испытания.');
}

function openTalk() {
  if (game.world !== 'gamma') return;
  if (Math.hypot(cam.x - SITH.x, cam.z - SITH.z) > 26) { toast('Советник слишком далеко'); return; }
  const w = document.getElementById('talk');
  w.classList.add('show');
  document.getElementById('app').classList.add('talking');
  document.getElementById('talk-input').focus();
}

function closeTalk() {
  document.getElementById('talk').classList.remove('show');
  document.getElementById('app').classList.remove('talking');
  document.getElementById('talk-input').blur();
}

/* ---------------- усиленное испытание ---------------- */

/* Ударная волна теперь валит с ног, оглушает и рушит постройки. */
const HIT = {
  vx: 0, vz: 0,        // отброс наблюдателя
  down: 0,             // насколько присели/упали, метры
  deaf: 0,             // глухота и звон, 0..1
};

const deafSnd = { osc: null, gain: null, osc2: null };

/** Звон в ушах: две близкие частоты, медленно затухают. */
function startTinnitus(power) {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;
  stopTinnitus();
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.055 * power, ctx.currentTime + 0.12);
  g.connect(out);
  const o1 = ctx.createOscillator();
  o1.type = 'sine'; o1.frequency.value = 3950;
  const o2 = ctx.createOscillator();
  o2.type = 'sine'; o2.frequency.value = 4090;
  o1.connect(g); o2.connect(g);
  o1.start(); o2.start();
  deafSnd.osc = o1; deafSnd.osc2 = o2; deafSnd.gain = g;
}

function stopTinnitus() {
  if (!deafSnd.osc) return;
  try { deafSnd.osc.stop(); deafSnd.osc2.stop(); } catch (e) {}
  deafSnd.osc = null; deafSnd.osc2 = null; deafSnd.gain = null;
}

/**
 * Приход фронта: сбивает с ног, оглушает, рвёт постройки и поджигает лес.
 * Сила падает как обратный квадрат расстояния.
 */
function shockArrival() {
  const bx = BLAST.pos[0], bz = BLAST.pos[2];
  const px = CAR.inside ? CAR.x : cam.x, pz = CAR.inside ? CAR.z : cam.z;
  const d = Math.max(Math.hypot(px - bx, pz - bz), 40);
  const power = clamp(700 / d, 0, 1.6);

  // отброс: скорость от эпицентра плюс падение на землю
  const nx = (px - bx) / d, nz = (pz - bz) / d;
  HIT.vx += nx * power * 16;
  HIT.vz += nz * power * 16;
  if (power > 0.25 && !CAR.inside) HIT.down = Math.min(1.25, HIT.down + power * 1.1);
  if (CAR.inside) { CAR.speed += power * 8; CAR.yaw += (Math.random() - 0.5) * power * 0.5; }

  // оглушение
  HIT.deaf = Math.min(1, HIT.deaf + power * 0.9);
  if (HIT.deaf > 0.12) {
    startTinnitus(clamp(HIT.deaf, 0.2, 1));
    toast('Звон в ушах');
  }

  // постройки
  for (const b of BUILDINGS) {
    const bd = Math.hypot(b.x - bx, b.z - bz);
    const p = clamp(820 / Math.max(bd, 60) / b.tough - 0.35, 0, 1.4);
    if (p > 0.05) shockBuilding(b, p);
  }

  // лес: ближние ломает, дальние поджигает
  const dirty = new Set();
  for (let i = 0; i < TREES.length; i++) {
    const t = TREES[i];
    const td = Math.hypot(t.x - bx, t.z - bz);
    if (td > 900) continue;
    const p = clamp(620 / Math.max(td, 60) - 0.35, 0, 1.4);
    if (p <= 0.02) continue;
    let changed = false;
    if (p > 0.55 && t.fell < 1) { t.fell = 1; t.fellDir = Math.atan2(t.z - bz, t.x - bx); changed = true; }
    if (p > 0.12 && t.burn < 1) {
      t.burn = 1; changed = true;
      FIRES.push({ x: t.x, z: t.z, y: t.y, r: 2.2 + t.s * 2.4,
                   life: 70 + Math.random() * 60, age: 0, seed: Math.random() * 100, next: Math.random() * 0.3 });
    }
    if (changed) dirty.add((i / TREE_CHUNK) | 0);
  }
  for (const c of dirty) rebuildTreeChunk(c);
  if (FIRES.length > 220) FIRES.splice(0, FIRES.length - 220);
}

/** Отброс и подъём на ноги, затухание глухоты. */
function updateHit(dt) {
  if (Math.abs(HIT.vx) + Math.abs(HIT.vz) > 0.01) {
    const k = Math.exp(-3.2 * dt);
    if (!CAR.inside) {
      cam.x += HIT.vx * dt;
      cam.z += HIT.vz * dt;
    }
    HIT.vx *= k; HIT.vz *= k;
  }
  // встаём примерно за две секунды
  HIT.down = Math.max(0, HIT.down - dt * 0.62);
  if (HIT.deaf > 0) {
    HIT.deaf = Math.max(0, HIT.deaf - dt / 13);
    if (deafSnd.gain) {
      deafSnd.gain.gain.setTargetAtTime(Math.max(0.0001, 0.055 * HIT.deaf), audio.ctx.currentTime, 1.2);
    }
    // остальной мир на это время глохнет
    if (audio.master) {
      audio.master.gain.setTargetAtTime(Math.max(0.06, 1 - HIT.deaf * 0.85) * (audio.on ? 1 : 0.0001),
        audio.ctx.currentTime, 0.5);
    }
    if (HIT.deaf === 0) stopTinnitus();
  }
}

/* ---------------- звук мотора ---------------- */

/* Гул двигателя: пила через фильтр, частота растёт со скоростью,
   плюс шум шин. Заводится, когда садишься за руль. */
const carSnd = { osc: null, sub: null, filt: null, gain: null, tyre: null, tyreGain: null };

function carSoundStart() {
  if (!audio.ctx || !audio.on || carSnd.osc) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;

  const gain = ctx.createGain();
  gain.gain.value = 0.0001;
  gain.connect(out);

  const filt = ctx.createBiquadFilter();
  filt.type = 'lowpass';
  filt.frequency.value = 480;
  filt.Q.value = 3.2;
  filt.connect(gain);

  const osc = ctx.createOscillator();
  osc.type = 'sawtooth';
  osc.frequency.value = 42;
  osc.connect(filt);
  osc.start();

  const sub = ctx.createOscillator();
  sub.type = 'square';
  sub.frequency.value = 21;
  const subGain = ctx.createGain();
  subGain.gain.value = 0.35;
  sub.connect(subGain).connect(filt);
  sub.start();

  // шины: шум, который слышно только на ходу
  const len = ctx.sampleRate * 2;
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  let lp = 0;
  for (let i = 0; i < len; i++) { lp = lp * 0.72 + (Math.random() * 2 - 1) * 0.28; d[i] = lp * 2.4; }
  const tyre = ctx.createBufferSource();
  tyre.buffer = buf; tyre.loop = true;
  const tf = ctx.createBiquadFilter();
  tf.type = 'bandpass'; tf.frequency.value = 900; tf.Q.value = 0.7;
  const tg = ctx.createGain();
  tg.gain.value = 0.0001;
  tyre.connect(tf).connect(tg).connect(out);
  tyre.start();

  Object.assign(carSnd, { osc, sub, filt, gain, tyre, tyreGain: tg });
}

function carSoundStop() {
  if (!carSnd.osc) return;
  const t = audio.ctx.currentTime;
  carSnd.gain.gain.setTargetAtTime(0.0001, t, 0.15);
  carSnd.tyreGain.gain.setTargetAtTime(0.0001, t, 0.15);
  const { osc, sub, tyre } = carSnd;
  setTimeout(() => { try { osc.stop(); sub.stop(); tyre.stop(); } catch (e) {} }, 700);
  carSnd.osc = null; carSnd.sub = null; carSnd.gain = null; carSnd.tyre = null; carSnd.tyreGain = null;
}

/** Обороты идут за скоростью, но с «переключением передач». */
function carSoundLevel() {
  if (!carSnd.osc || !audio.ctx) return;
  const t = audio.ctx.currentTime;
  const v = Math.abs(CAR.speed);
  const gear = Math.min(4, Math.floor(v / 15));          // четыре ступени
  const rpm = 0.25 + ((v - gear * 15) / 15) * 0.75;       // обороты внутри передачи
  carSnd.osc.frequency.setTargetAtTime(38 + rpm * 68, t, 0.08);
  carSnd.sub.frequency.setTargetAtTime(19 + rpm * 34, t, 0.08);
  carSnd.filt.frequency.setTargetAtTime(320 + rpm * 780, t, 0.12);
  carSnd.gain.gain.setTargetAtTime(0.035 + rpm * 0.055, t, 0.12);
  carSnd.tyreGain.gain.setTargetAtTime(Math.min(v / 64, 1) * 0.10, t, 0.2);
}
