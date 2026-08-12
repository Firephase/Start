'use strict';

/* ============================================================
   Ханойская башня — игра на чистом JS
   Цель: перенести всю пирамиду со стержня A на стержень C
   за минимальное число ходов (2^n − 1).
   ============================================================ */

const MIN_DISKS = 3;
const MAX_DISKS = 12;
const PICKER_MAX = 10;
const TARGET_PEG = 2;
const STORE_KEY = 'hanoi-best-v1';
const BASE_DURATION = 420; // мс на один ход в ручном режиме

const el = {
  picker: document.getElementById('disk-picker'),
  speed: document.getElementById('speed'),
  speedValue: document.getElementById('speed-value'),
  btnNew: document.getElementById('btn-new'),
  btnUndo: document.getElementById('btn-undo'),
  btnHint: document.getElementById('btn-hint'),
  btnAuto: document.getElementById('btn-auto'),
  btnSound: document.getElementById('btn-sound'),
  statMoves: document.getElementById('stat-moves'),
  statMin: document.getElementById('stat-min'),
  statLeft: document.getElementById('stat-left'),
  statTime: document.getElementById('stat-time'),
  statBest: document.getElementById('stat-best'),
  progress: document.getElementById('progress-fill'),
  badge: document.getElementById('optimal-badge'),
  board: document.getElementById('board'),
  towers: Array.from(document.querySelectorAll('.tower')),
  stacks: Array.from(document.querySelectorAll('.stack')),
  message: document.getElementById('message'),
  winOverlay: document.getElementById('win-overlay'),
  winTitle: document.getElementById('win-title'),
  winSub: document.getElementById('win-sub'),
  winCrown: document.getElementById('win-crown'),
  winMoves: document.getElementById('win-moves'),
  winMin: document.getElementById('win-min'),
  winTime: document.getElementById('win-time'),
  winStars: document.getElementById('win-stars'),
  winRecord: document.getElementById('win-record'),
  btnAgain: document.getElementById('btn-again'),
  btnHarder: document.getElementById('btn-harder'),
  confetti: document.getElementById('confetti'),
};

const state = {
  n: 4,
  pegs: [[], [], []],   // pegs[i][0] — нижний диск, последний элемент — верхний
  disks: new Map(),     // размер диска -> DOM-элемент
  history: [],          // [{from, to}, ...]
  moves: 0,
  startedAt: 0,
  elapsed: 0,
  timerId: 0,
  selected: null,
  animating: false,
  auto: false,
  won: false,
  hintsUsed: 0,
  undosUsed: 0,
  autoUsed: false,
  sound: true,
};

/* ---------------- вспомогательное ---------------- */

const minMovesFor = (n) => Math.pow(2, n) - 1;
const topDisk = (peg) => state.pegs[peg][state.pegs[peg].length - 1] || null;
const pegOfDisk = (size) => state.pegs.findIndex((p) => p.includes(size));

/** Согласование числительных: 1 ход, 2 хода, 5 ходов. */
function plural(count, one, few, many) {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

const moveWord = (n) => `${n} ${plural(n, 'ход', 'хода', 'ходов')}`;
const diskWord = (n) => `${n} ${plural(n, 'диск', 'диска', 'дисков')}`;

function formatTime(ms) {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function canMove(from, to) {
  if (from === to) return false;
  const disk = topDisk(from);
  if (disk === null) return false;
  const dest = topDisk(to);
  return dest === null || disk < dest;
}

/** Оптимальный следующий ход из ЛЮБОЙ корректной позиции. */
function optimalMove(size = state.n, target = TARGET_PEG) {
  if (size === 0) return null;
  const cur = pegOfDisk(size);
  if (cur === target) return optimalMove(size - 1, target);
  const other = 3 - cur - target;
  return optimalMove(size - 1, other) || { from: cur, to: target };
}

/** Сколько ходов минимально осталось из текущей позиции. */
function movesLeft(size = state.n, target = TARGET_PEG) {
  if (size === 0) return 0;
  const cur = pegOfDisk(size);
  if (cur === target) return movesLeft(size - 1, target);
  const other = 3 - cur - target;
  return movesLeft(size - 1, other) + 1 + (Math.pow(2, size - 1) - 1);
}

/* ---------------- звук ---------------- */

let audioCtx = null;

function beep(freq, duration = 0.11, type = 'triangle', volume = 0.05) {
  if (!state.sound) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(volume, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) { /* звук не критичен */ }
}

const soundLift = () => beep(520, 0.08, 'sine', 0.035);
const soundDrop = (size) => beep(240 + (state.n - size) * 34, 0.13, 'triangle', 0.05);
const soundDeny = () => beep(120, 0.18, 'sawtooth', 0.04);
const soundWin = () => [523, 659, 784, 1047].forEach((f, i) =>
  setTimeout(() => beep(f, 0.22, 'sine', 0.06), i * 130));

/* ---------------- рекорды ---------------- */

function loadRecords() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; }
  catch (e) { return {}; }
}

function saveRecord(n, moves, time) {
  const all = loadRecords();
  const prev = all[n];
  if (prev && (prev.moves < moves || (prev.moves === moves && prev.time <= time))) return false;
  all[n] = { moves, time };
  try { localStorage.setItem(STORE_KEY, JSON.stringify(all)); } catch (e) { /* приватный режим */ }
  return true;
}

/* ---------------- отрисовка ---------------- */

function buildPicker() {
  for (let n = MIN_DISKS; n <= PICKER_MAX; n++) {
    const b = document.createElement('button');
    b.className = 'disk-btn';
    b.textContent = n;
    b.dataset.n = n;
    b.addEventListener('click', () => newGame(n));
    el.picker.appendChild(b);
  }
}

function syncPicker() {
  el.picker.querySelectorAll('.disk-btn').forEach((b) => {
    b.classList.toggle('active', Number(b.dataset.n) === state.n);
  });
}

function layoutDisks() {
  const stackH = el.stacks[0].clientHeight;
  const towerW = el.towers[0].clientWidth;
  const height = Math.max(11, Math.min(32, Math.floor(stackH / state.n) - 2));
  const maxW = Math.max(70, Math.min(towerW - 12, 280));
  const minW = Math.max(38, Math.round(maxW * 0.32));

  state.disks.forEach((node, size) => {
    const t = state.n > 1 ? (size - 1) / (state.n - 1) : 1;
    node.style.width = `${Math.round(minW + (maxW - minW) * t)}px`;
    node.style.height = `${height}px`;
    node.style.fontSize = `${Math.min(12, Math.max(8, height - 8))}px`;
    node.textContent = height >= 15 ? String(size) : '';
  });
}

function markTopDisks() {
  state.disks.forEach((node) => node.classList.remove('top'));
  state.pegs.forEach((peg) => {
    const size = peg[peg.length - 1];
    if (size) state.disks.get(size).classList.add('top');
  });
}

function setMessage(text, tone = '') {
  el.message.textContent = text;
  el.message.className = `message ${tone}`;
}

function flash(node) {
  node.classList.remove('flash');
  void node.offsetWidth;
  node.classList.add('flash');
}

function updateStats(animateMoves = false) {
  const min = minMovesFor(state.n);
  const left = state.won ? 0 : movesLeft();

  el.statMoves.textContent = state.moves;
  el.statMin.textContent = min;
  el.statLeft.textContent = left;
  el.statTime.textContent = formatTime(currentElapsed());
  if (animateMoves) flash(el.statMoves);

  const best = loadRecords()[state.n];
  el.statBest.textContent = best ? `${best.moves}` : '—';
  el.statBest.title = best ? `${best.moves} ходов за ${formatTime(best.time)}` : 'рекорда ещё нет';

  const done = min - left;
  el.progress.style.width = `${Math.max(0, Math.min(100, (done / min) * 100))}%`;
  el.badge.classList.toggle('on', !state.won && state.moves + left === min);

  el.btnUndo.disabled = state.history.length === 0 || state.auto || state.won;
  el.btnHint.disabled = state.won || state.auto;
}

function currentElapsed() {
  return state.startedAt ? state.elapsed + (Date.now() - state.startedAt) : state.elapsed;
}

function startTimer() {
  if (state.startedAt || state.won) return;
  state.startedAt = Date.now();
  state.timerId = setInterval(() => {
    el.statTime.textContent = formatTime(currentElapsed());
  }, 250);
}

function stopTimer() {
  if (state.startedAt) {
    state.elapsed += Date.now() - state.startedAt;
    state.startedAt = 0;
  }
  clearInterval(state.timerId);
  state.timerId = 0;
}

/* ---------------- новая игра ---------------- */

function newGame(n = state.n) {
  stopAuto();
  stopTimer();

  state.n = Math.max(MIN_DISKS, Math.min(MAX_DISKS, n));
  state.pegs = [[], [], []];
  state.disks.clear();
  state.history = [];
  state.moves = 0;
  state.elapsed = 0;
  state.startedAt = 0;
  state.selected = null;
  state.animating = false;
  state.won = false;
  state.hintsUsed = 0;
  state.undosUsed = 0;
  state.autoUsed = false;

  el.stacks.forEach((s) => (s.innerHTML = ''));
  el.winOverlay.hidden = true;
  clearHighlights();

  for (let size = state.n; size >= 1; size--) {
    const node = document.createElement('div');
    node.className = 'disk';
    node.dataset.size = size;
    node.style.setProperty('--h', String(Math.round((190 + ((size - 1) / state.n) * 320) % 360)));
    node.addEventListener('pointerdown', onDiskPointerDown);
    state.disks.set(size, node);
    el.stacks[0].appendChild(node); // column-reverse: первый ребёнок — нижний
    state.pegs[0].push(size);
  }
  // pegs[0] должен идти снизу вверх: [n, n-1, ..., 1] — так и получилось
  layoutDisks();
  markTopDisks();
  syncPicker();
  updateStats();
  setMessage(`${diskWord(state.n)} — минимум ${moveWord(minMovesFor(state.n))}. Удачи!`);
}

/* ---------------- анимация хода ---------------- */

function duration() {
  return state.auto ? Math.max(70, BASE_DURATION / Number(el.speed.value)) : BASE_DURATION;
}

/**
 * Переносит DOM-элемент в новый стек и проигрывает дугу «поднять → перенести → опустить».
 * Возвращает Promise завершения анимации.
 */
function animateTo(node, toPeg, arc = true) {
  const first = node.getBoundingClientRect();
  node.style.transform = '';
  el.stacks[toPeg].appendChild(node);
  const last = node.getBoundingClientRect();

  const dx = first.left - last.left;
  const dy = first.top - last.top;
  if (!dx && !dy) return Promise.resolve();

  const boardTop = el.board.getBoundingClientRect().top + 8;
  const liftFrom = Math.min(dy, boardTop - last.top);
  const liftTo = Math.min(0, boardTop - last.top);

  const frames = arc
    ? [
        { transform: `translate(${dx}px, ${dy}px)`, offset: 0, easing: 'ease-in' },
        { transform: `translate(${dx}px, ${liftFrom}px)`, offset: 0.3, easing: 'ease-in-out' },
        { transform: `translate(0px, ${liftTo}px)`, offset: 0.68, easing: 'ease-in' },
        { transform: 'translate(0px, 0px)', offset: 1 },
      ]
    : [
        { transform: `translate(${dx}px, ${dy}px)` },
        { transform: 'translate(0px, 0px)' },
      ];

  const anim = node.animate(frames, {
    duration: duration(),
    easing: arc ? 'linear' : 'cubic-bezier(.3,1.2,.5,1)',
  });
  return anim.finished.catch(() => {});
}

/* ---------------- ход ---------------- */

async function move(from, to, { record = true, arc = true } = {}) {
  if (state.animating || state.won) return false;
  if (!canMove(from, to)) {
    denyFeedback(to);
    return false;
  }

  const size = state.pegs[from].pop();
  state.pegs[to].push(size);
  if (record) {
    state.history.push({ from, to });
    state.moves++;
  }

  const node = state.disks.get(size);
  node.classList.remove('selected');
  state.selected = null;
  clearHighlights();
  markTopDisks();
  startTimer();
  soundLift();

  state.animating = true;
  await animateTo(node, to, arc);
  state.animating = false;
  soundDrop(size);

  updateStats(record);
  checkWin();
  return true;
}

function denyFeedback(peg) {
  const tower = el.towers[peg];
  tower.classList.remove('shake');
  void tower.offsetWidth;
  tower.classList.add('shake');
  setTimeout(() => tower.classList.remove('shake'), 350);
  soundDeny();
  setMessage('Нельзя класть больший диск на меньший!', 'bad');
}

async function undo() {
  if (!state.history.length || state.animating || state.auto || state.won) return;
  const last = state.history.pop();
  const size = state.pegs[last.to].pop();
  state.pegs[last.from].push(size);
  state.moves++;
  state.undosUsed++;

  const node = state.disks.get(size);
  deselect();
  markTopDisks();
  state.animating = true;
  await animateTo(node, last.from);
  state.animating = false;
  soundDrop(size);
  updateStats();
  setMessage('Ход отменён (он всё равно засчитан в счётчик ходов).');
  checkWin();
}

/* ---------------- выбор / подсветка ---------------- */

function clearHighlights() {
  el.towers.forEach((t) => t.classList.remove('drop-ok', 'drop-bad', 'hint-from', 'hint-to'));
  state.disks.forEach((d) => d.classList.remove('hint-disk'));
}

function deselect() {
  if (state.selected !== null) {
    const size = topDisk(state.selected);
    if (size) state.disks.get(size).classList.remove('selected');
    state.selected = null;
  }
  clearHighlights();
}

function select(peg) {
  const size = topDisk(peg);
  if (size === null) {
    setMessage('На этом стержне нет дисков.');
    return;
  }
  deselect();
  state.selected = peg;
  state.disks.get(size).classList.add('selected');
  el.towers.forEach((t, i) => {
    if (i === peg) return;
    t.classList.add(canMove(peg, i) ? 'drop-ok' : 'drop-bad');
  });
  soundLift();
  setMessage(`Взят диск ${size}. Куда положим?`);
}

function tapTower(peg) {
  if (state.animating || state.auto || state.won) return;
  if (state.selected === null) {
    select(peg);
  } else if (state.selected === peg) {
    deselect();
    setMessage('Диск возвращён на место.');
  } else {
    const from = state.selected;
    if (canMove(from, peg)) {
      move(from, peg);
      setMessage('');
    } else {
      denyFeedback(peg);
    }
  }
}

/* ---------------- перетаскивание ---------------- */

let drag = null;

function onDiskPointerDown(event) {
  if (state.animating || state.auto || state.won) return;
  const node = event.currentTarget;
  const size = Number(node.dataset.size);
  const peg = pegOfDisk(size);
  if (topDisk(peg) !== size) {
    denyFeedback(peg);
    setMessage('Двигать можно только верхний диск.', 'bad');
    return;
  }

  drag = { node, size, peg, startX: event.clientX, startY: event.clientY, active: false };
  node.setPointerCapture(event.pointerId);
  node.addEventListener('pointermove', onDiskPointerMove);
  node.addEventListener('pointerup', onDiskPointerUp);
  node.addEventListener('pointercancel', onDiskPointerUp);
  event.preventDefault();
}

function pegUnderPointer(x, y) {
  let best = null;
  el.towers.forEach((t, i) => {
    const r = t.getBoundingClientRect();
    if (x >= r.left && x <= r.right && y >= r.top - 120 && y <= r.bottom + 120) best = i;
  });
  return best;
}

function onDiskPointerMove(event) {
  if (!drag) return;
  const dx = event.clientX - drag.startX;
  const dy = event.clientY - drag.startY;

  if (!drag.active && Math.hypot(dx, dy) < 6) return;
  if (!drag.active) {
    drag.active = true;
    drag.node.classList.add('dragging');
    drag.node.classList.remove('selected');
    state.selected = null;
    soundLift();
  }

  drag.node.style.transform = `translate(${dx}px, ${dy}px)`;
  const over = pegUnderPointer(event.clientX, event.clientY);
  el.towers.forEach((t, i) => {
    t.classList.toggle('drop-ok', i === over && i !== drag.peg && canMove(drag.peg, i));
    t.classList.toggle('drop-bad', i === over && i !== drag.peg && !canMove(drag.peg, i));
  });
}

async function onDiskPointerUp(event) {
  if (!drag) return;
  const current = drag;
  drag = null;

  current.node.removeEventListener('pointermove', onDiskPointerMove);
  current.node.removeEventListener('pointerup', onDiskPointerUp);
  current.node.removeEventListener('pointercancel', onDiskPointerUp);
  current.node.classList.remove('dragging');
  clearHighlights();

  if (!current.active) {         // это был обычный клик
    tapTower(current.peg);
    return;
  }

  const target = pegUnderPointer(event.clientX, event.clientY);
  if (target !== null && target !== current.peg && canMove(current.peg, target)) {
    await move(current.peg, target, { arc: false });
    setMessage('');
  } else {
    if (target !== null && target !== current.peg) denyFeedback(target);
    state.animating = true;
    await animateTo(current.node, current.peg, false);
    state.animating = false;
  }
}

/* ---------------- подсказка и авто-решение ---------------- */

function hint() {
  if (state.won || state.animating || state.auto) return;
  const next = optimalMove();
  if (!next) return;
  state.hintsUsed++;
  clearHighlights();
  const size = topDisk(next.from);
  state.disks.get(size).classList.add('hint-disk');
  el.towers[next.from].classList.add('hint-from');
  el.towers[next.to].classList.add('hint-to');
  setMessage(`Подсказка: диск ${size} со стержня ${'ABC'[next.from]} на ${'ABC'[next.to]}.`, 'good');
  setTimeout(clearHighlights, 2200);
}

async function autoSolve() {
  if (state.auto) { stopAuto(); return; }
  if (state.won) return;

  deselect();
  state.auto = true;
  state.autoUsed = true;
  el.btnAuto.textContent = '⏸ Стоп';
  el.btnAuto.classList.add('muted');
  updateStats();
  setMessage('Смотрим оптимальное решение…');

  while (state.auto && !state.won) {
    const next = optimalMove();
    if (!next) break;
    await move(next.from, next.to);
    if (state.auto) await new Promise((r) => setTimeout(r, Math.max(20, duration() * 0.12)));
  }
  stopAuto();
}

function stopAuto() {
  state.auto = false;
  el.btnAuto.textContent = '▶ Авто-решение';
  el.btnAuto.classList.remove('muted');
  updateStats();
}

/* ---------------- победа ---------------- */

function checkWin() {
  if (state.pegs[TARGET_PEG].length !== state.n) return;
  state.won = true;
  stopAuto();
  stopTimer();
  updateStats();

  const min = minMovesFor(state.n);
  const clean = !state.autoUsed && state.hintsUsed === 0 && state.undosUsed === 0;
  const perfect = clean && state.moves === min;
  const isRecord = clean && saveRecord(state.n, state.moves, state.elapsed);

  const stars = state.autoUsed ? 0 : state.moves === min ? 3 : state.moves <= Math.ceil(min * 1.35) ? 2 : 1;
  el.winStars.textContent = '★'.repeat(stars) + '☆'.repeat(3 - stars);
  el.winCrown.textContent = state.autoUsed ? '🤖' : perfect ? '🏆' : stars === 3 ? '🥇' : stars === 2 ? '🥈' : '🎖';
  el.winTitle.textContent = state.autoUsed ? 'Решено автоматом' : perfect ? 'Идеально!' : 'Башня собрана!';
  el.winSub.textContent = state.autoUsed
    ? `Так выглядит оптимальное решение для башни из ${state.n} дисков. Теперь попробуйте сами!`
    : perfect
      ? `${diskWord(state.n)} за минимально возможные ${moveWord(min)}.`
      : state.moves === min
        ? 'Минимум ходов достигнут (были подсказки или отмены).'
        : `Вы уложились в ${moveWord(state.moves)} при минимуме ${min}. Попробуйте точнее!`;
  el.winMoves.textContent = state.moves;
  el.winMin.textContent = min;
  el.winTime.textContent = formatTime(state.elapsed);
  el.winRecord.hidden = !isRecord;
  el.btnHarder.disabled = state.n >= MAX_DISKS;

  el.winOverlay.hidden = false;
  soundWin();
  launchConfetti();
  setMessage('Победа! 🎉', 'good');
}

/* ---------------- конфетти ---------------- */

function launchConfetti() {
  const canvas = el.confetti;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const parts = Array.from({ length: 130 }, () => ({
    x: w / 2 + (Math.random() - 0.5) * w * 0.5,
    y: h / 2 - 40,
    vx: (Math.random() - 0.5) * 9,
    vy: -Math.random() * 11 - 3,
    size: 4 + Math.random() * 6,
    rot: Math.random() * Math.PI,
    spin: (Math.random() - 0.5) * 0.28,
    hue: Math.floor(Math.random() * 360),
    life: 1,
  }));

  const started = performance.now();
  (function tick(now) {
    if (el.winOverlay.hidden) { ctx.clearRect(0, 0, w, h); return; }
    ctx.clearRect(0, 0, w, h);
    parts.forEach((p) => {
      p.vy += 0.28;
      p.vx *= 0.995;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.spin;
      p.life = Math.max(0, 1 - (now - started) / 3400);
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.globalAlpha = p.life;
      ctx.fillStyle = `hsl(${p.hue} 90% 62%)`;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
      ctx.restore();
    });
    if (now - started < 3400) requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, w, h);
  })(started);
}

/* ---------------- события ---------------- */

el.towers.forEach((tower) => {
  tower.addEventListener('click', (e) => {
    if (e.target.classList.contains('disk')) return; // клик по диску обрабатывает pointerup
    tapTower(Number(tower.dataset.peg));
  });
});

el.btnNew.addEventListener('click', () => newGame());
el.btnUndo.addEventListener('click', undo);
el.btnHint.addEventListener('click', hint);
el.btnAuto.addEventListener('click', autoSolve);
el.btnAgain.addEventListener('click', () => newGame());
el.btnHarder.addEventListener('click', () => newGame(state.n + 1));

el.btnSound.addEventListener('click', () => {
  state.sound = !state.sound;
  el.btnSound.textContent = state.sound ? '🔊' : '🔇';
  el.btnSound.classList.toggle('muted', !state.sound);
});

el.speed.addEventListener('input', () => {
  el.speedValue.textContent = `×${el.speed.value}`;
});

document.addEventListener('keydown', (e) => {
  const key = e.key.toLowerCase();
  if (['1', '2', '3'].includes(key)) { tapTower(Number(key) - 1); return; }
  if (key === 'u' || key === 'г') { undo(); return; }
  if (key === 'h' || key === 'р') { hint(); return; }
  if (key === 'n' || key === 'т') { newGame(); return; }
  if (key === 'escape') { deselect(); return; }
  if (e.code === 'Space') { e.preventDefault(); autoSolve(); }
});

let resizeRaf = 0;
window.addEventListener('resize', () => {
  cancelAnimationFrame(resizeRaf);
  resizeRaf = requestAnimationFrame(layoutDisks);
});

/* ---------------- старт ---------------- */

buildPicker();
el.speedValue.textContent = `×${el.speed.value}`;
newGame(4);
