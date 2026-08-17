/* ============================================================
   Звук: ветер пустыни, щелчок разметки, звон разреза
   ============================================================ */

const audio = { ctx: null, master: null, wind: null, on: true };

function initAudio() {
  if (audio.ctx) return;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  const ctx = new AC();
  audio.ctx = ctx;

  const master = ctx.createGain();
  master.gain.value = audio.on ? 0.0001 : 0.0001;
  master.connect(ctx.destination);
  audio.master = master;

  // шумовой буфер — основа ветра
  const len = ctx.sampleRate * 4;
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const data = buf.getChannelData(0);
  let b0 = 0, b1 = 0, b2 = 0;
  for (let i = 0; i < len; i++) {
    const w = Math.random() * 2 - 1;
    b0 = 0.99765 * b0 + w * 0.0990460;
    b1 = 0.96300 * b1 + w * 0.2965164;
    b2 = 0.57000 * b2 + w * 1.0526913;
    data[i] = (b0 + b1 + b2 + w * 0.1848) * 0.16;
  }

  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.loop = true;

  // ровный низкий гул
  const low = ctx.createBiquadFilter();
  low.type = 'lowpass';
  low.frequency.value = 320;
  const lowGain = ctx.createGain();
  lowGain.gain.value = 0.55;

  // порывы: полоса, которую водит медленный LFO
  const band = ctx.createBiquadFilter();
  band.type = 'bandpass';
  band.frequency.value = 720;
  band.Q.value = 0.85;
  const gustGain = ctx.createGain();
  gustGain.gain.value = 0.18;

  const lfo = ctx.createOscillator();
  lfo.frequency.value = 0.055;
  const lfoAmp = ctx.createGain();
  lfoAmp.gain.value = 0.16;
  lfo.connect(lfoAmp).connect(gustGain.gain);

  const lfo2 = ctx.createOscillator();
  lfo2.frequency.value = 0.021;
  const lfo2Amp = ctx.createGain();
  lfo2Amp.gain.value = 320;
  lfo2.connect(lfo2Amp).connect(band.frequency);

  src.connect(low).connect(lowGain).connect(master);
  src.connect(band).connect(gustGain).connect(master);
  src.start();
  lfo.start();
  lfo2.start();

  audio.wind = master;
  audio.src = src;

  // сэмпл шага декодируем один раз
  try {
    const decoded = ctx.decodeAudioData(decodeBase64(STEP_MP3),
      (buf) => { audio.step = buf; },
      () => { audio.step = null; });
    if (decoded && decoded.then) decoded.then((buf) => { audio.step = buf; }, () => { audio.step = null; });
  } catch (e) { audio.step = null; }
  setWindLevel(audio.on ? 0.22 : 0);
}

function setWindLevel(v) {
  if (!audio.ctx) return;
  audio.master.gain.setTargetAtTime(Math.max(0.0001, v), audio.ctx.currentTime, 0.6);
}

function blip(freq, dur, type, vol) {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx;
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, ctx.currentTime);
  g.gain.setValueAtTime(vol, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
  o.connect(g).connect(ctx.destination);
  o.start();
  o.stop(ctx.currentTime + dur);
}

const soundTick = () => blip(1180 + Math.random() * 120, 0.05, 'square', 0.012);

function soundCut() {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx;
  const noise = ctx.createBufferSource();
  const len = Math.floor(ctx.sampleRate * 0.7);
  const b = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.2);
  noise.buffer = b;
  const f = ctx.createBiquadFilter();
  f.type = 'bandpass';
  f.Q.value = 3.4;
  f.frequency.setValueAtTime(2600, ctx.currentTime);
  f.frequency.exponentialRampToValueAtTime(420, ctx.currentTime + 0.6);
  const g = ctx.createGain();
  g.gain.value = 0.13;
  noise.connect(f).connect(g).connect(ctx.destination);
  noise.start();
  blip(880, 0.5, 'sine', 0.05);
  setTimeout(() => blip(1320, 0.4, 'sine', 0.03), 60);
}

/** Шаг: сэмпл pl_tile4 из Counter-Strike. */
let stepFoot = 0;
function soundStep() {
  if (!audio.ctx || !audio.on || !audio.step) return;
  const ctx = audio.ctx;
  stepFoot ^= 1;                                   // левая и правая чуть отличаются
  const src = ctx.createBufferSource();
  src.buffer = audio.step;
  src.playbackRate.value = (stepFoot ? 1.0 : 0.94) * (0.97 + Math.random() * 0.06);
  const g = ctx.createGain();
  g.gain.value = 0.55 + Math.random() * 0.12;
  src.connect(g).connect(ctx.destination);
  src.start();
}

/** Плеск воды в баке. */
function soundSplash() {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx;
  const len = Math.floor(ctx.sampleRate * 1.1);
  const b = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < len; i++) {
    const t = i / len;
    d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, 1.7) * (0.4 + 0.6 * Math.abs(Math.sin(t * 26)));
  }
  const src = ctx.createBufferSource();
  src.buffer = b;
  const f = ctx.createBiquadFilter();
  f.type = 'bandpass';
  f.Q.value = 1.6;
  f.frequency.setValueAtTime(900, ctx.currentTime);
  f.frequency.linearRampToValueAtTime(2200, ctx.currentTime + 0.9);
  const g = ctx.createGain();
  g.gain.value = 0.11;
  src.connect(f).connect(g).connect(ctx.destination);
  src.start();
  for (let i = 0; i < 5; i++) {
    setTimeout(() => blip(1500 + Math.random() * 1400, 0.09, 'sine', 0.022), 90 + i * 150);
  }
}

/* ============================================================
   Интерфейс
   ============================================================ */

const ui = {
  panel: document.getElementById('panel'),
  name: document.getElementById('f-name'),
  step1: document.getElementById('step-1'),
  step2: document.getElementById('step-2'),
  step3: document.getElementById('step-3'),
  rowDraw: document.getElementById('row-draw'),
  rowCut: document.getElementById('row-cut'),
  rowSep: document.getElementById('row-sep'),
  btnDraw: document.getElementById('btn-draw'),
  btnAuto: document.getElementById('btn-autodraw'),
  btnCut: document.getElementById('btn-cut'),
  sep: document.getElementById('sep'),
  meter: document.getElementById('draw-meter'),
  hint: document.getElementById('hint'),
  reticle: document.getElementById('reticle'),
  prompt: document.getElementById('prompt'),
  keys: document.getElementById('keys'),
  stick: document.getElementById('stick'),
  knob: document.getElementById('stick-knob'),
  cover: document.getElementById('cover'),
  help: document.getElementById('help'),
  clocks: document.getElementById('clocks'),
  clockMe: document.getElementById('clock-me'),
  clockFar: document.getElementById('clock-far'),
  clockRate: document.getElementById('clock-rate'),
  toast: document.getElementById('toast'),
  tentPanel: document.getElementById('tent-panel'),
  rocketPanel: document.getElementById('rocket-panel'),
  rocketLaunch: document.getElementById('rocket-launch'),
  rocketHome: document.getElementById('rocket-home'),
  rocketWarp: document.getElementById('rocket-warp'),
  rocketDest: document.getElementById('rocket-dest'),
  flash: document.getElementById('flash'),
  rocketStealth: document.getElementById('rocket-stealth'),
  rocketInfo: document.getElementById('rocket-info'),
};

let toastUntil = 0;
function toast(text) {
  ui.toast.textContent = text;
  ui.toast.classList.add('show');
  toastUntil = game.proper + 2.6;
}

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

const WASH_TIME = 5;

/** Расположиться в палатке: камера садится внутрь, включается джаз. */
function tentSit() {
  if (game.tent.inside) return false;
  if (Math.hypot(cam.x - TENT.x, cam.z - TENT.z) > 4.2) return false;
  game.tent.inside = true;
  game.tent.from = [cam.x, cam.z, cam.yaw, cam.pitch];
  // смотрим вглубь палатки — туда, где кот и ящик с блокнотом
  game.tent.yaw = Math.atan2(TENT.lookAt[0] - TENT.seat[0], -(TENT.lookAt[1] - TENT.seat[2]));
  jazzStart();
  toast('Вы расположились');
  syncTent();
  return true;
}

function tentLeave() {
  if (!game.tent.inside) return;
  game.tent.inside = false;
  diaryToggle(false);
  jazzStop();
  syncTent();
}

function syncTent() {
  ui.tentPanel.classList.toggle('show', game.tent.inside);
}

/** Сесть в ракету, если стоим рядом. */
function rocketBoard() {
  if (game.rocket.inside) return false;
  if (Math.hypot(cam.x - PAD.x, cam.z - PAD.z) > 6.5) return false;
  game.rocket.inside = true;
  game.mode = 'rocket';
  toast('Вы в кабине');
  syncRocket();
  return true;
}

function rocketExit() {
  game.rocket.inside = false;
  game.mode = 'walk';
  engineStop();
  rocketReset();
  ROCKET.stealth = false;
  // высаживаемся рядом с площадкой
  cam.x = PAD.x + 6; cam.z = PAD.z + 4;
  camBase = eyeHeight(cam.x, cam.z);
  syncRocket();
  if (game.world === 'gamma') setTimeout(sithGreet, 900);
}

function rocketLaunch() {
  if (!game.rocket.inside || ROCKET.phase !== 'pad') return;
  rocketStart();
  engineStart();
  toast('Пуск');
  syncRocket();
}

/** Двигатель: ровный гул, громкость падает вместе с плотностью воздуха. */
const engine = { src: null, gain: null, filt: null };

function engineStart() {
  if (!audio.ctx || !audio.on || engine.src) return;
  const ctx = audio.ctx;
  const len = Math.floor(ctx.sampleRate * 3);
  const b = ctx.createBuffer(1, len, ctx.sampleRate);
  const dch = b.getChannelData(0);
  let lp = 0;
  for (let i = 0; i < len; i++) {
    const w = Math.random() * 2 - 1;
    lp = lp * 0.86 + w * 0.14;                 // грубый низкий рокот
    dch[i] = lp * 2.2 + w * 0.25;
  }
  const src = ctx.createBufferSource();
  src.buffer = b; src.loop = true;
  const filt = ctx.createBiquadFilter();
  filt.type = 'lowpass';
  filt.frequency.value = 420;
  const g = ctx.createGain();
  g.gain.value = 0.0001;
  src.connect(filt).connect(g).connect(ctx.destination);
  src.start();
  engine.src = src; engine.gain = g; engine.filt = filt;
}

function engineStop() {
  if (!engine.src) return;
  try { engine.gain.gain.setTargetAtTime(0.0001, audio.ctx.currentTime, 0.4); } catch (e) {}
  const s = engine.src;
  setTimeout(() => { try { s.stop(); } catch (e) {} }, 1200);
  engine.src = null; engine.gain = null;
}

/** Громкость двигателя: тяга × воздух вокруг. В вакууме остаётся лёгкая вибрация корпуса. */
function engineLevel() {
  if (!engine.gain || !audio.ctx) return;
  const air = airDensity(ROCKET.alt + ROCKET.cruise);
  const v = ROCKET.thrust * (0.05 + 0.55 * air);
  engine.gain.gain.setTargetAtTime(Math.max(0.0001, v), audio.ctx.currentTime, 0.25);
  engine.filt.frequency.setTargetAtTime(180 + 420 * air, audio.ctx.currentTime, 0.4);
}

function rocketToggleStealth() {
  ROCKET.stealth = !ROCKET.stealth;
  toast(ROCKET.stealth ? 'Корпус прозрачен' : 'Корпус виден');
  syncRocket();
}

function syncRocket() {
  ui.rocketPanel.classList.toggle('show', game.rocket.inside);
  if (!game.rocket.inside) return;
  const ph = ROCKET.phase;
  const arrived = ROCKET.dest === 'quasar' && ROCKET.cruise >= QUASAR_STOP - 1;
  const toName = ROCKET.dest === 'quasar' ? 'К квазару'
    : ROCKET.dest === 'gamma' ? 'К Гамме' : 'На Землю';
  ui.rocketLaunch.textContent = ph === 'pad' ? 'Запуск'
    : ph === 'ascent' ? 'Подъём…'
    : ph === 'hold' ? (arrived ? 'Ближе нельзя' : toName)
    : ph === 'cruise' ? 'Остановиться'
    : 'Снижение…';
  ui.rocketLaunch.disabled = ph === 'ascent' || ph === 'home' || (ph === 'hold' && arrived);
  ui.rocketDest.textContent = 'цель: ' + destName();
  ui.rocketDest.disabled = !(ph === 'pad' || (ph === 'hold' && ROCKET.cruise < 1));
  ui.rocketHome.disabled = ph === 'pad' || ph === 'ascent' || ph === 'home';
  ui.rocketStealth.classList.toggle('on', ROCKET.stealth);
  ui.rocketWarp.textContent = `время ×${ROCKET.warp}`;
  ui.rocketWarp.classList.toggle('on', ROCKET.warp > 1);
}

/** Одна кнопка на все фазы: запуск, курс на квазар, остановка. */
function rocketPrimary() {
  if (ROCKET.phase === 'pad') rocketLaunch();
  else if (ROCKET.phase === 'hold') { rocketToQuasar(); toast('Курс на квазар'); }
  else if (ROCKET.phase === 'cruise') { rocketHold(); toast('Двигатель на удержание'); }
  syncRocket();
}

/** Раскатистый гул стартующего двигателя. */
function soundLaunch() {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx;
  const t0 = ctx.currentTime;
  const len = Math.floor(ctx.sampleRate * 6);
  const b = ctx.createBuffer(1, len, ctx.sampleRate);
  const dch = b.getChannelData(0);
  for (let i = 0; i < len; i++) dch[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = b;
  const f = ctx.createBiquadFilter();
  f.type = 'lowpass';
  f.frequency.setValueAtTime(90, t0);
  f.frequency.linearRampToValueAtTime(420, t0 + 1.2);
  f.frequency.linearRampToValueAtTime(120, t0 + 6);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.30, t0 + 0.8);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + 6);
  src.connect(f).connect(g).connect(ctx.destination);
  src.start(t0);
  src.stop(t0 + 6.1);
}

/** Помыть руки — если стоим у бака. Процесс идёт пять секунд. */
function washHands() {
  if (game.wash.active) return false;
  const d = Math.hypot(cam.x - TANK.x, cam.z - TANK.z);
  if (d > TANK.r + 2.2) return false;
  game.wash.active = true;
  game.wash.t = 0;
  soundWash();
  return true;
}

/** Пять секунд воды: струя, всплески и капли. */
function soundWash() {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx;
  const t0 = ctx.currentTime;
  const len = Math.floor(ctx.sampleRate * WASH_TIME);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;

  const src = ctx.createBufferSource();
  src.buffer = buf;
  const f = ctx.createBiquadFilter();
  f.type = 'bandpass';
  f.frequency.value = 1500;
  f.Q.value = 0.7;
  const lfo = ctx.createOscillator();
  lfo.frequency.value = 1.7;
  const lfoAmp = ctx.createGain();
  lfoAmp.gain.value = 700;
  lfo.connect(lfoAmp).connect(f.frequency);

  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.085, t0 + 0.18);
  g.gain.setValueAtTime(0.085, t0 + WASH_TIME - 0.6);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + WASH_TIME);

  src.connect(f).connect(g).connect(ctx.destination);
  src.start(t0);
  lfo.start(t0);
  src.stop(t0 + WASH_TIME);
  lfo.stop(t0 + WASH_TIME);

  soundSplash();
  for (const at of [1.4, 2.8, 4.0]) setTimeout(soundSplash, at * 1000);
}

function syncUI() {
  const i = game.focusIndex;
  if (i < 0) {
    ui.panel.classList.remove('show');
    ui.reticle.style.display = '';
    return;
  }
  const s = SHAPES[i];
  ui.panel.classList.add('show');
  ui.reticle.style.display = 'none';
  ui.name.textContent = s.name;

  const lineDone = s.progress >= 0.999;
  const cutDone = s.cutTarget > 0.5 && s.cut > 0.9;

  ui.step1.className = 'step' + (lineDone ? ' done' : ' active');
  ui.step2.className = 'step' + (cutDone ? ' done' : lineDone ? ' active' : '');
  ui.step3.className = 'step' + (cutDone && s.sepTarget > 0.02 ? ' done' : cutDone ? ' active' : '');

  ui.rowDraw.classList.toggle('hide', lineDone);
  ui.rowCut.classList.toggle('hide', !lineDone || cutDone);
  ui.rowSep.classList.toggle('hide', !cutDone);

  ui.btnDraw.classList.toggle('on', game.tool === 'draw');
  ui.meter.style.width = `${Math.round(s.progress * 100)}%`;

  ui.hint.textContent = !lineDone
    ? (game.tool === 'draw'
      ? `Ведите по кругу вокруг фигуры: за остриём линии едет нормаль к поверхности. Пройдено ${Math.round(s.progress * 100)}%.`
      : 'Нажмите «Провести линию» и обведите фигуру по кругу — линия ляжет ровно по середине.')
    : !cutDone
      ? 'Линия замкнулась. Сравните бирюзовую стрелку с оранжевой в точке старта — и разрежьте по линии.'
      : s.sepTarget < 0.02
        ? 'Разрез готов. Тяните ползунок — и посмотрите, что вышло.'
        : 'Крутите фигуру и меняйте масштаб, чтобы рассмотреть со всех сторон.';
}

function setTool(t) {
  game.tool = t;
  syncUI();
}

function enterFocus(i) {
  const s = SHAPES[i];
  game.mode = 'focus';
  game.focusIndex = i;
  game.tool = 'rotate';
  const f = camForward();
  s.grabPos = [cam.x + f[0] * 3.9, cam.y + f[1] * 3.9 + 0.42, cam.z + f[2] * 3.9];
  s.zoomTarget = 1;
  ui.sep.value = String(Math.round(s.sepTarget * 100));
  ui.prompt.classList.remove('show');
  syncUI();
}

function exitFocus() {
  game.mode = 'walk';
  game.focusIndex = -1;
  game.tool = 'rotate';
  syncUI();
}

function resetShape(s) {
  s.progress = 0;
  s.cut = 0; s.cutTarget = 0;
  s.sep = 0; s.sepTarget = 0;
  s.autoDraw = false;
  ui.sep.value = '0';
  syncUI();
}

/* ============================================================
   Ввод
   ============================================================ */

const keys = Object.create(null);
const pointers = new Map();
let lookId = null, pinchDist = 0, drawDir = 0, drawAngle = 0, lastTickAt = 0;

const isCoarse = window.matchMedia('(pointer: coarse)').matches;
if (isCoarse) {
  ui.stick.classList.add('show');
  ui.keys.classList.add('hide');
}

function ndc(e) {
  const r = canvas.getBoundingClientRect();
  return [((e.clientX - r.left) / r.width) * 2 - 1, 1 - ((e.clientY - r.top) / r.height) * 2];
}

function unproject(nx, ny, nz) {
  const x = invVP[0] * nx + invVP[4] * ny + invVP[8] * nz + invVP[12];
  const y = invVP[1] * nx + invVP[5] * ny + invVP[9] * nz + invVP[13];
  const z = invVP[2] * nx + invVP[6] * ny + invVP[10] * nz + invVP[14];
  const w = invVP[3] * nx + invVP[7] * ny + invVP[11] * nz + invVP[15];
  return [x / w, y / w, z / w];
}

/** Луч из точки экрана; возвращает индекс фигуры или -1. */
function pick(nx, ny) {
  if (game.world !== 'earth') return -1;    // фигуры остались на Земле
  const a = unproject(nx, ny, -1);
  const b = unproject(nx, ny, 1);
  const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const dl = Math.hypot(d[0], d[1], d[2]) || 1;
  d[0] /= dl; d[1] /= dl; d[2] /= dl;

  let best = -1, bestT = 1e9;
  SHAPES.forEach((s, i) => {
    const r = 1.62 * s.zoom;
    const ox = a[0] - s.pos[0], oy = a[1] - s.pos[1], oz = a[2] - s.pos[2];
    const bq = ox * d[0] + oy * d[1] + oz * d[2];
    const c = ox * ox + oy * oy + oz * oz - r * r;
    const disc = bq * bq - c;
    if (disc < 0) return;
    const t = -bq - Math.sqrt(disc);
    if (t > 0.1 && t < bestT) { bestT = t; best = i; }
  });
  return best;
}

/** Экранный угол точки относительно проекции фигуры — для черчения. */
function angleAround(shape, nx, ny) {
  const p = shape.pos;
  const x = vp[0] * p[0] + vp[4] * p[1] + vp[8] * p[2] + vp[12];
  const y = vp[1] * p[0] + vp[5] * p[1] + vp[9] * p[2] + vp[13];
  const w = vp[3] * p[0] + vp[7] * p[1] + vp[11] * p[2] + vp[15];
  if (Math.abs(w) < 1e-5) return null;
  return Math.atan2(ny - y / w, nx - x / w);
}

canvas.addEventListener('pointerdown', (e) => {
  if (!game.started || game.wash.active) return;
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  window.focus();

  if (pointers.size === 2) {
    const [p1, p2] = [...pointers.values()];
    pinchDist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
    lookId = null;
    return;
  }

  if (lookId === null) {
    lookId = e.pointerId;
    const [nx, ny] = ndc(e);
    if (game.mode === 'focus' && game.tool === 'draw') {
      drawDir = 0;
      drawAngle = angleAround(SHAPES[game.focusIndex], nx, ny) ?? 0;
    } else if (game.mode === 'walk') {
      const hit = pick(nx, ny);
      if (hit >= 0) { enterFocus(hit); lookId = null; }
      else if (buyCoffee() || talkClose() || washHands() || tentSit() || carBoard() || rocketBoard()) lookId = null;
    }
  }
});

canvas.addEventListener('pointermove', (e) => {
  if (!game.started) return;
  const prev = pointers.get(e.pointerId);
  if (!prev) {
    if (game.mode === 'walk') {
      const [nx, ny] = ndc(e);
      game.hovered = pick(nx, ny);
    }
    return;
  }
  const dx = e.clientX - prev.x, dy = e.clientY - prev.y;
  prev.x = e.clientX; prev.y = e.clientY;

  if (pointers.size >= 2) {
    const [p1, p2] = [...pointers.values()];
    const d = Math.hypot(p1.x - p2.x, p1.y - p2.y);
    if (pinchDist > 0) {
      if (game.mode === 'focus') {
        const s = SHAPES[game.focusIndex];
        s.zoomTarget = clamp(s.zoomTarget * (d / pinchDist), 0.5, 2.6);
      } else {
        setZoom(game.zoom * (d / pinchDist));   // щипок приближает вид
      }
    }
    pinchDist = d;
    return;
  }
  if (e.pointerId !== lookId) return;

  if (game.mode === 'walk' || game.mode === 'rocket') {
    // на приближении палец должен водить взглядом медленнее
    const k = 0.0042 / game.zoom;
    cam.yaw += dx * k;
    const lim = game.rocket.inside ? 1.53 : 1.15;   // в ракете смотрим куда угодно
    cam.pitch = clamp(cam.pitch - dy * k, -lim, game.rocket.inside ? lim : 0.95);
    return;
  }

  const s = SHAPES[game.focusIndex];
  if (game.tool === 'draw') {
    const [nx, ny] = ndc(e);
    const a = angleAround(s, nx, ny);
    if (a === null) return;
    let da = a - drawAngle;
    while (da > Math.PI) da -= TAU;
    while (da < -Math.PI) da += TAU;
    drawAngle = a;
    if (drawDir === 0) {
      if (Math.abs(da) > 0.035) drawDir = Math.sign(da);
      else return;
    }
    const before = s.progress;
    s.progress = clamp(s.progress + (da * drawDir) / TAU, 0, 1);
    if (Math.floor(s.progress * 22) !== Math.floor(before * 22)) soundTick();
    if (s.progress >= 0.999 && before < 0.999) {
      blip(1560, 0.16, 'sine', 0.05);
      setTool('rotate');
    }
    syncUI();
  } else {
    s.rotYTarget += dx * 0.0075;
    s.rotXTarget = clamp(s.rotXTarget + dy * 0.0075, -1.3, 1.3);
  }
});

function endPointer(e) {
  pointers.delete(e.pointerId);
  if (e.pointerId === lookId) lookId = null;
  if (pointers.size < 2) pinchDist = 0;
}
canvas.addEventListener('pointerup', endPointer);
canvas.addEventListener('pointercancel', endPointer);
canvas.addEventListener('pointerleave', endPointer);

window.addEventListener('wheel', (e) => {
  e.preventDefault();
  if (game.mode === 'focus') {
    const s = SHAPES[game.focusIndex];
    s.zoomTarget = clamp(s.zoomTarget * Math.exp(-e.deltaY * 0.0012), 0.5, 2.6);
  } else {
    // на ходу колесо приближает вид
    setZoom(game.zoom * Math.exp(-e.deltaY * 0.0016));
  }
}, { passive: false });

/* Приближение: сужаем поле зрения. Чувствительность взгляда падает
   пропорционально, иначе на четырёхкратном зуме камера дёргается. */
function setZoom(z) {
  game.zoom = clamp(z, 1, 4);
  const el = document.getElementById('zoom-label');
  if (el) el.textContent = '×' + game.zoom.toFixed(1);
  const box = document.getElementById('zoom');
  if (box) box.classList.toggle('on', game.zoom > 1.02);
}

window.addEventListener('keydown', (e) => {
  if (diary.open) {                       // пока открыт блокнот, миром не управляем
    if (e.code === 'Escape') diaryToggle(false);
    return;
  }
  keys[e.code] = true;
  if (e.code === 'Escape' && game.mode === 'focus') exitFocus();
  if (e.code === 'KeyE' && game.mode === 'walk') { if (!buyCoffee() && !talkClose() && !washHands() && !tentSit() && !carBoard()) rocketBoard(); }
  if (e.code === 'KeyT' && game.world === 'gamma' && !CAR.inside) openTalk();
  if (e.code === 'KeyB') dropBomb();
  if (e.code === 'Escape' && game.tent.inside) tentLeave();
  if (e.code === 'Escape' && game.rocket.inside) rocketExit();
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) e.preventDefault();
});
window.addEventListener('keyup', (e) => { keys[e.code] = false; });
window.addEventListener('blur', () => { for (const k in keys) keys[k] = false; });

/* ---------------- джойстик ---------------- */

const stick = { active: false, id: null, dx: 0, dy: 0 };

ui.stick.addEventListener('pointerdown', (e) => {
  stick.active = true;
  stick.id = e.pointerId;
  ui.stick.setPointerCapture(e.pointerId);
  moveStick(e);
});
ui.stick.addEventListener('pointermove', (e) => { if (stick.active && e.pointerId === stick.id) moveStick(e); });
function releaseStick(e) {
  if (e.pointerId !== stick.id) return;
  stick.active = false; stick.id = null; stick.dx = 0; stick.dy = 0;
  ui.knob.style.transform = '';
}
ui.stick.addEventListener('pointerup', releaseStick);
ui.stick.addEventListener('pointercancel', releaseStick);

function moveStick(e) {
  const r = ui.stick.getBoundingClientRect();
  let dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
  let dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
  const l = Math.hypot(dx, dy);
  if (l > 1) { dx /= l; dy /= l; }
  stick.dx = dx; stick.dy = dy;
  ui.knob.style.transform = `translate(${dx * 32}px, ${dy * 32}px)`;
}

/* ---------------- кнопки ---------------- */

document.getElementById('btn-start').addEventListener('click', () => start(true));
document.getElementById('btn-start-mute').addEventListener('click', () => start(false));

function start(withSound) {
  audio.on = withSound;
  ui.cover.classList.add('gone');
  game.started = true;
  if (withSound) initAudio();
  document.getElementById('btn-sound').classList.toggle('on', withSound);
}

document.getElementById('btn-sound').addEventListener('click', (e) => {
  audio.on = !audio.on;
  if (audio.on) { initAudio(); setWindLevel(0.22); } else setWindLevel(0);
  e.currentTarget.classList.toggle('on', audio.on);
});

document.getElementById('btn-help').addEventListener('click', () => ui.help.classList.toggle('show'));
document.getElementById('tent-book').addEventListener('click', () => {
  document.getElementById('diary-stamp').textContent = gameStamp();
  diaryToggle(true);
});
document.getElementById('tent-leave').addEventListener('click', tentLeave);
document.getElementById('rocket-launch').addEventListener('click', rocketPrimary);
document.getElementById('rocket-dest').addEventListener('click', () => {
  if (ROCKET.phase !== 'pad' && ROCKET.phase !== 'hold') return;
  if (ROCKET.cruise > 1) { toast('Сначала вернитесь на орбиту старта'); return; }
  cycleDest();
  syncRocket();
});
document.getElementById('bomb-btn').addEventListener('click', (e) => { e.stopPropagation(); dropBomb(); });
document.getElementById('talk-btn').addEventListener('click', (e) => { e.stopPropagation(); openTalk(); });
document.getElementById('zoom-in').addEventListener('click', () => setZoom(game.zoom * 1.45));
document.getElementById('zoom-out').addEventListener('click', () => setZoom(game.zoom / 1.45));
document.getElementById('car-exit').addEventListener('click', carExit);
/* Педали и руль держатся нажатыми: pointerdown включает, любой отпуск — гасит. */
for (const [id, key] of [['car-gas', 'gas'], ['car-brake', 'brake'], ['car-left', 'left'], ['car-right', 'right']]) {
  const el = document.getElementById(id);
  const on = (e) => { e.preventDefault(); e.stopPropagation(); CAR.pedal[key] = 1; el.classList.add('held');
                      if (el.setPointerCapture && e.pointerId !== undefined) { try { el.setPointerCapture(e.pointerId); } catch (err) {} } };
  const off = () => { CAR.pedal[key] = 0; el.classList.remove('held'); };
  el.addEventListener('pointerdown', on);
  el.addEventListener('pointerup', off);
  el.addEventListener('pointercancel', off);
  el.addEventListener('pointerleave', off);
  el.addEventListener('contextmenu', (e) => e.preventDefault());
}
document.getElementById('car-auto').addEventListener('click', () => {
  if (CAR.auto) { CAR.auto = 0; toast('Автопилот выключен'); }
  else {
    CAR.auto = Math.hypot(CAR.x - G.city.x, CAR.z - G.city.z) < 700 ? -1 : 1;
    toast(CAR.auto > 0 ? 'Автопилот: в город' : 'Автопилот: к площадке');
  }
  syncCarUI();
});
{
  const send = () => {
    const inp = document.getElementById('talk-input');
    const text = inp.value.trim();
    if (!text) return;
    inp.value = '';
    saySith(text);
  };
  initVoice();
  document.getElementById('talk-mic').addEventListener('click', toggleVoice);
  document.getElementById('talk-send').addEventListener('click', send);
  document.getElementById('talk-close').addEventListener('click', closeTalk);
  document.getElementById('talk-input').addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') send();
    if (e.key === 'Escape') closeTalk();
  });
}
document.getElementById('rocket-warp').addEventListener('click', () => {
  ROCKET.warp = ROCKET.warp === 1 ? 100 : ROCKET.warp === 100 ? 1000 : 1;
  syncRocket();
});
document.getElementById('rocket-home').addEventListener('click', () => { rocketHome(); toast('Курс домой'); syncRocket(); });
document.getElementById('rocket-stealth').addEventListener('click', rocketToggleStealth);
document.getElementById('rocket-exit').addEventListener('click', rocketExit);
diaryInit();
document.getElementById('btn-release').addEventListener('click', exitFocus);
ui.btnDraw.addEventListener('click', () => setTool(game.tool === 'draw' ? 'rotate' : 'draw'));
ui.btnAuto.addEventListener('click', () => { SHAPES[game.focusIndex].autoDraw = true; setTool('rotate'); });
ui.btnCut.addEventListener('click', () => {
  const s = SHAPES[game.focusIndex];
  if (s.progress < 0.999) return;
  s.cutTarget = 1;
  soundCut();
  syncUI();
});
ui.sep.addEventListener('input', () => {
  const s = SHAPES[game.focusIndex];
  s.sepTarget = Number(ui.sep.value) / 100;
  syncUI();
});
document.getElementById('btn-reset-1').addEventListener('click', () => resetShape(SHAPES[game.focusIndex]));
document.getElementById('btn-reset-2').addEventListener('click', () => resetShape(SHAPES[game.focusIndex]));

/* ============================================================
   Шаг симуляции
   ============================================================ */

let bobPhase = 0;
let camBase = 0;
let lastSig = '';

function update(dt) {
  // Собственное время идёт как идёт, а «дальнее» — быстрее, и тем сильнее,
  // чем ближе мы к дыре. По нему живут ветряк, покачивание фигур и ветер.
  game.dilation = damp(game.dilation, game.world === 'earth' ? dilationAt(cam.x, cam.y, cam.z) : 1, 6, dt);
  game.proper += dt;
  game.time += dt * game.dilation;
  updateSky(game.time);          // сутки за пять минут «дальнего» времени
  updateRocket(dt);
  if (game.world === 'gamma') {
    updateCar(dt);
    updateSith(dt);
    updatePeople(dt);
    updateBuildings(dt);
    updateGrass(cam.x, cam.z);
  }
  updateHit(dt);
  updateBlast(dt);
  // тепловая вспышка бьёт по экрану, а мир на секунду заливает светом
  if (ui.flash) ui.flash.style.opacity = BLAST.flash > 0.002 ? Math.min(BLAST.flash, 1).toFixed(3) : '0';
  if (BLAST.flash > 0.002) {
    const k = BLAST.flash * 1.6;
    for (let i = 0; i < 3; i++) { AMB[i] += k * 0.9; LIGHT[i] += k * 0.7; }
  }
  updateDebris(dt);
  updatePairs(dt, Math.hypot(cam.x - BH.pos[0], cam.y - BH.pos[1], cam.z - BH.pos[2]));
  if (game.world !== 'earth') {  // на полигоне воздух пыльный и рыжий
    const wh = WORLDS[game.world].haze;
    for (let i = 0; i < 3; i++) HAZE[i] *= wh[i];
  }
  if (spaceAmount > 0.001) {     // за атмосферой дымки нет, остаётся чернота
    for (let i = 0; i < 3; i++) HAZE[i] = lerp(HAZE[i], 0.015, spaceAmount);
  }
  game.splash += dt;

  // мытьё: руки поднимаются в кадр, вода бурлит, ходьба на это время замирает
  if (game.wash.active) {
    game.wash.t += dt;
    const t = game.wash.t;
    game.splash = 0.12 + 0.34 * Math.abs(Math.sin(t * 3.1));
    cam.pitch = damp(cam.pitch, -0.44, 3.2, dt);
    const left = Math.max(1, Math.ceil(WASH_TIME - t));
    if (left !== game.wash.shown) { game.wash.shown = left; toast(`Моем руки… ${left}`); }
    if (t >= WASH_TIME) {
      game.wash.active = false;
      game.wash.shown = 0;
      game.washed = true;
      game.splash = 0;
      toast('Руки вымыты');
    }
  }
  game.wash.vis = damp(game.wash.vis, game.wash.active
    ? Math.min(smoothstep(0, 0.5, game.wash.t), smoothstep(WASH_TIME, WASH_TIME - 0.5, game.wash.t))
    : 0, 12, dt);

  // ходьба
  let ix = 0, iz = 0;
  if (game.mode === 'walk' && !game.wash.active && !game.tent.inside && !game.rocket.inside && !CAR.inside) {
    if (keys.KeyW || keys.ArrowUp) iz += 1;
    if (keys.KeyS || keys.ArrowDown) iz -= 1;
    if (keys.KeyD || keys.ArrowRight) ix += 1;
    if (keys.KeyA || keys.ArrowLeft) ix -= 1;
    ix += stick.dx; iz -= stick.dy;
    const l = Math.hypot(ix, iz);
    if (l > 1) { ix /= l; iz /= l; }
  }
  const speed = (keys.ShiftLeft || keys.ShiftRight) ? 5.4 : 3.2;
  const fwd = [Math.sin(cam.yaw), 0, -Math.cos(cam.yaw)];
  const rgt = [Math.cos(cam.yaw), 0, Math.sin(cam.yaw)];
  const tx = (fwd[0] * iz + rgt[0] * ix) * speed;
  const tz = (fwd[2] * iz + rgt[2] * ix) * speed;
  cam.vx = damp(cam.vx, tx, 9, dt);
  cam.vz = damp(cam.vz, tz, 9, dt);
  cam.x += cam.vx * dt;
  cam.z += cam.vz * dt;

  // к сингулярности не пускаем (дыра осталась в Неваде)
  const bdx = cam.x - BH.pos[0], bdz = cam.z - BH.pos[2];
  const bd = Math.hypot(bdx, cam.y - BH.pos[1], bdz);
  if (bd < BH.block && !game.rocket.inside && game.world === 'earth') {
    const k = (BH.block - bd) * 0.9;
    let l = Math.hypot(bdx, bdz);
    const ux = l > 0.01 ? bdx / l : 0;
    const uz = l > 0.01 ? bdz / l : 1;   // ровно под дырой — уходим на юг
    cam.x += ux * k * Math.min(1, dt * 8);
    cam.z += uz * k * Math.min(1, dt * 8);
  }

  // сидя в палатке камера мягко переезжает на подстилку
  if (game.tent.inside) {
    cam.x = damp(cam.x, TENT.seat[0], 4, dt);
    cam.z = damp(cam.z, TENT.seat[2], 4, dt);
    cam.vx = cam.vz = 0;
    if (!lookId) {
      cam.yaw = damp(cam.yaw, game.tent.yaw, 3, dt);
      cam.pitch = damp(cam.pitch, -0.16, 3, dt);
    }
  }

  // в ракете камера привязана к кабине, смотреть можно куда угодно
  if (game.rocket.inside) {
    cam.x = ROCKET.cockpit[0];
    cam.z = ROCKET.cockpit[2];
    cam.vx = cam.vz = 0;
  }

  // мягкая граница прогулки: на полигоне гулять можно на километры
  const walkR = game.world === 'earth' ? 92 : G.R * 0.94;
  const r = Math.hypot(cam.x, cam.z);
  if (r > walkR && !game.rocket.inside) {
    const k = walkR / r;
    cam.x = lerp(cam.x, cam.x * k, 1 - Math.exp(-4 * dt));
    cam.z = lerp(cam.z, cam.z * k, 1 - Math.exp(-4 * dt));
  }

  const moving = Math.hypot(cam.vx, cam.vz);
  const stepBefore = Math.floor(bobPhase / Math.PI);
  bobPhase += moving * dt * 2.1;
  if (moving > 0.7 && Math.floor(bobPhase / Math.PI) !== stepBefore) soundStep();
  const bob = game.reduced ? 0 : Math.sin(bobPhase) * 0.022 * smoothstep(0, 2, moving);
  if (game.rocket.inside) {
    // на разгоне картинка чуть дрожит, поле зрения раскрывается
    const shake = ROCKET.thrust * airDensity(ROCKET.alt) * 0.006;
    cam.fov = damp(cam.fov, (1.02 + clamp(ROCKET.gforce - 1, 0, 2) * 0.05) / game.zoom, 3, dt);
    cam.yaw += (Math.random() - 0.5) * shake;
    cam.pitch += (Math.random() - 0.5) * shake;
  } else {
    cam.fov = damp(cam.fov, 1.02 / game.zoom, 3, dt);
  }

  const wantY = game.rocket.inside ? ROCKET.cockpit[1]
    : game.tent.inside ? TENT.seat[1] : eyeHeight(cam.x, cam.z);
  camBase = game.rocket.inside ? wantY : damp(camBase, wantY, game.tent.inside ? 4 : 12, dt);
  cam.y = camBase + (game.tent.inside || game.rocket.inside ? 0 : bob);

  // ветер громче на открытом месте и при ходьбе
  if (jazz.on) jazzSchedule();
  if (audio.ctx && audio.on) {
    setWindLevel(game.tent.inside ? 0.07 : 0.19 + Math.min(moving, 4) * 0.012);
    if (audio.src) audio.src.playbackRate.value = clamp(game.dilation, 1, 3);
  }

  // фигуры
  SHAPES.forEach((s, i) => {
    const focused = game.focusIndex === i;
    s.focus = damp(s.focus, focused ? 1 : 0, 6.0, dt);
    for (let a = 0; a < 3; a++) {
      s.pos[a] = lerp(s.home[a], s.grabPos[a], smoothstep(0, 1, s.focus));
    }
    s.rotY = damp(s.rotY, s.rotYTarget, 9, dt);
    s.rotX = damp(s.rotX, s.rotXTarget, 9, dt);
    s.zoom = damp(s.zoom, focused ? s.zoomTarget : 1, 7, dt);

    if (s.autoDraw) {
      s.progress = Math.min(1, s.progress + dt * 0.62);
      if (s.progress >= 1) { s.autoDraw = false; blip(1560, 0.16, 'sine', 0.05); }
      if (focused) syncUI();
    }

    s.cut = damp(s.cut, s.cutTarget, 4.5, dt);
    s.sep = damp(s.sep, s.sepTarget, 3.6, dt);
  });

  // панель обновляется, когда этап сменился сам собой (доехала анимация)
  const i = game.focusIndex;
  const sig = i < 0 ? 'none'
    : `${i}|${game.tool}|${Math.round(SHAPES[i].progress * 100)}|${SHAPES[i].cut > 0.9 ? 1 : 0}|${SHAPES[i].sepTarget > 0.02 ? 1 : 0}`;
  if (sig !== lastSig) { lastSig = sig; syncUI(); }

  // часы: показываем, как только расхождение становится заметным
  // часы расхождения нужны только там, где есть дыра
  const showClocks = game.world === 'earth' && game.dilation > 1.015;
  ui.clocks.classList.toggle('show', showClocks);
  if (showClocks) {
    ui.clockMe.textContent = mmss(game.proper);
    ui.clockFar.textContent = mmss(game.time);
    ui.clockRate.textContent = `×${game.dilation.toFixed(2)}`;
  }

  if (ui.toast.classList.contains('show') && game.proper > toastUntil && !game.wash.active) {
    ui.toast.classList.remove('show');
  }

  if (game.rocket.inside) {
    const ph = ROCKET.phase;
    const km = (ROCKET.alt + ROCKET.cruise) / 1000;
    const speed = Math.hypot(ROCKET.vel, ROCKET.cruiseVel);
    const speedTxt = speed > 900 ? `${(speed / 1000).toFixed(0)} км/с` : `${Math.round(speed)} м/с`;
    if (ph === 'pad') {
      ui.rocketInfo.textContent = 'На площадке. Подъём до 20 км занимает две минуты.';
    } else if (ph === 'cruise' || (ph === 'home' && ROCKET.cruise > 1)) {
      const range = (ROCKET.dest === 'quasar'
        ? quasarRange() - QUASAR_R
        : gammaRange() - (game.world === 'earth' ? GAMMA.R : PLANET_R)) / 1000;
      const rest = Math.abs((ph === 'cruise' ? destStop() : 0) - ROCKET.cruise);
      const v = Math.abs(ROCKET.cruiseVel);
      ui.rocketInfo.textContent =
        `до цели ${Math.round(range).toLocaleString('ru-RU')} км · ${(v / 1000).toFixed(0)} км/с · ` +
        `${ROCKET.gforce.toFixed(0)} g · ещё ${mmss(cruiseEta(rest, v))}` +
        (ROCKET.warp > 1 ? ` · время ×${ROCKET.warp}` : '');
    } else if (ROCKET.cruise > 1) {
      // висим в космосе на полпути или у самого квазара
      const range = (quasarRange() - QUASAR_R) / 1000;
      ui.rocketInfo.textContent =
        `до квазара ${Math.round(range).toLocaleString('ru-RU')} км · двигатели молчат`;
    } else {
      ui.rocketInfo.textContent =
        `${km < 10 ? km.toFixed(2) : Math.round(km)} км · ${speedTxt} · перегрузка ${ROCKET.gforce.toFixed(2)} g`;
    }
    const tag = ph + (ROCKET.cruise >= QUASAR_STOP - 1 ? '@' : '') + ROCKET.dest;
    if (tag !== game.rocket.shown) { game.rocket.shown = tag; syncRocket(); }
    engineLevel();
  }

  syncBombUI();
  syncTalkUI();
  updateBubble();
  if (CAR.inside) { syncCarUI(); carSoundLevel(); }
  fireLevel();

  // прицел и подсказки «взять фигуру» / «помыть руки»
  if (game.mode === 'walk') {
    const hit = pick(0, 0);
    game.hovered = hit;
    const home = game.world === 'earth';
    const nearShape = home && hit >= 0 && Math.hypot(cam.x - SHAPES[hit].home[0], cam.z - SHAPES[hit].home[2]) < 26;
    const nearWater = home && !game.wash.active && Math.hypot(cam.x - TANK.x, cam.z - TANK.z) < TANK.r + 2.2;
    const nearTent = home && !game.tent.inside && Math.hypot(cam.x - TENT.x, cam.z - TENT.z) < 4.2;
    const nearRocket = !game.rocket.inside && Math.hypot(cam.x - PAD.x, cam.z - PAD.z) < 6.5;
    const nearCar = !home && !CAR.inside && Math.hypot(cam.x - CAR.x, cam.z - CAR.z) < 4.5;
    const atBar = nearCafe();
    const atSith = !home && !CAR.inside && Math.hypot(cam.x - SITH.x, cam.z - SITH.z) < 5.5
      && !document.getElementById('talk').classList.contains('show');
    if (atBar) ui.prompt.textContent = 'Нажмите или E — взять кофе';
    else if (atSith) ui.prompt.textContent = 'Нажмите или E — поговорить';
    else if (nearShape) ui.prompt.textContent = 'Нажмите, чтобы взять';
    else if (nearWater) ui.prompt.textContent = 'Нажмите или E — помыть руки';
    else if (nearTent) ui.prompt.textContent = 'Нажмите или E — расположиться';
    else if (nearCar) ui.prompt.textContent = 'Нажмите или E — сесть за руль';
    else if (nearRocket) ui.prompt.textContent = 'Нажмите или E — сесть в ракету';
    const hot = atBar || atSith || nearShape || nearWater || nearTent || nearCar || nearRocket;
    ui.reticle.classList.toggle('hot', hot);
    ui.prompt.classList.toggle('show', hot);
  } else {
    ui.prompt.classList.remove('show');
  }
}

/* ============================================================
   Кадр
   ============================================================ */

let last = performance.now();
let frameAvg = 16, scaleCheck = 0;

/** Если кадры проседают — понижаем внутреннее разрешение, и наоборот. */
function autoScale(dt) {
  frameAvg = frameAvg * 0.9 + dt * 1000 * 0.1;
  scaleCheck += dt;
  if (scaleCheck < 1.2) return;
  scaleCheck = 0;
  if (frameAvg > 30 && renderScale > 0.6) renderScale = Math.max(0.6, renderScale - 0.15);
  else if (frameAvg < 17 && renderScale < 1) renderScale = Math.min(1, renderScale + 0.1);
}

function frame(now) {
  // отметка кадра иногда оказывается раньше performance.now() — отрицательный
  // шаг развалил бы демпферы, поэтому зажимаем сразу
  const dt = clamp((now - last) / 1000, 0, 0.05);
  last = now;
  autoScale(dt);
  update(dt);
  drawScene();
  requestAnimationFrame(frame);
}

cam.y = camBase = eyeHeight(cam.x, cam.z);
drawScene();
requestAnimationFrame(frame);
syncUI();
