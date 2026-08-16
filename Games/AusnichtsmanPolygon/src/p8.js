/* ============================================================
   Мягкий джаз в палатке — играется процедурно, по нотам
   ============================================================ */

const jazz = {
  on: false, bus: null, next: 0, step: 0,
  bpm: 76,
  // ii – V – I – VI: спокойный круг, повторяется бесконечно
  bars: [
    { chord: [62, 65, 69, 76], bass: [38, 45, 41, 43] },  // Dm9
    { chord: [59, 65, 67, 76], bass: [43, 50, 47, 46] },  // G13
    { chord: [64, 67, 71, 74], bass: [36, 43, 40, 41] },  // Cmaj9
    { chord: [60, 64, 67, 72], bass: [45, 40, 44, 47] },  // Am7
  ],
};

const midiHz = (n) => 440 * Math.pow(2, (n - 69) / 12);

function jazzBus() {
  if (jazz.bus) return jazz.bus;
  const ctx = audio.ctx;
  const g = ctx.createGain();
  g.gain.value = 0.0001;
  const warm = ctx.createBiquadFilter();
  warm.type = 'lowpass';
  warm.frequency.value = 2400;
  g.connect(warm).connect(ctx.destination);
  jazz.bus = g;
  return g;
}

/** Электропиано: две расстроенные синусоиды с мягкой атакой. */
function jazzKey(t, midi, dur, vol) {
  const ctx = audio.ctx, bus = jazzBus();
  for (const [mul, det, amp] of [[1, 0, 1], [1, 5, 0.5], [2, -4, 0.18]]) {
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.value = midiHz(midi) * mul * Math.pow(2, det / 1200);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol * amp, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(bus);
    o.start(t);
    o.stop(t + dur + 0.05);
  }
}

/** Контрабас: короткий щипок с быстрым спадом. */
function jazzBass(t, midi, dur, vol) {
  const ctx = audio.ctx, bus = jazzBus();
  const o = ctx.createOscillator();
  o.type = 'triangle';
  o.frequency.setValueAtTime(midiHz(midi) * 1.01, t);
  o.frequency.exponentialRampToValueAtTime(midiHz(midi), t + 0.06);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(vol, t + 0.015);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  const f = ctx.createBiquadFilter();
  f.type = 'lowpass';
  f.frequency.value = 420;
  o.connect(f).connect(g).connect(bus);
  o.start(t);
  o.stop(t + dur + 0.05);
}

/** Щётки по малому барабану и тихая тарелка. */
function jazzBrush(t, vol, bright) {
  const ctx = audio.ctx, bus = jazzBus();
  const len = Math.floor(ctx.sampleRate * 0.28);
  const b = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < len; i++) {
    const k = i / len;
    d[i] = (Math.random() * 2 - 1) * Math.pow(1 - k, 2.0) * (0.5 + 0.5 * Math.sin(k * 22));
  }
  const src = ctx.createBufferSource();
  src.buffer = b;
  const f = ctx.createBiquadFilter();
  f.type = 'bandpass';
  f.frequency.value = bright;
  f.Q.value = 0.8;
  const g = ctx.createGain();
  g.gain.value = vol;
  src.connect(f).connect(g).connect(bus);
  src.start(t);
}

/** Планировщик: подкладывает ноты на полсекунды вперёд. */
function jazzSchedule() {
  if (!jazz.on || !audio.ctx) return;
  const ctx = audio.ctx;
  const beat = 60 / jazz.bpm;
  if (jazz.next < ctx.currentTime) jazz.next = ctx.currentTime + 0.08;

  while (jazz.next < ctx.currentTime + 0.6) {
    const t = jazz.next;
    const bar = jazz.bars[Math.floor(jazz.step / 4) % jazz.bars.length];
    const beatInBar = jazz.step % 4;

    // бас шагает по четвертям
    jazzBass(t, bar.bass[beatInBar], beat * 0.85, 0.16);

    // аккорд ложится на первую и слегка синкопированную третью долю
    if (beatInBar === 0 || beatInBar === 2) {
      const spread = beatInBar === 0 ? 0 : 0.012;
      bar.chord.forEach((n, i) => {
        jazzKey(t + i * spread + (beatInBar === 2 ? beat * 0.33 : 0), n, beat * 2.1, 0.055);
      });
    }
    // одинокая нота мелодии поверх — раз в такт, вразнобой
    if (beatInBar === 3 && Math.random() < 0.55) {
      const top = bar.chord[bar.chord.length - 1] + [0, 2, 3, 5, 7][Math.floor(Math.random() * 5)];
      jazzKey(t + beat * 0.66, top, beat * 1.4, 0.045);
    }

    // щётки: шорох на 2 и 4, тихая тарелка на каждую долю со свингом
    jazzBrush(t, beatInBar % 2 === 1 ? 0.030 : 0.014, beatInBar % 2 === 1 ? 1700 : 5200);
    jazzBrush(t + beat * 0.66, 0.010, 6400);

    jazz.next += beat;
    jazz.step++;
  }
}

function jazzSetLevel(v) {
  if (!audio.ctx || !jazz.bus) return;
  jazz.bus.gain.setTargetAtTime(Math.max(0.0001, v), audio.ctx.currentTime, 0.8);
}

function jazzStart() {
  if (!audio.ctx || !audio.on) return;
  jazzBus();
  jazz.on = true;
  jazz.next = audio.ctx.currentTime + 0.1;
  jazzSetLevel(0.5);
}

function jazzStop() {
  jazzSetLevel(0);
  jazz.on = false;
}

/* ============================================================
   Дневничок
   ============================================================ */

const DIARY_KEY = 'ausnichtsman-diary-v1';

function diaryLoad() {
  try { return JSON.parse(localStorage.getItem(DIARY_KEY)) || []; }
  catch (e) { return []; }
}

function diarySave(list) {
  try { localStorage.setItem(DIARY_KEY, JSON.stringify(list.slice(-60))); } catch (e) { /* приватный режим */ }
}

/** Внутриигровая дата: сутки идут пять минут, рассвет считаем шестью утра. */
function gameStamp() {
  const day = Math.floor(game.time / DAY_LENGTH) + 1;
  const hours = (dayPhase * 24 + 6) % 24;
  const hh = String(Math.floor(hours)).padStart(2, '0');
  const mm = String(Math.floor((hours % 1) * 60)).padStart(2, '0');
  return `День ${day} · ${hh}:${mm}`;
}

const diary = {
  el: null, pages: null, input: null, pen: null,
  open: false,
  entries: [],
};

function diaryInit() {
  diary.el = document.getElementById('diary');
  diary.pages = document.getElementById('diary-entries');
  diary.input = document.getElementById('diary-input');
  diary.pen = document.getElementById('diary-pen');
  diary.entries = diaryLoad();

  document.getElementById('diary-write').addEventListener('click', diaryWrite);
  document.getElementById('diary-close').addEventListener('click', () => diaryToggle(false));
  diary.input.addEventListener('input', () => {
    diary.pen.classList.add('writing');
    clearTimeout(diary.penTimer);
    diary.penTimer = setTimeout(() => diary.pen.classList.remove('writing'), 400);
  });
  diary.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); diaryWrite(); }
    e.stopPropagation();
  });
  diaryRender();
}

function diaryRender() {
  if (!diary.pages) return;
  if (!diary.entries.length) {
    diary.pages.innerHTML = '<p class="diary-empty">Страница пока пуста. Первая мысль — за вами.</p>';
    return;
  }
  diary.pages.innerHTML = diary.entries
    .slice()
    .reverse()
    .map((e) => `<div class="diary-entry"><span class="diary-when">${escapeHtml(e.when)}</span>` +
                `<span class="diary-text">${escapeHtml(e.text)}</span></div>`)
    .join('');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function diaryWrite() {
  const text = diary.input.value.trim();
  if (!text) return;
  diary.entries.push({ when: gameStamp(), text });
  diarySave(diary.entries);
  diary.input.value = '';
  diaryRender();
  diary.pages.scrollTop = 0;
  // короткий скрип пера
  if (audio.ctx && audio.on) {
    blip(2100 + Math.random() * 400, 0.05, 'triangle', 0.02);
    setTimeout(() => blip(1500, 0.07, 'triangle', 0.015), 70);
  }
  toast('Записано в блокнот');
}

function diaryToggle(open) {
  diary.open = open;
  diary.el.classList.toggle('show', open);
  if (open) setTimeout(() => diary.input.focus(), 60);
  else diary.input.blur();
}
