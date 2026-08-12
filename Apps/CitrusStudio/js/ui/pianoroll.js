"use strict";

/* ============================================================
   Citrus Studio — Piano Roll
   Canvas-редактор нот: рисование, перетаскивание, длина,
   velocity-лейн, призраки нот других каналов.
   ============================================================ */

(function (CS) {

  const { $, el, fitCanvas, clamp, noteName, isBlackKey, confirm } = CS.util;
  const { Project, Engine } = CS;

  const LEFT = 58;        // ширина клавиатуры
  const RULER = 22;       // линейка тактов
  const VEL_H = 58;       // высота velocity-лейна
  const MIN_KEY = 12;
  const MAX_KEY = 108;

  const PianoRoll = {

    zoomX: 26,            // px на шаг
    keyH: 13,
    scrollX: 0,           // в шагах
    scrollY: 0,           // px
    snap: 1,
    channelId: null,
    selection: new Set(),
    lastDur: 1,
    _drag: null,

    init() {
      this.canvas = $("#pr-canvas");
      this.host = this.canvas.parentNode;

      this.channelSel = $("#pr-channel");
      this.channelSel.addEventListener("change", () => {
        this.channelId = this.channelSel.value;
        CS.selectChannel(this.channelId, true);
        this.draw();
      });

      $("#pr-snap").addEventListener("change", (e) => { this.snap = parseFloat(e.target.value); });
      $("#pr-zoom-in").addEventListener("click", () => { this.zoomX = clamp(this.zoomX * 1.3, 6, 160); this.draw(); });
      $("#pr-zoom-out").addEventListener("click", () => { this.zoomX = clamp(this.zoomX / 1.3, 6, 160); this.draw(); });
      $("#pr-quantize").addEventListener("click", () => this.quantize());
      $("#pr-clear").addEventListener("click", () => {
        confirm("Очистить", "Удалить все ноты этого канала в текущем паттерне?", () => {
          const pat = Project.currentPattern();
          if (!pat || !this.channelId) return;
          Project.snapshot();
          pat.notes[this.channelId] = [];
          this.selection.clear();
          CS.bus.emit("notes:changed", this.channelId);
          this.draw();
        });
      });

      this.bindMouse();

      CS.bus.on("project:loaded", () => { this.channelId = null; this.syncChannels(); this.scrollToNotes(); this.draw(); });
      CS.bus.on("channels:changed", () => { this.syncChannels(); this.draw(); });
      CS.bus.on("pattern:changed", () => { this.selection.clear(); this.draw(); });
      CS.bus.on("channel:selected", (id) => {
        this.channelId = id;
        if (this.channelSel.value !== id) this.channelSel.value = id;
        this.selection.clear();
        this.draw();
      });
      CS.bus.on("notes:edited", () => this.draw());

      window.addEventListener("resize", () => this.draw());
      this.syncChannels();
    },

    /* ---------------- Данные ---------------- */

    syncChannels() {
      const sel = this.channelSel;
      const prev = this.channelId;
      sel.innerHTML = "";
      for (const ch of Project.state.channels) {
        sel.appendChild(el("option", { value: ch.id, text: ch.name }));
      }
      const exists = Project.state.channels.some((c) => c.id === prev);
      this.channelId = exists ? prev : (Project.state.channels[0] ? Project.state.channels[0].id : null);
      if (this.channelId) sel.value = this.channelId;
    },

    channel() { return Project.channel(this.channelId); },

    notes() {
      const pat = Project.currentPattern();
      if (!pat || !this.channelId) return [];
      return Project.notes(pat.id, this.channelId);
    },

    scrollToNotes() {
      const notes = this.notes();
      if (!notes.length) {
        const ch = this.channel();
        const center = ch ? ch.key : 60;
        this.scrollY = clamp((MAX_KEY - center - 8) * this.keyH, 0, this.gridHeight());
        return;
      }
      let min = 127, max = 0;
      for (const n of notes) { min = Math.min(min, n.key); max = Math.max(max, n.key); }
      const center = (min + max) / 2;
      this.scrollY = clamp((MAX_KEY - center - 8) * this.keyH, 0, this.gridHeight());
    },

    gridHeight() { return (MAX_KEY - MIN_KEY + 1) * this.keyH; },

    /* ---------------- Координаты ---------------- */

    xOfStep(s) { return LEFT + (s - this.scrollX) * this.zoomX; },
    stepOfX(x) { return (x - LEFT) / this.zoomX + this.scrollX; },
    yOfKey(k) { return RULER + (MAX_KEY - k) * this.keyH - this.scrollY; },
    keyOfY(y) { return MAX_KEY - Math.floor((y + this.scrollY - RULER) / this.keyH); },

    snapStep(s) {
      if (!this.snap) return Math.max(0, s);
      return Math.max(0, Math.round(s / this.snap) * this.snap);
    },

    /* ---------------- Мышь ---------------- */

    bindMouse() {
      const c = this.canvas;

      c.addEventListener("contextmenu", (e) => e.preventDefault());

      c.addEventListener("wheel", (e) => {
        if (e.ctrlKey) {
          const before = this.stepOfX(e.offsetX);
          this.zoomX = clamp(this.zoomX * (e.deltaY < 0 ? 1.15 : 1 / 1.15), 6, 160);
          this.scrollX = clamp(this.scrollX + (before - this.stepOfX(e.offsetX)), 0, 4096);
        } else if (e.shiftKey) {
          this.scrollX = clamp(this.scrollX + (e.deltaY > 0 ? 2 : -2), 0, 4096);
        } else {
          const rect = c.getBoundingClientRect();
          const maxScroll = Math.max(0, this.gridHeight() - (rect.height - RULER - VEL_H));
          this.scrollY = clamp(this.scrollY + (e.deltaY > 0 ? 40 : -40), 0, maxScroll);
        }
        this.draw();
        e.preventDefault();
      }, { passive: false });

      c.addEventListener("mousedown", (e) => {
        const rect = c.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const ch = this.channel();
        if (!ch) return;

        // линейка — перемотка
        if (y < RULER) {
          const step = Math.max(0, this.stepOfX(x));
          Engine.seek(step);
          this.draw();
          return;
        }

        // клавиатура — проиграть ноту
        if (x < LEFT && y < rect.height - VEL_H) {
          const key = this.keyOfY(y);
          if (key >= MIN_KEY && key <= MAX_KEY) Engine.preview(ch, key, 0.5);
          return;
        }

        // velocity-лейн
        if (y > rect.height - VEL_H) {
          this.dragVelocity(e, rect);
          return;
        }

        const step = this.stepOfX(x);
        const key = this.keyOfY(y);
        const hit = this.noteAt(step, key);

        if (e.button === 2) {                       // ПКМ — стирание кистью
          this.dragErase(e, rect);
          return;
        }

        if (hit) {
          const nx = this.xOfStep(hit.t + hit.dur);
          if (Math.abs(x - nx) < 8) this.dragResize(e, rect, hit);
          else this.dragMove(e, rect, hit);
        } else {
          Project.snapshot();
          const note = {
            t: this.snapStep(step - (this.snap ? 0 : 0)),
            dur: this.lastDur,
            key: clamp(key, MIN_KEY, MAX_KEY),
            vel: 0.85
          };
          this.notes().push(note);
          this.selection.clear();
          this.selection.add(note);
          Engine.preview(ch, note.key, 0.4);
          CS.bus.emit("notes:changed", this.channelId);
          this.dragMove(e, rect, note, true);
        }
      });
    },

    noteAt(step, key) {
      const notes = this.notes();
      for (let i = notes.length - 1; i >= 0; i--) {
        const n = notes[i];
        if (n.key === key && step >= n.t && step <= n.t + n.dur) return n;
      }
      return null;
    },

    dragMove(e, rect, note, isNew) {
      if (!isNew) Project.snapshot();
      const startX = e.clientX;
      const startY = e.clientY;
      const origT = note.t;
      const origKey = note.key;
      let moved = false;

      const move = (ev) => {
        const dSteps = (ev.clientX - startX) / this.zoomX;
        const dKeys = Math.round((ev.clientY - startY) / this.keyH);
        const nt = this.snapStep(origT + dSteps);
        const nk = clamp(origKey - dKeys, MIN_KEY, MAX_KEY);
        if (nt !== note.t || nk !== note.key) {
          moved = true;
          if (nk !== note.key) Engine.preview(this.channel(), nk, 0.25);
          note.t = nt;
          note.key = nk;
          this.draw();
        }
      };
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
        if (moved || isNew) CS.bus.emit("notes:changed", this.channelId);
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
      this.draw();
    },

    dragResize(e, rect, note) {
      Project.snapshot();
      const startX = e.clientX;
      const origDur = note.dur;
      const move = (ev) => {
        const d = (ev.clientX - startX) / this.zoomX;
        let nd = origDur + d;
        if (this.snap) nd = Math.round(nd / this.snap) * this.snap;
        note.dur = Math.max(this.snap || 0.25, nd);
        this.lastDur = note.dur;
        this.draw();
      };
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
        CS.bus.emit("notes:changed", this.channelId);
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    },

    dragErase(e, rect) {
      Project.snapshot();
      const erase = (ev) => {
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        const hit = this.noteAt(this.stepOfX(x), this.keyOfY(y));
        if (hit) {
          const notes = this.notes();
          const i = notes.indexOf(hit);
          if (i >= 0) notes.splice(i, 1);
          this.selection.delete(hit);
          this.draw();
        }
      };
      erase(e);
      const up = () => {
        window.removeEventListener("mousemove", erase);
        window.removeEventListener("mouseup", up);
        CS.bus.emit("notes:changed", this.channelId);
      };
      window.addEventListener("mousemove", erase);
      window.addEventListener("mouseup", up);
    },

    dragVelocity(e, rect) {
      Project.snapshot();
      const laneTop = rect.height - VEL_H + 12;
      const laneH = VEL_H - 20;

      const apply = (ev) => {
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        const step = this.stepOfX(x);
        // ближайшая нота по горизонтали
        let best = null, bestD = 0.6;
        for (const n of this.notes()) {
          const d = Math.abs(n.t - step);
          if (d < bestD) { bestD = d; best = n; }
        }
        if (best) {
          best.vel = clamp(1 - (y - laneTop) / laneH, 0.05, 1);
          this.draw();
        }
      };
      apply(e);
      const up = () => {
        window.removeEventListener("mousemove", apply);
        window.removeEventListener("mouseup", up);
        CS.bus.emit("notes:changed", this.channelId);
      };
      window.addEventListener("mousemove", apply);
      window.addEventListener("mouseup", up);
    },

    quantize() {
      const notes = this.notes();
      if (!notes.length) return;
      Project.snapshot();
      const snap = this.snap || 1;
      for (const n of notes) n.t = Math.round(n.t / snap) * snap;
      CS.bus.emit("notes:changed", this.channelId);
      this.draw();
    },

    deleteSelection() {
      if (!this.selection.size) return;
      Project.snapshot();
      const notes = this.notes();
      for (const n of this.selection) {
        const i = notes.indexOf(n);
        if (i >= 0) notes.splice(i, 1);
      }
      this.selection.clear();
      CS.bus.emit("notes:changed", this.channelId);
      this.draw();
    },

    /* ---------------- Отрисовка ---------------- */

    draw() {
      if (!this.canvas || !this.canvas.offsetParent) return;
      const { ctx, w, h } = fitCanvas(this.canvas);
      const pat = Project.currentPattern();
      const ch = this.channel();

      ctx.fillStyle = "#191c21";
      ctx.fillRect(0, 0, w, h);

      if (!pat || !ch) {
        ctx.fillStyle = "#6b7684";
        ctx.font = "13px Inter, system-ui, sans-serif";
        ctx.fillText("Нет каналов — добавь инструмент в Channel Rack", 20, 40);
        return;
      }

      const gridBottom = h - VEL_H;
      const firstKey = clamp(this.keyOfY(gridBottom), MIN_KEY, MAX_KEY);
      const lastKey = clamp(this.keyOfY(RULER) + 1, MIN_KEY, MAX_KEY);

      /* --- горизонтальные полосы клавиш --- */
      for (let k = firstKey; k <= lastKey; k++) {
        const y = this.yOfKey(k);
        if (y + this.keyH < RULER || y > gridBottom) continue;
        ctx.fillStyle = isBlackKey(k) ? "#1d2127" : "#232830";
        ctx.fillRect(LEFT, Math.max(y, RULER), w - LEFT, Math.min(this.keyH, gridBottom - y));
        if (k % 12 === 0) {
          ctx.fillStyle = "#2e353f";
          ctx.fillRect(LEFT, Math.max(y, RULER), w - LEFT, 1);
        }
      }

      /* --- вертикальная сетка --- */
      const stepsVisible = (w - LEFT) / this.zoomX;
      const startStep = Math.floor(this.scrollX);
      for (let s = startStep; s <= startStep + stepsVisible + 1; s++) {
        const x = this.xOfStep(s);
        if (x < LEFT) continue;
        const isBar = s % 16 === 0;
        const isBeat = s % 4 === 0;
        ctx.fillStyle = isBar ? "#3c4552" : isBeat ? "#2c333d" : "#242a32";
        ctx.fillRect(x, RULER, isBar ? 1.5 : 1, gridBottom - RULER);
      }

      /* --- граница длины паттерна --- */
      const endX = this.xOfStep(pat.length);
      if (endX > LEFT && endX < w) {
        ctx.fillStyle = "rgba(0,0,0,0.35)";
        ctx.fillRect(endX, RULER, w - endX, gridBottom - RULER);
        ctx.fillStyle = "#f0a03c";
        ctx.fillRect(endX, RULER, 1.5, gridBottom - RULER);
      }

      /* --- призраки нот других каналов --- */
      for (const other of Project.state.channels) {
        if (other.id === this.channelId) continue;
        const arr = pat.notes[other.id];
        if (!arr) continue;
        ctx.fillStyle = "rgba(255,255,255,0.07)";
        for (const n of arr) {
          const x = this.xOfStep(n.t);
          const y = this.yOfKey(n.key);
          if (y < RULER - this.keyH || y > gridBottom) continue;
          ctx.fillRect(x, y + 1, Math.max(3, n.dur * this.zoomX - 2), this.keyH - 2);
        }
      }

      /* --- ноты канала --- */
      const notes = this.notes();
      for (const n of notes) {
        const x = this.xOfStep(n.t);
        const y = this.yOfKey(n.key);
        const wid = Math.max(4, n.dur * this.zoomX - 2);
        if (x > w || x + wid < LEFT || y < RULER - this.keyH || y > gridBottom) continue;

        const alpha = 0.45 + n.vel * 0.55;
        ctx.fillStyle = hexAlpha(ch.color, alpha);
        roundRect(ctx, x, y + 1, wid, this.keyH - 2, 3);
        ctx.fill();

        if (this.selection.has(n)) {
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1.5;
          roundRect(ctx, x, y + 1, wid, this.keyH - 2, 3);
          ctx.stroke();
        }
        // маркер длины
        ctx.fillStyle = "rgba(0,0,0,0.35)";
        ctx.fillRect(x + wid - 2, y + 2, 2, this.keyH - 4);
      }

      /* --- клавиатура слева --- */
      ctx.fillStyle = "#15181c";
      ctx.fillRect(0, RULER, LEFT, gridBottom - RULER);
      for (let k = firstKey; k <= lastKey; k++) {
        const y = this.yOfKey(k);
        if (y + this.keyH < RULER || y > gridBottom) continue;
        const black = isBlackKey(k);
        const kh = Math.min(this.keyH, gridBottom - y) - 1;
        ctx.fillStyle = black ? "#313946" : "#d7dde5";
        ctx.fillRect(0, Math.max(y, RULER), black ? LEFT - 24 : LEFT - 6, kh);
        if (black) {
          // «белая» подложка справа от чёрной клавиши
          ctx.fillStyle = "#b9c2cd";
          ctx.fillRect(LEFT - 24, Math.max(y, RULER), 18, kh);
        }
        if (k % 12 === 0) {
          ctx.fillStyle = "#4a5461";
          ctx.font = "9px Inter, system-ui, sans-serif";
          ctx.fillText(noteName(k), 4, y + this.keyH - 3);
        }
        if (ch.key === k) {
          ctx.fillStyle = hexAlpha(ch.color, 0.9);
          ctx.fillRect(LEFT - 6, Math.max(y, RULER), 4, Math.min(this.keyH, gridBottom - y) - 1);
        }
      }

      /* --- линейка --- */
      ctx.fillStyle = "#20242a";
      ctx.fillRect(0, 0, w, RULER);
      ctx.fillStyle = "#8894a4";
      ctx.font = "10px Inter, system-ui, sans-serif";
      for (let s = startStep - (startStep % 4); s <= startStep + stepsVisible + 4; s += 4) {
        const x = this.xOfStep(s);
        if (x < LEFT) continue;
        const isBar = s % 16 === 0;
        ctx.fillStyle = isBar ? "#4b5666" : "#333b45";
        ctx.fillRect(x, isBar ? 4 : 12, 1, RULER - (isBar ? 4 : 12));
        if (isBar) {
          ctx.fillStyle = "#98a5b6";
          ctx.fillText(String(s / 16 + 1), x + 3, 12);
        }
      }

      /* --- velocity-лейн --- */
      ctx.fillStyle = "#15181c";
      ctx.fillRect(0, gridBottom, w, VEL_H);
      ctx.fillStyle = "#2a3038";
      ctx.fillRect(LEFT, gridBottom, w - LEFT, 1);
      ctx.fillStyle = "#6b7684";
      ctx.font = "9px Inter, system-ui, sans-serif";
      ctx.fillText("VEL", 6, gridBottom + 14);

      const laneTop = gridBottom + 12;
      const laneH = VEL_H - 20;
      for (const n of notes) {
        const x = this.xOfStep(n.t);
        if (x < LEFT || x > w) continue;
        const barH = n.vel * laneH;
        ctx.fillStyle = hexAlpha(ch.color, 0.85);
        ctx.fillRect(x, laneTop + laneH - barH, 3, barH);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(x - 1, laneTop + laneH - barH - 2, 5, 2);
      }

      /* --- курсор воспроизведения --- */
      if (Engine.playing) {
        let pos = Engine.positionSteps();
        if (Engine.mode === "song") {
          // в режиме песни показываем позицию внутри клипа текущего паттерна
          pos = pos % Math.max(1, pat.length);
        }
        const x = this.xOfStep(pos);
        if (x >= LEFT && x <= w) {
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(x, RULER, 1.5, gridBottom - RULER);
        }
      }
    }
  };

  /* ---------------- Вспомогательное рисование ---------------- */

  function roundRect(ctx, x, y, w, h, r) {
    const rr = Math.min(r, h / 2, w / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }

  function hexAlpha(hex, a) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  CS.PianoRoll = PianoRoll;
  CS.draw = { roundRect, hexAlpha };

})(window.CS);
