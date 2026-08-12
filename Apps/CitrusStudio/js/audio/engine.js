"use strict";

/* ============================================================
   Citrus Studio — аудиодвижок
   • граф микшера (каналы → инсерты → мастер)
   • планировщик с упреждением (lookahead), как в Web Audio Clock
   ============================================================ */

(function (CS) {

  const { clamp } = CS.util;
  const { Instruments, Effects, Project } = CS;

  const TICKS_PER_STEP = 4;          // разрешение планировщика: 1/64 нота
  const LOOKAHEAD = 0.12;            // насколько вперёд планируем, с
  const INTERVAL = 25;               // как часто просыпается планировщик, мс

  /* ============================================================
     Построение аудиографа (используется и для offline-рендера)
     ============================================================ */

  function buildGraph(ctx, state, opts) {
    opts = opts || {};
    const inserts = [];

    // мастер (инсерт 0)
    const masterChain = Effects.buildChain(ctx, state.inserts[0] ? state.inserts[0].fx : []);
    const masterIn = ctx.createGain();
    const masterGain = ctx.createGain();
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -1.5;
    limiter.knee.value = 0;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.002;
    limiter.release.value = 0.12;

    masterIn.connect(masterChain.input);
    masterChain.output.connect(masterGain);
    masterGain.connect(limiter);

    let analyser = null;
    if (opts.analyser) {
      analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      limiter.connect(analyser);
      analyser.connect(ctx.destination);
    } else {
      limiter.connect(opts.destination || ctx.destination);
    }

    inserts[0] = { input: masterIn, gain: masterGain, pan: null, chain: masterChain };

    // обычные инсерты
    for (let i = 1; i < state.inserts.length; i++) {
      const def = state.inserts[i];
      const input = ctx.createGain();
      const chain = Effects.buildChain(ctx, def.fx);
      const gain = ctx.createGain();
      const pan = ctx.createStereoPanner();
      input.connect(chain.input);
      chain.output.connect(gain);
      gain.connect(pan);
      pan.connect(masterIn);
      let insAnalyser = null;
      if (opts.analyser) {
        insAnalyser = ctx.createAnalyser();
        insAnalyser.fftSize = 512;
        pan.connect(insAnalyser);
      }
      inserts[i] = { input, gain, pan, chain, analyser: insAnalyser };
    }

    return { ctx, inserts, master: inserts[0], masterGain, analyser, channelNodes: new Map() };
  }

  function channelNode(graph, ch) {
    let node = graph.channelNodes.get(ch.id);
    const insertIdx = clamp(ch.insert | 0, 0, graph.inserts.length - 1);
    if (!node) {
      const ctx = graph.ctx;
      const gain = ctx.createGain();
      const pan = ctx.createStereoPanner();
      gain.connect(pan);
      node = { gain, pan, insert: -1 };
      graph.channelNodes.set(ch.id, node);
    }
    if (node.insert !== insertIdx) {
      try { node.pan.disconnect(); } catch (e) {}
      node.pan.connect(graph.inserts[insertIdx].input);
      node.insert = insertIdx;
    }
    return node;
  }

  /** Применить громкости/панорамы/мьюты из состояния проекта к графу. */
  function syncMix(graph, state) {
    const anySoloCh = state.channels.some((c) => c.solo);
    const anySoloIns = state.inserts.some((x, i) => i > 0 && x.solo);

    for (const ch of state.channels) {
      const node = channelNode(graph, ch);
      const audible = !ch.mute && (!anySoloCh || ch.solo);
      const target = audible ? ch.vol * ch.vol : 0;   // квадратичная кривая громкости
      if (Math.abs(node.gain.gain.value - target) > 0.001) node.gain.gain.value = target;
      if (node.pan.pan.value !== ch.pan) node.pan.pan.value = clamp(ch.pan, -1, 1);
    }

    for (let i = 1; i < state.inserts.length && i < graph.inserts.length; i++) {
      const def = state.inserts[i];
      const g = graph.inserts[i];
      const audible = !def.mute && (!anySoloIns || def.solo);
      const target = audible ? def.vol * def.vol : 0;
      if (Math.abs(g.gain.gain.value - target) > 0.001) g.gain.gain.value = target;
      if (g.pan.pan.value !== def.pan) g.pan.pan.value = clamp(def.pan, -1, 1);
    }

    const mv = state.masterVol * state.masterVol;
    if (Math.abs(graph.masterGain.gain.value - mv) > 0.001) graph.masterGain.gain.value = mv;
  }

  /* ============================================================
     Сбор событий: какие ноты звучат на данном тике
     ============================================================ */

  /**
   * @param state   проект
   * @param tick    абсолютный тик воспроизведения
   * @param mode    "pat" | "song"
   * @param out     массив, в который добавляются { channel, note }
   */
  function collectEvents(state, tick, mode, out) {
    if (mode === "pat") {
      const pat = state.patterns.find((p) => p.id === state.currentPattern) || state.patterns[0];
      if (!pat) return out;
      const lenTicks = pat.length * TICKS_PER_STEP;
      const local = ((tick % lenTicks) + lenTicks) % lenTicks;
      pushPatternNotes(state, pat, local, out);
      return out;
    }

    for (const clip of state.playlist.clips) {
      const startT = clip.start * TICKS_PER_STEP;
      const endT = (clip.start + clip.length) * TICKS_PER_STEP;
      if (tick < startT || tick >= endT) continue;
      const pat = state.patterns.find((p) => p.id === clip.pattern);
      if (!pat) continue;
      const patTicks = pat.length * TICKS_PER_STEP;
      const local = (tick - startT) % patTicks;
      pushPatternNotes(state, pat, local, out);
    }
    return out;
  }

  function pushPatternNotes(state, pat, localTick, out) {
    for (const ch of state.channels) {
      const notes = pat.notes[ch.id];
      if (!notes || !notes.length) continue;
      for (const n of notes) {
        if (Math.round(n.t * TICKS_PER_STEP) === localTick) out.push({ channel: ch, note: n });
      }
    }
  }

  /* ============================================================
     Движок
     ============================================================ */

  const Engine = {

    ctx: null,
    graph: null,
    playing: false,
    mode: "pat",
    loopSong: true,
    recording: false,

    _timer: null,
    _tick: 0,              // следующий планируемый тик
    _nextTickTime: 0,
    _queue: [],            // [{ tick, time }] для отрисовки курсора
    _lastPlayed: { tick: 0, time: 0 },
    _held: new Map(),      // живые ноты с клавиатуры

    /* ---------- контекст и граф ---------- */

    ensureContext() {
      if (!this.ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        this.ctx = new AC({ latencyHint: "interactive" });
        this.rebuild();
      }
      if (this.ctx.state === "suspended") this.ctx.resume();
      return this.ctx;
    },

    rebuild() {
      if (!this.ctx) return;
      const old = this.graph;
      this.graph = buildGraph(this.ctx, Project.state, { analyser: true });
      syncMix(this.graph, Project.state);
      if (old) {
        // старый граф отключаем с задержкой, чтобы хвосты не щёлкали
        setTimeout(() => {
          try {
            old.masterGain.disconnect();
            if (old.analyser) old.analyser.disconnect();
            for (const fx of old.master.chain.nodes) if (fx.dispose) fx.dispose();
            for (const ins of old.inserts) {
              if (!ins) continue;
              for (const fx of ins.chain.nodes) if (fx.dispose) fx.dispose();
            }
          } catch (e) {}
        }, 400);
      }
      CS.bus.emit("graph:rebuilt");
    },

    /* ---------- тайминг ---------- */

    stepDuration() {
      return 60 / Project.state.bpm / 4;
    },

    tickDuration() {
      return this.stepDuration() / TICKS_PER_STEP;
    },

    lengthTicks() {
      if (this.mode === "pat") {
        const pat = Project.currentPattern();
        return (pat ? pat.length : 16) * TICKS_PER_STEP;
      }
      return Project.songLength() * TICKS_PER_STEP;
    },

    /** Текущая позиция в шагах (дробная) — для курсора. */
    positionSteps() {
      if (!this.playing) return this._pausedStep || 0;
      const elapsed = this.ctx.currentTime - this._lastPlayed.time;
      const tick = this._lastPlayed.tick + elapsed / this.tickDuration();
      const len = this.lengthTicks();
      return (len > 0 ? ((tick % len) + len) % len : tick) / TICKS_PER_STEP;
    },

    /* ---------- транспорт ---------- */

    play(fromStep) {
      this.ensureContext();
      if (this.playing) return;
      const startTick = Math.round((fromStep !== undefined ? fromStep : (this._pausedStep || 0)) * TICKS_PER_STEP);
      this._tick = startTick;
      this._nextTickTime = this.ctx.currentTime + 0.06;
      this._lastPlayed = { tick: startTick, time: this._nextTickTime };
      this._queue.length = 0;
      this.playing = true;
      this._timer = setInterval(() => this._schedule(), INTERVAL);
      this._schedule();
      CS.bus.emit("transport:play");
    },

    pause() {
      if (!this.playing) return;
      this._pausedStep = this.positionSteps();
      this._halt();
      CS.bus.emit("transport:pause");
    },

    stop() {
      this._pausedStep = 0;
      this._halt();
      CS.bus.emit("transport:stop");
    },

    toggle() {
      if (this.playing) this.pause();
      else this.play();
    },

    _halt() {
      this.playing = false;
      if (this._timer) clearInterval(this._timer);
      this._timer = null;
      this._queue.length = 0;
      // мягко глушим хвосты
      if (this.graph) {
        const t = this.ctx.currentTime;
        for (const [, node] of this.graph.channelNodes) {
          const v = node.gain.gain.value;
          node.gain.gain.cancelScheduledValues(t);
          node.gain.gain.setValueAtTime(v, t);
        }
      }
    },

    seek(step) {
      const wasPlaying = this.playing;
      this._pausedStep = Math.max(0, step);
      if (wasPlaying) {
        this._halt();
        this.play(this._pausedStep);
      } else {
        CS.bus.emit("transport:seek", this._pausedStep);
      }
    },

    setMode(mode) {
      if (this.mode === mode) return;
      const wasPlaying = this.playing;
      this._halt();
      this.mode = mode;
      this._pausedStep = 0;
      CS.bus.emit("transport:mode", mode);
      if (wasPlaying) this.play(0);
    },

    /* ---------- планировщик ---------- */

    _schedule() {
      if (!this.playing) return;
      const ctx = this.ctx;
      const state = Project.state;
      syncMix(this.graph, state);

      const tickDur = this.tickDuration();
      const stepDur = this.stepDuration();
      const lenTicks = this.lengthTicks();

      while (this._nextTickTime < ctx.currentTime + LOOKAHEAD) {
        let tick = this._tick;

        // зацикливание
        if (lenTicks > 0) {
          if (this.mode === "pat") {
            tick = ((tick % lenTicks) + lenTicks) % lenTicks;
          } else if (tick >= lenTicks) {
            if (this.loopSong) {
              tick = tick % lenTicks;
              this._tick = tick;
            } else {
              this.stop();
              return;
            }
          }
        }

        const events = collectEvents(state, tick, this.mode, []);
        // свинг: чётные 1/16 на месте, нечётные — сдвигаются позже
        const step = Math.floor(tick / TICKS_PER_STEP);
        const swingOffset = (step % 2 === 1) ? state.swing * 0.5 * stepDur : 0;
        const when = this._nextTickTime + swingOffset;

        for (const ev of events) {
          if (!Project.channelAudible(ev.channel)) continue;
          const node = channelNode(this.graph, ev.channel);
          Instruments.trigger(ctx, node.gain, ev.channel, {
            key: ev.note.key,
            vel: ev.note.vel,
            dur: Math.max(0.02, (ev.note.dur || 1) * stepDur)
          }, when);
        }

        // метроном
        if (state.metronome && tick % (TICKS_PER_STEP * 4) === 0) {
          Instruments.metronome(ctx, this.graph.master.input, this._nextTickTime, step % 16 === 0);
        }

        this._queue.push({ tick, time: this._nextTickTime });
        this._nextTickTime += tickDur;
        this._tick = (this.mode === "pat" ? tick : this._tick) + 1;
      }

      // подчищаем очередь курсора
      while (this._queue.length && this._queue[0].time < ctx.currentTime - 1) this._queue.shift();
    },

    /** Вызывается из rAF: обновляет «отыгранный» тик для курсора. */
    pumpCursor() {
      if (!this.playing) return null;
      const now = this.ctx.currentTime;
      let played = null;
      while (this._queue.length && this._queue[0].time <= now) {
        played = this._queue.shift();
      }
      if (played) this._lastPlayed = played;
      return this._lastPlayed;
    },

    /* ---------- живая игра (клавиатура, превью) ---------- */

    noteOn(channel, key, vel) {
      this.ensureContext();
      if (!this.graph) return;
      syncMix(this.graph, Project.state);
      const node = channelNode(this.graph, channel);
      const handle = Instruments.trigger(this.ctx, node.gain, channel, {
        key, vel: vel === undefined ? 0.85 : vel
      }, this.ctx.currentTime + 0.005);
      const id = channel.id + ":" + key;
      const prev = this._held.get(id);
      if (prev && prev.release) prev.release(this.ctx.currentTime);
      this._held.set(id, handle);
      return handle;
    },

    noteOff(channel, key) {
      const id = channel.id + ":" + key;
      const handle = this._held.get(id);
      if (handle && handle.release) handle.release(this.ctx.currentTime);
      this._held.delete(id);
    },

    /** Короткое превью ноты (клик по клавише / шагу). */
    preview(channel, key, dur) {
      this.ensureContext();
      if (!this.graph) return;
      syncMix(this.graph, Project.state);
      const node = channelNode(this.graph, channel);
      Instruments.trigger(this.ctx, node.gain, channel, {
        key: key === undefined ? channel.key : key,
        vel: 0.85,
        dur: dur === undefined ? 0.35 : dur
      }, this.ctx.currentTime + 0.005);
    },

    /** Обновить живой узел эффекта после кручения ручки (без пересборки графа). */
    updateFx(item) {
      if (!this.graph) return;
      for (const ins of this.graph.inserts) {
        if (!ins) continue;
        for (const fx of ins.chain.nodes) {
          if (fx.source === item) { fx.update(item.params); return true; }
        }
      }
      return false;
    },

    /* ---------- уровень для индикатора ---------- */

    _peakOf(analyser) {
      if (!analyser) return 0;
      const size = analyser.fftSize;
      if (!this._bufs) this._bufs = {};
      if (!this._bufs[size]) this._bufs[size] = new Float32Array(size);
      const buf = this._bufs[size];
      analyser.getFloatTimeDomainData(buf);
      let peak = 0;
      for (let i = 0; i < size; i++) {
        const v = Math.abs(buf[i]);
        if (v > peak) peak = v;
      }
      return peak;
    },

    masterLevel() {
      return this.graph ? this._peakOf(this.graph.analyser) : 0;
    },

    insertLevel(index) {
      if (!this.graph || !this.graph.inserts[index]) return 0;
      if (index === 0) return this.masterLevel();
      return this._peakOf(this.graph.inserts[index].analyser);
    }
  };

  CS.Engine = Engine;
  CS.audio = { buildGraph, syncMix, channelNode, collectEvents, TICKS_PER_STEP };

})(window.CS);
