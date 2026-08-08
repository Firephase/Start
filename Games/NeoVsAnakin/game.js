"use strict";

/* ============================================================
   Neo vs Anakin — The Matrix Awakens the Force
   Self-contained canvas fighting game. No external assets.
   ============================================================ */

const bgCanvas = document.getElementById("bg-canvas");
const fxCanvas = document.getElementById("fx-canvas");
const bgCtx = bgCanvas.getContext("2d");
const fxCtx = fxCanvas.getContext("2d");

const W = fxCanvas.width;
const H = fxCanvas.height;

const GROUND_Y = 460;
const GRAVITY = 0.62;
const JUMP_V = -13.2;
const ARENA_LEFT = 30;
const ARENA_RIGHT = W - 30;

const ROUND_TIME = 60;
const ROUNDS_TO_WIN = 2;

/* ---------------- Utility ---------------- */

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const rand = (a, b) => a + Math.random() * (b - a);
const chance = (p) => Math.random() < p;

/* ---------------- Background: Matrix rain + Starfield ---------------- */

class Backdrop {
  constructor() {
    this.cols = Math.floor(W / 16);
    this.drops = new Array(this.cols).fill(0).map(() => rand(-30, 0));
    this.chars = "アイウエオカキクケコサシスセソ01木火水土金".split("");
    this.stars = new Array(90).fill(0).map(() => ({
      x: rand(0, W), y: rand(0, H * 0.65), r: rand(0.4, 1.8), tw: rand(0, Math.PI * 2)
    }));
    this.tieTimer = rand(4, 10);
    this.tieX = -80;
    this.tieActive = false;
    this.flashAlpha = 0;
    this.flashColor = "77,255,160";
  }

  triggerFlash(colorRGB) {
    this.flashAlpha = 0.35;
    this.flashColor = colorRGB;
  }

  update(dt) {
    this.tieTimer -= dt;
    if (!this.tieActive && this.tieTimer <= 0) {
      this.tieActive = true;
      this.tieX = -80;
    }
    if (this.tieActive) {
      this.tieX += dt * 220;
      if (this.tieX > W + 80) {
        this.tieActive = false;
        this.tieTimer = rand(8, 16);
      }
    }
    if (this.flashAlpha > 0) this.flashAlpha = Math.max(0, this.flashAlpha - dt * 0.8);
  }

  draw() {
    bgCtx.fillStyle = "#02060a";
    bgCtx.fillRect(0, 0, W, H);

    // starfield (right/upper leaning, Star Wars side)
    for (const s of this.stars) {
      s.tw += 0.03;
      const a = 0.4 + Math.sin(s.tw) * 0.35;
      bgCtx.fillStyle = `rgba(180,210,255,${clamp(a, 0.1, 0.9)})`;
      bgCtx.fillRect(s.x, s.y, s.r, s.r);
    }

    if (this.tieActive) this.drawTie(this.tieX, 70);

    // matrix digital rain (left/lower leaning, Matrix side), blended over whole width at low density
    bgCtx.font = "14px monospace";
    for (let i = 0; i < this.cols; i++) {
      this.drops[i] += 0.35 + (i % 3) * 0.05;
      if (this.drops[i] * 16 > H + 40) {
        this.drops[i] = rand(-20, 0);
      }
      const ch = this.chars[Math.floor(rand(0, this.chars.length))];
      const x = i * 16;
      const y = this.drops[i] * 16;
      const depthFade = 0.12 + (x / W) * 0.06;
      bgCtx.fillStyle = `rgba(60,255,140,${depthFade})`;
      bgCtx.fillText(ch, x, y);
    }

    // arena floor: fused grid (green matrix grid fading into starlit stone)
    const floorGrad = bgCtx.createLinearGradient(0, GROUND_Y, 0, H);
    floorGrad.addColorStop(0, "rgba(20,50,35,0.9)");
    floorGrad.addColorStop(1, "rgba(4,8,10,1)");
    bgCtx.fillStyle = floorGrad;
    bgCtx.fillRect(0, GROUND_Y + 40, W, H - GROUND_Y - 40);

    bgCtx.strokeStyle = "rgba(77,255,160,0.18)";
    bgCtx.lineWidth = 1;
    for (let x = 0; x <= W; x += 40) {
      bgCtx.beginPath();
      bgCtx.moveTo(x, GROUND_Y + 40);
      bgCtx.lineTo(W / 2 + (x - W / 2) * 2.2, H);
      bgCtx.stroke();
    }
    for (let y = GROUND_Y + 40; y <= H; y += 14) {
      bgCtx.beginPath();
      bgCtx.moveTo(0, y);
      bgCtx.lineTo(W, y);
      bgCtx.stroke();
    }

    bgCtx.fillStyle = "rgba(0,0,0,0.55)";
    bgCtx.fillRect(0, GROUND_Y, W, 2);

    if (this.flashAlpha > 0) {
      bgCtx.fillStyle = `rgba(${this.flashColor},${this.flashAlpha})`;
      bgCtx.fillRect(0, 0, W, H);
    }
  }

  drawTie(x, y) {
    bgCtx.save();
    bgCtx.translate(x, y);
    bgCtx.strokeStyle = "rgba(200,210,230,0.8)";
    bgCtx.fillStyle = "rgba(30,30,35,0.9)";
    bgCtx.lineWidth = 2;
    bgCtx.beginPath();
    bgCtx.arc(-22, 0, 16, 0, Math.PI * 2);
    bgCtx.stroke();
    bgCtx.beginPath();
    bgCtx.arc(22, 0, 16, 0, Math.PI * 2);
    bgCtx.stroke();
    bgCtx.beginPath();
    bgCtx.ellipse(0, 0, 9, 9, 0, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.restore();
  }
}

const backdrop = new Backdrop();

/* ---------------- Particles ---------------- */

class Particles {
  constructor() { this.list = []; }

  spawn(p) { this.list.push(p); }

  spark(x, y, colorRGB, count = 10) {
    for (let i = 0; i < count; i++) {
      this.spawn({
        type: "dot", x, y,
        vx: rand(-4, 4), vy: rand(-5, 1),
        life: rand(0.25, 0.5), age: 0,
        color: colorRGB, r: rand(1.5, 3.5)
      });
    }
  }

  lightning(x, y, colorRGB) {
    this.spawn({ type: "bolt", x, y, life: 0.18, age: 0, color: colorRGB });
  }

  ripple(x, y, colorRGB) {
    this.spawn({ type: "ripple", x, y, life: 0.6, age: 0, color: colorRGB, r: 4 });
  }

  update(dt) {
    for (const p of this.list) {
      p.age += dt;
      if (p.type === "dot") {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.25;
      }
      if (p.type === "ripple") p.r += dt * 260;
    }
    this.list = this.list.filter((p) => p.age < p.life);
  }

  draw() {
    for (const p of this.list) {
      const t = 1 - p.age / p.life;
      if (p.type === "dot") {
        fxCtx.fillStyle = `rgba(${p.color},${t})`;
        fxCtx.beginPath();
        fxCtx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        fxCtx.fill();
      } else if (p.type === "bolt") {
        fxCtx.strokeStyle = `rgba(${p.color},${t})`;
        fxCtx.lineWidth = 2;
        fxCtx.beginPath();
        let cx = p.x, cy = p.y;
        fxCtx.moveTo(cx, cy);
        for (let i = 0; i < 4; i++) {
          cx += rand(-14, 14);
          cy += rand(6, 16);
          fxCtx.lineTo(cx, cy);
        }
        fxCtx.stroke();
      } else if (p.type === "ripple") {
        fxCtx.strokeStyle = `rgba(${p.color},${t * 0.8})`;
        fxCtx.lineWidth = 3;
        fxCtx.beginPath();
        fxCtx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        fxCtx.stroke();
      }
    }
  }
}

const particles = new Particles();

/* ---------------- Attack definitions ---------------- */

const MOVES = {
  punch:   { startup: 0.08, active: 0.07, recovery: 0.16, dmg: 6,  range: 58, knock: 3,  meterGain: 7,  meterCost: 0 },
  kick:    { startup: 0.13, active: 0.09, recovery: 0.22, dmg: 10, range: 66, knock: 6,  meterGain: 9,  meterCost: 0 },
  slash:   { startup: 0.10, active: 0.08, recovery: 0.18, dmg: 9,  range: 64, knock: 4,  meterGain: 8,  meterCost: 0 },
  push:    { startup: 0.14, active: 0.10, recovery: 0.28, dmg: 7,  range: 190, knock: 16, meterGain: 8, meterCost: 0 },
  bullet:  { startup: 0.16, active: 0.22, recovery: 0.30, dmg: 22, range: 260, knock: 10, meterGain: 0, meterCost: 100, special: true },
  lightning: { startup: 0.20, active: 0.42, recovery: 0.30, dmg: 26, range: 120, knock: 2, meterGain: 0, meterCost: 100, special: true, multiHit: true },
};

/* ---------------- Fighter ---------------- */

class Fighter {
  constructor(name, x, facing, colors, isAnakin) {
    this.name = name;
    this.isAnakin = isAnakin;
    this.x = x;
    this.vx = 0;
    this.vy = 0;
    this.jumpOffset = 0; // 0 = grounded
    this.facing = facing;
    this.width = 44;
    this.height = 118;
    this.colors = colors;

    this.maxHealth = 100;
    this.health = 100;
    this.maxMeter = 100;
    this.meter = 0;

    this.state = "idle"; // idle, walk, jump, crouch, block, attack, hit, ko
    this.action = null;  // active move key
    this.actionTimer = 0;
    this.actionPhase = null; // startup, active, recovery
    this.hasHit = false;
    this._lightningTick = 0;

    this.hitstun = 0;
    this.blocking = false;
    this.ko = false;

    this.isAI = false;
    this.aiState = { timer: rand(0.4, 1), mode: "approach" };

    this.slowFactor = 1; // used for bullet-time effect on opponent
    this.walkAnimT = 0;
  }

  canAct() {
    return this.state !== "attack" && this.state !== "hit" && this.state !== "ko";
  }

  startAttack(key) {
    if (!this.canAct()) return false;
    const move = MOVES[key];
    if (move.special && this.meter < move.meterCost) return false;
    this.action = key;
    this.actionPhase = "startup";
    this.actionTimer = move.startup;
    this.state = "attack";
    this.hasHit = false;
    this._lightningTick = 0;
    if (move.special) this.meter = 0;
    return true;
  }

  takeHit(dmg, knock, fromRight, special) {
    this.health = clamp(this.health - dmg, 0, this.maxHealth);
    this.hitstun = special ? 0.45 : 0.22;
    this.state = "hit";
    this.vx = fromRight ? -knock : knock;
    this.meter = clamp(this.meter + dmg * 0.6, 0, this.maxMeter);
    if (this.health <= 0) {
      this.ko = true;
      this.state = "ko";
    }
  }

  update(dt, opponent, bounds) {
    dt *= this.slowFactor;
    this.slowFactor = 1;

    // gravity / jump
    if (this.jumpOffset > 0 || this.vy < 0 || this.state === "jump") {
      this.vy += GRAVITY;
      this.jumpOffset -= this.vy;
      if (this.jumpOffset <= 0) {
        this.jumpOffset = 0;
        this.vy = 0;
        if (this.state === "jump") this.state = "idle";
      }
    }

    // horizontal drift from knockback
    this.x += this.vx;
    this.vx *= 0.82;
    this.x = clamp(this.x, bounds.left + this.width / 2, bounds.right - this.width / 2);

    // face opponent (unless mid-attack)
    if (this.state !== "attack") {
      this.facing = opponent.x >= this.x ? 1 : -1;
    }

    if (this.hitstun > 0) {
      this.hitstun -= dt;
      if (this.hitstun <= 0 && this.state === "hit") this.state = "idle";
    }

    if (this.state === "attack") {
      this.updateAttack(dt, opponent);
    }

    this.walkAnimT += dt;
  }

  updateAttack(dt, opponent) {
    const move = MOVES[this.action];
    this.actionTimer -= dt;

    if (this.actionPhase === "startup" && this.actionTimer <= 0) {
      this.actionPhase = "active";
      this.actionTimer = move.active;
      if (this.action === "lightning") particles.lightning(this.x + this.facing * 30, GROUND_Y - 80, this.colors.fx);
    } else if (this.actionPhase === "active") {
      if (this.action === "lightning" && Math.random() < 0.35) {
        particles.lightning(opponent.x, GROUND_Y - rand(40, 90), this.colors.fx);
      }
      if (!this.hasHit || move.multiHit) {
        this.tryLandHit(opponent, move);
      }
      if (this.actionTimer <= 0) {
        this.actionPhase = "recovery";
        this.actionTimer = move.recovery;
      }
    } else if (this.actionPhase === "recovery" && this.actionTimer <= 0) {
      this.state = "idle";
      this.action = null;
    }
  }

  tryLandHit(opponent, move) {
    const dist = Math.abs(opponent.x - this.x);
    const facingRight = this.facing === 1;
    const opponentInFront = facingRight ? opponent.x > this.x : opponent.x < this.x;
    if (dist <= move.range && opponentInFront && !opponent.ko) {
      // multi-hit lightning ticks repeatedly with a small cooldown gate
      if (move.multiHit) {
        if (!this._lightningTick || this._lightningTick <= 0) {
          this._lightningTick = 0.12;
          this.applyDamage(opponent, Math.round(move.dmg / 4), move.knock, move.special);
        } else {
          this._lightningTick -= 1 / 60;
        }
        return;
      }
      this.applyDamage(opponent, move.dmg, move.knock, move.special);
      this.hasHit = true;
    }
  }

  applyDamage(opponent, dmg, knock, special) {
    const wasBlocking = opponent.blocking && ((this.facing === 1 && opponent.facing === -1) || (this.facing === -1 && opponent.facing === 1));
    let finalDmg = dmg;
    let finalKnock = knock;
    if (wasBlocking && !special) {
      finalDmg = Math.max(1, Math.round(dmg * 0.3));
      finalKnock *= 0.4;
      particles.spark(opponent.x - opponent.facing * 20, GROUND_Y - 60, "180,220,255", 6);
    } else {
      particles.spark(opponent.x, GROUND_Y - 70, this.colors.fx, 10);
    }
    const fromRight = this.x > opponent.x;
    opponent.takeHit(finalDmg, finalKnock, fromRight, special);
    this.meter = clamp(this.meter + (MOVES[this.action]?.meterGain || 0), 0, this.maxMeter);
  }

  draw() {
    const bx = this.x;
    const by = GROUND_Y - this.jumpOffset;
    const bodyH = this.state === "block" ? this.height * 0.9 : this.height;
    const legBend = this.state === "block" ? 10 : 0;

    fxCtx.save();
    fxCtx.translate(bx, by);
    fxCtx.scale(this.facing, 1);

    // shadow
    fxCtx.fillStyle = "rgba(0,0,0,0.4)";
    fxCtx.beginPath();
    fxCtx.ellipse(0, 4, this.width * 0.55 * (1 - this.jumpOffset / 300), 6, 0, 0, Math.PI * 2);
    fxCtx.fill();

    const flash = this.state === "hit" ? 0.5 + 0.5 * Math.sin(Date.now() / 30) : 0;

    if (this.isAnakin) this.drawAnakin(bodyH, legBend, flash);
    else this.drawNeo(bodyH, legBend, flash);

    fxCtx.restore();
  }

  drawNeo(bodyH, legBend, flash) {
    const c = this.colors;
    fxCtx.fillStyle = flash ? "rgba(255,255,255,0.8)" : c.coat;

    // legs
    fxCtx.fillRect(-14, -bodyH * 0.45, 10, bodyH * 0.45 - legBend);
    fxCtx.fillRect(4, -bodyH * 0.45, 10, bodyH * 0.45 - legBend);

    // coat/torso
    fxCtx.fillStyle = flash ? "rgba(255,255,255,0.8)" : c.coat;
    fxCtx.fillRect(-16, -bodyH * 0.95, 32, bodyH * 0.55);

    // shirt accent
    fxCtx.fillStyle = c.accent;
    fxCtx.fillRect(-6, -bodyH * 0.9, 12, bodyH * 0.5);

    // head
    fxCtx.fillStyle = "#1a1410";
    fxCtx.beginPath();
    fxCtx.arc(0, -bodyH - 6, 10, 0, Math.PI * 2);
    fxCtx.fill();

    // sunglasses
    fxCtx.fillStyle = "#000";
    fxCtx.fillRect(-8, -bodyH - 8, 16, 4);

    // arms
    fxCtx.strokeStyle = flash ? "#fff" : c.coat;
    fxCtx.lineWidth = 7;
    fxCtx.lineCap = "round";
    const armSwing = this.state === "walk" ? Math.sin(this.walkAnimT * 8) * 10 : 0;

    let armX = 20, armY = -bodyH * 0.6;
    if (this.state === "attack" && this.actionPhase !== "recovery") {
      const reach = this.action === "kick" ? 34 : 28;
      armX = reach;
      armY = -bodyH * 0.55;
      // leg kick pose
      if (this.action === "kick") {
        fxCtx.fillStyle = c.coat;
        fxCtx.save();
        fxCtx.translate(6, -bodyH * 0.45);
        fxCtx.rotate(-0.9);
        fxCtx.fillRect(0, -5, 34, 10);
        fxCtx.restore();
      }
    }
    if (this.action === "bullet") {
      // dash afterimage streaks
      fxCtx.strokeStyle = "rgba(120,255,190,0.6)";
      for (let i = 1; i <= 3; i++) {
        fxCtx.beginPath();
        fxCtx.moveTo(-20 - i * 10, -bodyH * 0.7);
        fxCtx.lineTo(-40 - i * 14, -bodyH * 0.7);
        fxCtx.stroke();
      }
    }

    fxCtx.beginPath();
    fxCtx.moveTo(-12, -bodyH * 0.75);
    fxCtx.lineTo(-24 + armSwing, -bodyH * 0.5);
    fxCtx.stroke();
    fxCtx.beginPath();
    fxCtx.moveTo(12, -bodyH * 0.75);
    fxCtx.lineTo(armX - armSwing, armY);
    fxCtx.stroke();
  }

  drawAnakin(bodyH, legBend, flash) {
    const c = this.colors;

    fxCtx.fillStyle = flash ? "rgba(255,255,255,0.8)" : c.robe;
    fxCtx.fillRect(-14, -bodyH * 0.45, 10, bodyH * 0.45 - legBend);
    fxCtx.fillRect(4, -bodyH * 0.45, 10, bodyH * 0.45 - legBend);

    fxCtx.fillStyle = flash ? "rgba(255,255,255,0.8)" : c.robe;
    fxCtx.fillRect(-17, -bodyH * 0.95, 34, bodyH * 0.55);

    fxCtx.fillStyle = c.accent;
    fxCtx.fillRect(-17, -bodyH * 0.95, 34, 8);

    // head + padawan-ish hair silhouette
    fxCtx.fillStyle = "#2a1f18";
    fxCtx.beginPath();
    fxCtx.arc(0, -bodyH - 6, 10, 0, Math.PI * 2);
    fxCtx.fill();
    fxCtx.fillStyle = "#3a2a1c";
    fxCtx.fillRect(-9, -bodyH - 14, 18, 6);

    // mechanical arm hint (right arm) darker
    fxCtx.strokeStyle = flash ? "#fff" : "#555";
    fxCtx.lineWidth = 7;
    fxCtx.lineCap = "round";
    fxCtx.beginPath();
    fxCtx.moveTo(-12, -bodyH * 0.75);
    fxCtx.lineTo(-22, -bodyH * 0.5);
    fxCtx.stroke();

    // saber arm + blade
    let handX = 18, handY = -bodyH * 0.65;
    if (this.state === "attack" && this.action === "slash" && this.actionPhase !== "recovery") {
      handX = 30; handY = -bodyH * 0.5;
    }
    if (this.state === "attack" && this.action === "push" && this.actionPhase !== "recovery") {
      handX = 34; handY = -bodyH * 0.6;
      // force push shockwave ring
      fxCtx.strokeStyle = "rgba(150,200,255,0.7)";
      fxCtx.lineWidth = 3;
      fxCtx.beginPath();
      fxCtx.arc(handX + 20, handY, 14 + Math.sin(Date.now() / 40) * 4, 0, Math.PI * 2);
      fxCtx.stroke();
    }
    fxCtx.strokeStyle = flash ? "#fff" : c.robe;
    fxCtx.beginPath();
    fxCtx.moveTo(12, -bodyH * 0.75);
    fxCtx.lineTo(handX, handY);
    fxCtx.stroke();

    // lightsaber blade
    const bladeOn = this.action === "slash" || this.action === "lightning" || this.state === "idle" || this.state === "walk" || this.state === "block";
    if (bladeOn) {
      const bladeLen = this.action === "slash" && this.actionPhase === "active" ? 54 : 46;
      const angle = this.action === "slash" && this.actionPhase !== "recovery" ? -0.9 : -1.3;
      fxCtx.save();
      fxCtx.translate(handX, handY);
      fxCtx.rotate(angle);
      const grad = fxCtx.createLinearGradient(0, 0, bladeLen, 0);
      grad.addColorStop(0, c.saber);
      grad.addColorStop(1, "rgba(255,255,255,0.9)");
      fxCtx.shadowColor = c.saber;
      fxCtx.shadowBlur = 14;
      fxCtx.fillStyle = grad;
      fxCtx.fillRect(0, -3, bladeLen, 6);
      fxCtx.shadowBlur = 0;
      fxCtx.restore();
    }

    if (this.action === "lightning") {
      fxCtx.fillStyle = "rgba(150,200,255,0.15)";
      fxCtx.beginPath();
      fxCtx.arc(handX, handY, 60, 0, Math.PI * 2);
      fxCtx.fill();
    }
  }
}

/* ---------------- Game / Match state ---------------- */

const neoColors = { coat: "#101614", accent: "#2f8f5c", fx: "77,255,160" };
const anakinColors = { robe: "#1b1b22", accent: "#3a3a52", saber: "#4dc6ff", fx: "120,190,255" };

let neo = new Fighter("Neo", 260, 1, neoColors, false);
let anakin = new Fighter("Anakin", 700, -1, anakinColors, true);

let mode = "1p"; // "1p" or "2p"
let score = { neo: 0, anakin: 0 };
let roundTimer = ROUND_TIME;
let matchPhase = "menu"; // menu, intro, fighting, roundend, matchend
let bannerTimer = 0;
let lastTs = 0;

const keysHeld = new Set();
const keysPressed = new Set(); // edge-triggered, cleared each frame after processing

window.addEventListener("keydown", (e) => {
  if (!keysHeld.has(e.code)) keysPressed.add(e.code);
  keysHeld.add(e.code);
});
window.addEventListener("keyup", (e) => keysHeld.delete(e.code));

/* ---------------- Input -> actions ---------------- */

function handlePlayerInput(fighter, keymap, opponent) {
  if (!fighter.canAct()) {
    fighter.blocking = false;
    return;
  }

  const left = keysHeld.has(keymap.left);
  const right = keysHeld.has(keymap.right);
  const down = keysHeld.has(keymap.down);
  const jumpKey = keysPressed.has(keymap.up);

  fighter.blocking = down && fighter.jumpOffset === 0;

  if (fighter.blocking) {
    fighter.state = "block";
  } else if (fighter.jumpOffset > 0) {
    fighter.state = "jump";
  } else if (left || right) {
    fighter.state = "walk";
  } else {
    fighter.state = "idle";
  }

  const speed = 4.3;
  if (!fighter.blocking) {
    if (left) fighter.x -= speed;
    if (right) fighter.x += speed;
  }

  if (jumpKey && fighter.jumpOffset === 0) {
    fighter.vy = JUMP_V;
    fighter.jumpOffset = 0.01;
    fighter.state = "jump";
  }

  for (const [code, moveKey] of Object.entries(keymap.attacks)) {
    if (keysPressed.has(code)) {
      fighter.startAttack(moveKey);
    }
  }
}

const neoKeymap = {
  left: "KeyA", right: "KeyD", up: "KeyW", down: "KeyS",
  attacks: { KeyJ: "punch", KeyK: "kick", KeyL: "bullet" }
};
const anakinKeymap = {
  left: "ArrowLeft", right: "ArrowRight", up: "ArrowUp", down: "ArrowDown",
  attacks: { Digit1: "slash", Digit2: "push", Digit3: "lightning" }
};

/* ---------------- Simple AI for Anakin ---------------- */

function updateAI(dt) {
  const ai = anakin;
  if (!ai.canAct()) { ai.blocking = false; return; }

  ai.aiState.timer -= dt;
  const dist = neo.x - ai.x;
  const adist = Math.abs(dist);
  const facing = dist >= 0 ? 1 : -1;

  ai.blocking = false;

  if (ai.aiState.timer <= 0) {
    ai.aiState.timer = rand(0.25, 0.7);
    if (adist > 240) {
      ai.aiState.mode = "approach";
    } else if (adist > 90) {
      ai.aiState.mode = chance(0.5) ? "approach" : "ranged";
    } else {
      const roll = Math.random();
      ai.aiState.mode = roll < 0.45 ? "attack" : roll < 0.7 ? "block" : "retreat";
    }
    if (ai.meter >= 100 && chance(0.5)) ai.aiState.mode = "special";
  }

  const speed = 3.6;
  ai.state = "idle"; // default; branches below override, startAttack() overrides last if it fires

  switch (ai.aiState.mode) {
    case "approach":
      ai.x += facing * speed;
      ai.state = "walk";
      break;
    case "retreat":
      ai.x -= facing * speed;
      ai.state = "walk";
      break;
    case "ranged":
      if (adist < 260 && adist > 70) ai.startAttack("push");
      break;
    case "attack":
      if (adist < 75) ai.startAttack(chance(0.7) ? "slash" : "push");
      else { ai.x += facing * speed; ai.state = "walk"; }
      break;
    case "block":
      ai.blocking = true;
      ai.state = "block";
      break;
    case "special":
      if (adist < 140) {
        ai.startAttack("lightning");
      } else {
        ai.x += facing * speed;
        ai.state = "walk";
      }
      break;
  }

  if (chance(0.002) && ai.jumpOffset === 0 && ai.state !== "attack") {
    ai.vy = JUMP_V; ai.jumpOffset = 0.01; ai.state = "jump";
  }
}

/* ---------------- HUD ---------------- */

const hpNeoEl = document.getElementById("hp-neo");
const hpAnakinEl = document.getElementById("hp-anakin");
const spNeoEl = document.getElementById("sp-neo");
const spAnakinEl = document.getElementById("sp-anakin");
const timerEl = document.getElementById("timer");
const roundBanner = document.getElementById("round-banner");
const pips = document.querySelectorAll(".round-pip");

function updateHud() {
  hpNeoEl.style.width = `${(neo.health / neo.maxHealth) * 100}%`;
  hpAnakinEl.style.width = `${(anakin.health / anakin.maxHealth) * 100}%`;
  spNeoEl.style.width = `${(neo.meter / neo.maxMeter) * 100}%`;
  spAnakinEl.style.width = `${(anakin.meter / anakin.maxMeter) * 100}%`;
  timerEl.textContent = Math.max(0, Math.ceil(roundTimer));

  pips.forEach((p) => {
    const player = p.dataset.p;
    const idx = Number(p.dataset.i);
    const won = player === "neo" ? score.neo > idx : score.anakin > idx;
    p.classList.toggle("filled", won);
  });
}

function showBanner(text, ms) {
  roundBanner.textContent = text;
  roundBanner.classList.add("show");
  bannerTimer = ms;
}

/* ---------------- Round / Match flow ---------------- */

function resetPositions() {
  neo.x = 260; neo.health = 100; neo.meter = 0; neo.vx = 0; neo.vy = 0;
  neo.jumpOffset = 0; neo.state = "idle"; neo.action = null; neo.ko = false; neo.facing = 1;
  anakin.x = 700; anakin.health = 100; anakin.meter = 0; anakin.vx = 0; anakin.vy = 0;
  anakin.jumpOffset = 0; anakin.state = "idle"; anakin.action = null; anakin.ko = false; anakin.facing = -1;
  roundTimer = ROUND_TIME;
}

function startMatch(selectedMode) {
  mode = selectedMode;
  score = { neo: 0, anakin: 0 };
  resetPositions();
  matchPhase = "intro";
  bannerTimer = 1.4;
  showBanner("FIGHT!", 1.4);
  hideAllMenus();
  matchPhase = "fighting";
}

function endRound(winner) {
  matchPhase = "roundend";
  if (winner === "neo") score.neo++;
  else if (winner === "anakin") score.anakin++;
  else { /* draw: no point awarded */ }

  updateHud();

  const matchOver = score.neo >= ROUNDS_TO_WIN || score.anakin >= ROUNDS_TO_WIN;
  const label = winner === "neo" ? "NEO WINS THE ROUND"
    : winner === "anakin" ? "ANAKIN WINS THE ROUND"
    : "DOUBLE KO — DRAW";
  showBanner(label, matchOver ? 1.6 : 2.0);

  setTimeout(() => {
    if (matchOver) {
      matchPhase = "matchend";
      showMatchResult(score.neo > score.anakin ? "neo" : "anakin");
    } else {
      resetPositions();
      matchPhase = "fighting";
      showBanner("FIGHT!", 1.2);
    }
  }, matchOver ? 1600 : 2000);
}

/* ---------------- Menu wiring ---------------- */

const overlay = document.getElementById("overlay");
const menuMain = document.getElementById("menu-main");
const menuHowto = document.getElementById("menu-howto");
const menuResult = document.getElementById("menu-result");

function hideAllMenus() {
  overlay.classList.add("hidden-all");
}
function showMenu(which) {
  overlay.classList.remove("hidden-all");
  [menuMain, menuHowto, menuResult].forEach((m) => m.classList.add("hidden"));
  which.classList.remove("hidden");
}

document.getElementById("btn-1p").addEventListener("click", () => startMatch("1p"));
document.getElementById("btn-2p").addEventListener("click", () => startMatch("2p"));
document.getElementById("btn-howto").addEventListener("click", () => showMenu(menuHowto));
document.getElementById("btn-back").addEventListener("click", () => showMenu(menuMain));
document.getElementById("btn-rematch").addEventListener("click", () => startMatch(mode));
document.getElementById("btn-menu").addEventListener("click", () => {
  matchPhase = "menu";
  showMenu(menuMain);
});

function showMatchResult(winner) {
  const title = document.getElementById("result-title");
  title.textContent = winner === "neo"
    ? "NEO BENDS THE FORCE ITSELF — VICTORY"
    : "ANAKIN CLAIMS THE MATRIX — VICTORY";
  title.style.color = winner === "neo" ? "#4dffa0" : "#ff8a6a";
  showMenu(menuResult);
}

showMenu(menuMain);

/* ---------------- Main loop ---------------- */

const bounds = { left: ARENA_LEFT, right: ARENA_RIGHT };

function gameLoop(ts) {
  const dt = lastTs ? Math.min((ts - lastTs) / 1000, 0.05) : 0;
  lastTs = ts;

  backdrop.update(dt);
  backdrop.draw();

  fxCtx.clearRect(0, 0, W, H);

  if (matchPhase === "fighting") {
    if (mode === "2p") {
      handlePlayerInput(neo, neoKeymap, anakin);
      handlePlayerInput(anakin, anakinKeymap, neo);
    } else {
      handlePlayerInput(neo, neoKeymap, anakin);
      updateAI(dt);
    }

    // Neo's bullet-time special slows Anakin's world-time while active
    if (neo.action === "bullet" && neo.state === "attack") {
      anakin.slowFactor = 0.32;
      if (Math.random() < 0.5) particles.spark(neo.x + rand(-20, 20), GROUND_Y - rand(20, 90), "150,255,200", 2);
    }

    neo.update(dt, anakin, bounds);
    anakin.update(dt, neo, bounds);

    // prevent overlap (simple separation)
    const minDist = 46;
    if (Math.abs(neo.x - anakin.x) < minDist) {
      const push = (minDist - Math.abs(neo.x - anakin.x)) / 2;
      if (neo.x < anakin.x) { neo.x -= push; anakin.x += push; }
      else { neo.x += push; anakin.x -= push; }
    }

    roundTimer -= dt;
    if (neo.ko || anakin.ko) {
      let winner = "draw";
      if (neo.ko && !anakin.ko) winner = "anakin";
      else if (anakin.ko && !neo.ko) winner = "neo";
      endRound(winner);
    } else if (roundTimer <= 0) {
      let winner = "draw";
      if (neo.health > anakin.health) winner = "neo";
      else if (anakin.health > neo.health) winner = "anakin";
      endRound(winner);
    }

    keysPressed.clear();
  } else {
    keysPressed.clear();
  }

  particles.update(dt);

  neo.draw();
  anakin.draw();
  particles.draw();

  if (bannerTimer > 0) {
    bannerTimer -= dt;
    if (bannerTimer <= 0) roundBanner.classList.remove("show");
  }

  updateHud();

  requestAnimationFrame(gameLoop);
}

requestAnimationFrame(gameLoop);
