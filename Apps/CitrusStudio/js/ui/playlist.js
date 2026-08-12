"use strict";

/* ============================================================
   Citrus Studio — Плейлист (аранжировка паттернов)
   ============================================================ */

(function (CS) {

  const { $, el, fitCanvas, clamp, confirm } = CS.util;
  const { Project, Engine, STEPS_PER_BAR } = CS;
  const { roundRect, hexAlpha } = CS.draw;

  const LEFT = 112;
  const RULER = 22;
  const TRACK_H = 46;

  const Playlist = {

    zoomX: 5.5,        // px на шаг
    scrollX: 0,        // в шагах
    scrollY: 0,
    brush: null,       // id паттерна-кисти
    _drag: null,

    init() {
      this.canvas = $("#pl-canvas");
      this.brushSel = $("#pl-brush");

      this.brushSel.addEventListener("change", () => { this.brush = this.brushSel.value; });
      $("#pl-zoom-in").addEventListener("click", () => { this.zoomX = clamp(this.zoomX * 1.3, 1.2, 40); this.draw(); });
      $("#pl-zoom-out").addEventListener("click", () => { this.zoomX = clamp(this.zoomX / 1.3, 1.2, 40); this.draw(); });
      $("#pl-loop").addEventListener("change", (e) => { Engine.loopSong = e.target.checked; });
      $("#pl-add-track").addEventListener("click", () => {
        Project.snapshot();
        Project.state.playlist.tracks.push({ name: "Трек " + (Project.state.playlist.tracks.length + 1) });
        this.draw();
      });
      $("#pl-clear").addEventListener("click", () => {
        confirm("Очистить плейлист", "Удалить все клипы из аранжировки?", () => {
          Project.snapshot();
          Project.state.playlist.clips = [];
          this.draw();
        });
      });

      this.bindMouse();

      CS.bus.on("project:loaded", () => { this.syncPatterns(); this.draw(); });
      CS.bus.on("patterns:changed", () => { this.syncPatterns(); this.draw(); });
      CS.bus.on("playlist:changed", () => this.draw());
      CS.bus.on("notes:changed", () => this.draw());
      CS.bus.on("notes:edited", () => this.draw());
      CS.bus.on("pattern:resized", () => this.draw());
      window.addEventListener("resize", () => this.draw());

      this.syncPatterns();
    },

    syncPatterns() {
      const sel = this.brushSel;
      const prev = this.brush;
      sel.innerHTML = "";
      for (const p of Project.state.patterns) {
        sel.appendChild(el("option", { value: p.id, text: p.name }));
      }
      const exists = Project.state.patterns.some((p) => p.id === prev);
      this.brush = exists ? prev : (Project.state.currentPattern || (Project.state.patterns[0] || {}).id);
      if (this.brush) sel.value = this.brush;
    },

    /* ---------------- Координаты ---------------- */

    xOfStep(s) { return LEFT + (s - this.scrollX) * this.zoomX; },
    stepOfX(x) { return (x - LEFT) / this.zoomX + this.scrollX; },
    yOfTrack(i) { return RULER + i * TRACK_H - this.scrollY; },
    trackOfY(y) { return Math.floor((y + this.scrollY - RULER) / TRACK_H); },

    clipAt(step, track) {
      const clips = Project.state.playlist.clips;
      for (let i = clips.length - 1; i >= 0; i--) {
        const c = clips[i];
        if (c.track === track && step >= c.start && step < c.start + c.length) return c;
      }
      return null;
    },

    /* ---------------- Мышь ---------------- */

    bindMouse() {
      const c = this.canvas;
      c.addEventListener("contextmenu", (e) => e.preventDefault());

      c.addEventListener("wheel", (e) => {
        if (e.ctrlKey) {
          const before = this.stepOfX(e.offsetX);
          this.zoomX = clamp(this.zoomX * (e.deltaY < 0 ? 1.15 : 1 / 1.15), 1.2, 40);
          this.scrollX = clamp(this.scrollX + (before - this.stepOfX(e.offsetX)), 0, 100000);
        } else if (e.shiftKey) {
          const rect = c.getBoundingClientRect();
          const maxY = Math.max(0, Project.state.playlist.tracks.length * TRACK_H - (rect.height - RULER));
          this.scrollY = clamp(this.scrollY + (e.deltaY > 0 ? 30 : -30), 0, maxY);
        } else {
          this.scrollX = clamp(this.scrollX + (e.deltaY > 0 ? 8 : -8), 0, 100000);
        }
        this.draw();
        e.preventDefault();
      }, { passive: false });

      c.addEventListener("mousedown", (e) => {
        const rect = c.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        if (y < RULER) {                       // линейка — перемотка
          Engine.setMode("song");
          Engine.seek(Math.max(0, this.stepOfX(x)));
          this.draw();
          return;
        }

        const track = this.trackOfY(y);
        if (track < 0 || track >= Project.state.playlist.tracks.length) return;

        if (x < LEFT) {                        // заголовок трека — мьют
          const t = Project.state.playlist.tracks[track];
          t.mute = !t.mute;
          this.draw();
          return;
        }

        const step = this.stepOfX(x);
        const hit = this.clipAt(step, track);

        if (e.button === 2) {                  // ПКМ — стирание
          this.dragErase(e, rect);
          return;
        }

        if (hit) this.dragClip(e, rect, hit);
        else this.paintClip(e, rect, track, step);
      });
    },

    paintClip(e, rect, track, step) {
      if (!this.brush) return;
      Project.snapshot();
      const snapped = Math.max(0, Math.round(step / 4) * 4);
      const clip = Project.addClip(this.brush, track, snapped);
      if (clip) this.dragClip(e, rect, clip, true);
    },

    dragClip(e, rect, clip, isNew) {
      if (!isNew) Project.snapshot();
      const startX = e.clientX;
      const startY = e.clientY;
      const origStart = clip.start;
      const origTrack = clip.track;

      const move = (ev) => {
        const dSteps = (ev.clientX - startX) / this.zoomX;
        const dTrack = Math.round((ev.clientY - startY) / TRACK_H);
        clip.start = Math.max(0, Math.round((origStart + dSteps) / 4) * 4);
        clip.track = clamp(origTrack + dTrack, 0, Project.state.playlist.tracks.length - 1);
        this.draw();
      };
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
        CS.bus.emit("playlist:changed");
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
      this.draw();
    },

    dragErase(e, rect) {
      Project.snapshot();
      const erase = (ev) => {
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        const hit = this.clipAt(this.stepOfX(x), this.trackOfY(y));
        if (hit) {
          Project.removeClip(hit.id);
          this.draw();
        }
      };
      erase(e);
      const up = () => {
        window.removeEventListener("mousemove", erase);
        window.removeEventListener("mouseup", up);
      };
      window.addEventListener("mousemove", erase);
      window.addEventListener("mouseup", up);
    },

    /* ---------------- Отрисовка ---------------- */

    draw() {
      if (!this.canvas || !this.canvas.offsetParent) return;
      const { ctx, w, h } = fitCanvas(this.canvas);
      const state = Project.state;

      ctx.fillStyle = "#191c21";
      ctx.fillRect(0, 0, w, h);

      const tracks = state.playlist.tracks;

      /* --- фон треков --- */
      for (let i = 0; i < tracks.length; i++) {
        const y = this.yOfTrack(i);
        if (y > h || y + TRACK_H < RULER) continue;
        ctx.fillStyle = i % 2 ? "#1d2127" : "#20242b";
        ctx.fillRect(LEFT, y, w - LEFT, TRACK_H - 1);
      }

      /* --- сетка тактов --- */
      const stepsVisible = (w - LEFT) / this.zoomX;
      const startBar = Math.floor(this.scrollX / STEPS_PER_BAR);
      const endBar = Math.ceil((this.scrollX + stepsVisible) / STEPS_PER_BAR) + 1;
      for (let bar = startBar; bar <= endBar; bar++) {
        const x = this.xOfStep(bar * STEPS_PER_BAR);
        if (x < LEFT) continue;
        ctx.fillStyle = bar % 4 === 0 ? "#3a4350" : "#282e37";
        ctx.fillRect(x, RULER, bar % 4 === 0 ? 1.5 : 1, h - RULER);
      }

      /* --- клипы --- */
      for (const clip of state.playlist.clips) {
        const pat = Project.pattern(clip.pattern);
        if (!pat) continue;
        const x = this.xOfStep(clip.start);
        const cw = clip.length * this.zoomX;
        const y = this.yOfTrack(clip.track);
        if (x > w || x + cw < LEFT || y > h || y + TRACK_H < RULER) continue;

        const muted = tracks[clip.track] && tracks[clip.track].mute;
        ctx.save();
        ctx.beginPath();
        ctx.rect(LEFT, RULER, w - LEFT, h - RULER);
        ctx.clip();

        ctx.fillStyle = hexAlpha(pat.color, muted ? 0.25 : 0.85);
        roundRect(ctx, x + 1, y + 2, Math.max(4, cw - 2), TRACK_H - 6, 4);
        ctx.fill();

        // мини-превью нот паттерна
        const notes = [];
        for (const chId in pat.notes) for (const n of pat.notes[chId]) notes.push(n);
        if (notes.length) {
          let min = 127, max = 0;
          for (const n of notes) { min = Math.min(min, n.key); max = Math.max(max, n.key); }
          const span = Math.max(12, max - min);
          const innerH = TRACK_H - 16;
          ctx.fillStyle = "rgba(12,14,18,0.72)";
          for (const n of notes.slice(0, 400)) {
            const nx = x + (n.t / pat.length) * cw;
            const ny = y + 8 + innerH - ((n.key - min) / span) * innerH;
            ctx.fillRect(nx, ny, Math.max(1.5, (n.dur / pat.length) * cw), 2);
          }
        }

        ctx.fillStyle = "rgba(10,12,15,0.85)";
        ctx.font = "10px Inter, system-ui, sans-serif";
        ctx.fillText(pat.name, x + 5, y + 13);
        ctx.restore();
      }

      /* --- заголовки треков --- */
      ctx.fillStyle = "#16191e";
      ctx.fillRect(0, RULER, LEFT, h - RULER);
      for (let i = 0; i < tracks.length; i++) {
        const y = this.yOfTrack(i);
        if (y > h || y + TRACK_H < RULER) continue;
        ctx.fillStyle = "#1d2229";
        ctx.fillRect(2, y + 2, LEFT - 6, TRACK_H - 6);
        ctx.fillStyle = tracks[i].mute ? "#5b6673" : "#c8d2de";
        ctx.font = "11px Inter, system-ui, sans-serif";
        ctx.fillText(tracks[i].name, 10, y + TRACK_H / 2 + 4);
        ctx.fillStyle = tracks[i].mute ? "#3d4550" : "#7de07d";
        ctx.beginPath();
        ctx.arc(LEFT - 14, y + TRACK_H / 2, 4, 0, Math.PI * 2);
        ctx.fill();
      }

      /* --- линейка --- */
      ctx.fillStyle = "#20242a";
      ctx.fillRect(0, 0, w, RULER);
      ctx.font = "10px Inter, system-ui, sans-serif";
      for (let bar = startBar; bar <= endBar; bar++) {
        const x = this.xOfStep(bar * STEPS_PER_BAR);
        if (x < LEFT) continue;
        const major = bar % 4 === 0;
        ctx.fillStyle = major ? "#4b5666" : "#333b45";
        ctx.fillRect(x, major ? 4 : 13, 1, RULER - (major ? 4 : 13));
        if (major) {
          ctx.fillStyle = "#98a5b6";
          ctx.fillText(String(bar + 1), x + 3, 12);
        }
      }
      ctx.fillStyle = "#8894a4";
      ctx.fillText("Аранжировка", 8, 14);

      /* --- курсор --- */
      if (Engine.mode === "song") {
        const pos = Engine.playing ? Engine.positionSteps() : (Engine._pausedStep || 0);
        const x = this.xOfStep(pos);
        if (x >= LEFT && x <= w) {
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(x, RULER, 1.5, h - RULER);
          ctx.beginPath();
          ctx.moveTo(x - 5, RULER);
          ctx.lineTo(x + 5, RULER);
          ctx.lineTo(x, RULER + 6);
          ctx.closePath();
          ctx.fill();
        }
      }
    }
  };

  CS.Playlist = Playlist;

})(window.CS);
