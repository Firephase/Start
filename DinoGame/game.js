// Кувыркающиеся Динозаврики — главный игровой скрипт

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

const scoreEl  = document.getElementById('score');
const bestEl   = document.getElementById('best');
const dinosEl  = document.getElementById('dinos');
const overlay  = document.getElementById('overlay');
const ui       = document.getElementById('ui');
const startBtn = document.getElementById('startBtn');
const finalEl  = document.getElementById('finalScore');

// ---------- helpers ----------
const rand = (a, b) => Math.random() * (b - a) + a;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// ---------- constants ----------
const GRAVITY = 1600;          // px/s²
const JUMP_VY = -620;
const ROLL_JUMP_VY = -480;
const GROUND_OFFSET = 0.62;    // fraction of canvas height

const DINO_COLORS = ['#4CAF50','#FF5722','#2196F3','#FF9800','#9C27B0','#00BCD4'];
const EYE_WHITE = '#fff';
const EYE_PUPIL = '#111';

// ---------- state ----------
let W, H, groundY;
let state = 'idle';    // idle | playing | dead
let score = 0;
let best  = +localStorage.getItem('dinoBest') || 0;
let speed = 280;       // px/s, increases over time
let elapsed = 0;
let lastTime = 0;
let lastClickTime = 0;

let dinos    = [];
let obstacles= [];
let clouds   = [];
let coins    = [];
let particles= [];
let spawnTimer = 0;
let cloudTimer = 0;
let coinTimer  = 0;

bestEl.textContent = best;

// ---------- resize ----------
function resize() {
  W = canvas.width  = window.innerWidth;
  H = canvas.height = window.innerHeight;
  groundY = H * GROUND_OFFSET;
}
window.addEventListener('resize', resize);
resize();

// ---------- Dino class ----------
class Dino {
  constructor(x, color, offset = 0) {
    this.x = x;
    this.y = groundY;
    this.vy = 0;
    this.onGround = true;
    this.angle = 0;
    this.rotSpeed = 0;
    this.color = color;
    this.r = 28;          // radius (body half-size)
    this.squish = 1;      // y scale for landing squish
    this.squishVel = 0;
    this.flailing = false; // rolling in air
    this.trail = [];
    this.offset = offset; // horizontal offset in formation
    this.jumpCount = 0;
  }

  jump(isRoll = false) {
    if (this.jumpCount >= 2) return;
    this.vy = isRoll ? ROLL_JUMP_VY : JUMP_VY;
    this.onGround = false;
    this.jumpCount++;
    if (isRoll || this.jumpCount === 2) {
      this.flailing = true;
      this.rotSpeed = rand(600, 900) * (Math.random() > 0.5 ? 1 : -1);
    } else {
      this.rotSpeed = 0;
    }
    spawnBurst(this.x, groundY, this.color, 8);
  }

  update(dt) {
    // gravity
    if (!this.onGround) {
      this.vy += GRAVITY * dt;
      this.y  += this.vy * dt;
    }

    // land
    if (this.y >= groundY) {
      this.y = groundY;
      if (this.vy > 200) {
        this.squish = 0.55;
        this.squishVel = 8;
        spawnBurst(this.x, groundY, this.color, 5);
      }
      this.vy = 0;
      this.onGround = true;
      this.flailing = false;
      this.jumpCount = 0;
      this.rotSpeed = 0;
    }

    // rotation
    if (this.flailing) {
      this.angle += this.rotSpeed * dt;
    } else {
      // slow spin while grounded (idle wobble)
      if (this.onGround) {
        this.angle = Math.sin(elapsed * 3 + this.offset) * 0.12;
      } else {
        this.angle += this.rotSpeed * dt;
      }
    }

    // squish spring
    this.squish += this.squishVel * dt * 5;
    this.squishVel -= (this.squish - 1) * 30 * dt;
    this.squishVel *= 0.85;

    // trail
    this.trail.push({ x: this.x, y: this.y, a: this.angle, t: 0 });
    if (this.trail.length > 6) this.trail.shift();
    this.trail.forEach(t => t.t += dt);
  }

  draw() {
    // trail
    this.trail.forEach((t, i) => {
      const alpha = (i / this.trail.length) * 0.25;
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.translate(t.x, t.y);
      ctx.rotate(t.a);
      ctx.scale(1, this.squish);
      drawDinoShape(ctx, this.r, this.color);
      ctx.restore();
    });

    // main body
    ctx.save();
    ctx.translate(this.x, this.y);
    ctx.rotate(this.angle);
    ctx.scale(1, this.squish);
    drawDinoShape(ctx, this.r, this.color);
    ctx.restore();
  }
}

function drawDinoShape(ctx, r, color) {
  // body (rounded rect)
  ctx.fillStyle = color;
  roundRect(ctx, -r * 0.7, -r * 1.3, r * 1.4, r * 1.4, r * 0.4);
  ctx.fill();

  // head
  ctx.fillStyle = color;
  roundRect(ctx, r * 0.1, -r * 1.9, r * 0.85, r * 0.75, r * 0.3);
  ctx.fill();

  // snout / mouth bump
  ctx.fillStyle = shadeColor(color, -20);
  roundRect(ctx, r * 0.65, -r * 1.7, r * 0.4, r * 0.4, r * 0.2);
  ctx.fill();

  // eye white
  ctx.fillStyle = EYE_WHITE;
  ctx.beginPath();
  ctx.arc(r * 0.5, -r * 1.65, r * 0.18, 0, Math.PI * 2);
  ctx.fill();

  // pupil
  ctx.fillStyle = EYE_PUPIL;
  ctx.beginPath();
  ctx.arc(r * 0.56, -r * 1.64, r * 0.09, 0, Math.PI * 2);
  ctx.fill();

  // back spine
  ctx.fillStyle = shadeColor(color, 20);
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.moveTo(-r * 0.5 + i * r * 0.2, -r * 1.3);
    ctx.lineTo(-r * 0.38 + i * r * 0.2, -r * 1.7);
    ctx.lineTo(-r * 0.26 + i * r * 0.2, -r * 1.3);
    ctx.fill();
  }

  // legs (2 visible)
  ctx.fillStyle = shadeColor(color, -30);
  ctx.beginPath();
  ctx.ellipse(-r * 0.28, r * 0.12, r * 0.18, r * 0.28, 0.2, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(r * 0.22, r * 0.12, r * 0.18, r * 0.28, -0.2, 0, Math.PI * 2);
  ctx.fill();

  // tiny arms
  ctx.strokeStyle = shadeColor(color, -15);
  ctx.lineWidth = r * 0.12;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(r * 0.35, -r * 0.7);
  ctx.lineTo(r * 0.72, -r * 0.5);
  ctx.stroke();
}

function roundRect(ctx, x, y, w, h, rad) {
  ctx.beginPath();
  ctx.moveTo(x + rad, y);
  ctx.lineTo(x + w - rad, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + rad);
  ctx.lineTo(x + w, y + h - rad);
  ctx.quadraticCurveTo(x + w, y + h, x + w - rad, y + h);
  ctx.lineTo(x + rad, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - rad);
  ctx.lineTo(x, y + rad);
  ctx.quadraticCurveTo(x, y, x + rad, y);
  ctx.closePath();
}

function shadeColor(hex, pct) {
  const n = parseInt(hex.slice(1), 16);
  const r = clamp(((n >> 16) & 255) + pct, 0, 255);
  const g = clamp(((n >> 8)  & 255) + pct, 0, 255);
  const b = clamp((n & 255)         + pct, 0, 255);
  return `rgb(${r},${g},${b})`;
}

// ---------- Obstacle ----------
class Obstacle {
  constructor() {
    this.x = W + 60;
    const type = Math.random();
    if (type < 0.45) {
      // cactus group
      this.kind  = 'cactus';
      this.w     = rand(24, 42);
      this.h     = rand(50, 100);
      this.count = Math.floor(rand(1, 4));
    } else if (type < 0.75) {
      // rock
      this.kind = 'rock';
      this.w    = rand(40, 70);
      this.h    = rand(35, 60);
    } else {
      // flying pterodactyl
      this.kind = 'ptero';
      this.w    = 60;
      this.h    = 30;
      this.y    = groundY - rand(60, 140);
      this.wingPhase = 0;
    }
    if (!this.y) this.y = groundY;
  }

  update(dt) {
    this.x -= speed * dt;
    if (this.kind === 'ptero') this.wingPhase += dt * 5;
  }

  draw() {
    if (this.kind === 'cactus') {
      drawCactus(this.x, this.y, this.w, this.h, this.count);
    } else if (this.kind === 'rock') {
      drawRock(this.x, this.y, this.w, this.h);
    } else {
      drawPtero(this.x, this.y, this.w, this.h, this.wingPhase);
    }
  }

  hitbox() {
    if (this.kind === 'ptero') {
      return { x: this.x - this.w * 0.35, y: this.y - this.h * 0.9,
               w: this.w * 0.7, h: this.h * 0.9 };
    }
    return { x: this.x - this.w * 0.45, y: this.y - this.h,
             w: this.w * 0.9, h: this.h };
  }
}

function drawCactus(cx, cy, w, h, count) {
  ctx.fillStyle = '#2d7a2d';
  for (let i = 0; i < count; i++) {
    const ox = (i - (count - 1) / 2) * w * 0.9;
    const hh = h * (i % 2 === 0 ? 1 : 0.72);
    // main stem
    roundRect(ctx, cx + ox - w * 0.22, cy - hh, w * 0.44, hh, w * 0.18);
    ctx.fill();
    // arms
    if (count > 1 || Math.random() > 0.4) {
      roundRect(ctx, cx + ox - w * 0.55, cy - hh * 0.55, w * 0.33, w * 0.22, w * 0.1);
      ctx.fill();
      roundRect(ctx, cx + ox - w * 0.55, cy - hh * 0.55, w * 0.22, hh * 0.28, w * 0.1);
      ctx.fill();
    }
  }
}

function drawRock(cx, cy, w, h) {
  ctx.fillStyle = '#888';
  ctx.beginPath();
  ctx.ellipse(cx, cy - h * 0.45, w * 0.5, h * 0.55, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#aaa';
  ctx.beginPath();
  ctx.ellipse(cx - w * 0.1, cy - h * 0.65, w * 0.22, h * 0.2, -0.3, 0, Math.PI * 2);
  ctx.fill();
}

function drawPtero(cx, cy, w, h, phase) {
  const flap = Math.sin(phase) * 0.5;
  ctx.fillStyle = '#7B4F9E';
  // body
  ctx.beginPath();
  ctx.ellipse(cx, cy, w * 0.18, h * 0.25, 0, 0, Math.PI * 2);
  ctx.fill();
  // wings
  ctx.beginPath();
  ctx.moveTo(cx, cy - h * 0.1);
  ctx.quadraticCurveTo(cx - w * 0.45, cy + flap * h, cx - w * 0.5, cy + flap * h * 0.5);
  ctx.quadraticCurveTo(cx - w * 0.2, cy, cx, cy);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(cx, cy - h * 0.1);
  ctx.quadraticCurveTo(cx + w * 0.45, cy + flap * h, cx + w * 0.5, cy + flap * h * 0.5);
  ctx.quadraticCurveTo(cx + w * 0.2, cy, cx, cy);
  ctx.fill();
  // head
  ctx.fillStyle = '#9B5FBE';
  ctx.beginPath();
  ctx.ellipse(cx + w * 0.2, cy - h * 0.2, w * 0.12, h * 0.18, 0.5, 0, Math.PI * 2);
  ctx.fill();
  // beak
  ctx.strokeStyle = '#f0c000';
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(cx + w * 0.28, cy - h * 0.22);
  ctx.lineTo(cx + w * 0.46, cy - h * 0.3);
  ctx.stroke();
}

// ---------- Cloud ----------
class Cloud {
  constructor() {
    this.x = W + 100;
    this.y = rand(H * 0.06, H * 0.35);
    this.r = rand(30, 65);
    this.speed = rand(40, 80);
  }
  update(dt) { this.x -= this.speed * dt; }
  draw() {
    ctx.globalAlpha = 0.75;
    ctx.fillStyle = '#fff';
    for (const [ox, oy, r] of [
      [0, 0, this.r], [-this.r * 0.6, this.r * 0.2, this.r * 0.65],
      [this.r * 0.6, this.r * 0.15, this.r * 0.7], [this.r * 0.05, this.r * 0.3, this.r * 0.5]
    ]) {
      ctx.beginPath();
      ctx.arc(this.x + ox, this.y + oy, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
}

// ---------- Coin ----------
class Coin {
  constructor() {
    this.x = W + 30;
    this.y = groundY - rand(40, 180);
    this.r = 14;
    this.phase = 0;
    this.collected = false;
  }
  update(dt) {
    this.x -= speed * dt;
    this.phase += dt * 4;
  }
  draw() {
    if (this.collected) return;
    const sc = 0.55 + Math.abs(Math.sin(this.phase)) * 0.45;
    ctx.save();
    ctx.translate(this.x, this.y);
    ctx.scale(sc, 1);
    ctx.fillStyle = '#FFD700';
    ctx.beginPath();
    ctx.arc(0, 0, this.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#FFA000';
    ctx.font = `bold ${this.r}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('$', 0, 1);
    ctx.restore();
  }
  hitbox() {
    return { x: this.x - this.r, y: this.y - this.r, w: this.r * 2, h: this.r * 2 };
  }
}

// ---------- Particle ----------
class Particle {
  constructor(x, y, color) {
    this.x  = x;
    this.y  = y;
    this.vx = rand(-200, 200);
    this.vy = rand(-300, -50);
    this.r  = rand(4, 9);
    this.life = 1;
    this.color = color;
    this.angle = rand(0, Math.PI * 2);
    this.rot   = rand(-8, 8);
  }
  update(dt) {
    this.x    += this.vx * dt;
    this.y    += (this.vy += GRAVITY * 0.6 * dt) * dt;
    this.life -= dt * 2.2;
    this.angle+= this.rot * dt;
  }
  draw() {
    ctx.save();
    ctx.globalAlpha = Math.max(0, this.life);
    ctx.translate(this.x, this.y);
    ctx.rotate(this.angle);
    ctx.fillStyle = this.color;
    ctx.fillRect(-this.r / 2, -this.r / 2, this.r, this.r);
    ctx.restore();
  }
}

function spawnBurst(x, y, color, n) {
  for (let i = 0; i < n; i++) particles.push(new Particle(x, y, color));
}

// ---------- collision ----------
function rectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x &&
         a.y < b.y + b.h && a.y + a.h > b.y;
}

function dinoHitbox(d) {
  const r = d.r * 0.7;
  return { x: d.x - r, y: d.y - d.r * 1.8, w: r * 2, h: d.r * 1.8 };
}

// ---------- game init ----------
function initGame() {
  score     = 0;
  elapsed   = 0;
  speed     = 280;
  obstacles = [];
  coins     = [];
  particles = [];
  clouds    = [new Cloud(), new Cloud(), new Cloud()];
  spawnTimer = 0;
  cloudTimer = 0;
  coinTimer  = 0;

  const count = 1 + Math.floor(score / 500);
  dinos = [];
  const startX = W * 0.18;
  dinos.push(new Dino(startX, DINO_COLORS[0]));

  updateUI();
}

function updateUI() {
  scoreEl.textContent = score;
  bestEl.textContent  = best;
  dinosEl.textContent = dinos.length;
}

// ---------- spawn extra dino (every 300 pts) ----------
function maybeAddDino() {
  const desired = 1 + Math.min(5, Math.floor(score / 300));
  while (dinos.length < desired) {
    const i   = dinos.length;
    const col = DINO_COLORS[i % DINO_COLORS.length];
    const d   = new Dino(W * 0.18 - i * 55, col, i * 1.4);
    dinos.push(d);
    spawnBurst(d.x, groundY, col, 14);
    updateUI();
  }
}

// ---------- input ----------
function handleClick() {
  if (state === 'idle' || state === 'dead') return;
  const now = Date.now();
  const isDouble = (now - lastClickTime) < 280;
  lastClickTime = now;
  dinos.forEach(d => d.jump(isDouble));
}

canvas.addEventListener('click',      handleClick);
canvas.addEventListener('touchstart', e => { e.preventDefault(); handleClick(); }, { passive: false });

document.addEventListener('keydown', e => {
  if (e.code === 'Space' || e.code === 'ArrowUp') {
    e.preventDefault();
    if (state === 'playing') dinos.forEach(d => d.jump(false));
  }
  if (e.code === 'KeyZ' || e.code === 'ArrowDown') {
    e.preventDefault();
    if (state === 'playing') dinos.forEach(d => d.jump(true));
  }
});

startBtn.addEventListener('click', e => {
  e.stopPropagation();
  overlay.style.display = 'none';
  ui.style.display      = 'flex';
  state = 'playing';
  lastTime = performance.now();
  initGame();
  requestAnimationFrame(loop);
});

// ---------- death ----------
function die() {
  state = 'dead';
  dinos.forEach(d => spawnBurst(d.x, d.y, d.color, 20));
  if (score > best) {
    best = score;
    localStorage.setItem('dinoBest', best);
  }
  ui.style.display = 'none';
  finalEl.textContent = `Очки: ${score}  |  Рекорд: ${best}`;
  finalEl.style.display = 'block';
  startBtn.textContent  = 'Снова!';
  overlay.style.display = 'flex';
}

// ---------- draw background ----------
function drawBackground() {
  // sky gradient
  const sky = ctx.createLinearGradient(0, 0, 0, groundY);
  sky.addColorStop(0,   '#5BA3CC');
  sky.addColorStop(1,   '#A8D8EA');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, W, groundY);

  // ground
  ctx.fillStyle = '#5D8A3C';
  ctx.fillRect(0, groundY, W, H - groundY);

  // ground line
  ctx.strokeStyle = '#3A6626';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, groundY);
  ctx.lineTo(W, groundY);
  ctx.stroke();

  // grass tufts
  ctx.fillStyle = '#7CB842';
  for (let gx = ((elapsed * 120) % 80); gx < W; gx += 80) {
    for (let s of [-1, 1]) {
      ctx.beginPath();
      ctx.moveTo(gx, groundY);
      ctx.quadraticCurveTo(gx + s * 6, groundY - 10, gx + s * 12, groundY);
      ctx.fill();
    }
  }
}

// ---------- main loop ----------
function loop(ts) {
  if (state !== 'playing') return;

  const dt = Math.min((ts - lastTime) / 1000, 0.05);
  lastTime = ts;
  elapsed += dt;

  // increase speed
  speed = 280 + elapsed * 18;
  score = Math.floor(elapsed * 12 + coins.filter(c => c.collected).length * 20);

  if (score > best) best = score;
  maybeAddDino();
  updateUI();

  // spawn obstacles
  spawnTimer -= dt;
  if (spawnTimer <= 0) {
    obstacles.push(new Obstacle());
    spawnTimer = rand(1.1, 2.6) * (280 / speed);
  }

  // spawn clouds
  cloudTimer -= dt;
  if (cloudTimer <= 0) {
    clouds.push(new Cloud());
    cloudTimer = rand(3, 7);
  }

  // spawn coins
  coinTimer -= dt;
  if (coinTimer <= 0) {
    coins.push(new Coin());
    coinTimer = rand(2, 5);
  }

  // update
  dinos.forEach(d => d.update(dt));
  obstacles.forEach(o => o.update(dt));
  clouds.forEach(c => c.update(dt));
  coins.forEach(c => c.update(dt));
  particles.forEach(p => p.update(dt));

  // cleanup
  obstacles = obstacles.filter(o => o.x > -200);
  clouds     = clouds.filter(c => c.x > -200);
  coins      = coins.filter(c => c.x > -60 && !c.collected);
  particles  = particles.filter(p => p.life > 0);

  // collision: obstacle → die
  let dead = false;
  for (const d of dinos) {
    const dh = dinoHitbox(d);
    for (const o of obstacles) {
      if (rectsOverlap(dh, o.hitbox())) { dead = true; break; }
    }
    if (dead) break;
  }
  if (dead) { die(); return; }

  // collision: coins
  for (const d of dinos) {
    const dh = dinoHitbox(d);
    for (const c of coins) {
      if (!c.collected && rectsOverlap(dh, c.hitbox())) {
        c.collected = true;
        spawnBurst(c.x, c.y, '#FFD700', 10);
      }
    }
  }

  // ---------- draw ----------
  ctx.clearRect(0, 0, W, H);
  drawBackground();
  clouds.forEach(c => c.draw());
  coins.forEach(c => c.draw());
  obstacles.forEach(o => o.draw());
  dinos.forEach(d => d.draw());
  particles.forEach(p => p.draw());

  // speed indicator (subtle)
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.fillRect(W - 120, H - 18, (speed / 600) * 100, 6);

  requestAnimationFrame(loop);
}
