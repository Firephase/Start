"use strict";

/* ============================================================
   Citrus Studio — модель проекта
   Паттерн хранит ноты по каналам; степ-секвенсор и Piano Roll
   работают с ОДНИМИ И ТЕМИ ЖЕ нотами (как в FL Studio).
   Время нот измеряется в шагах (1 шаг = 1/16 такта).
   ============================================================ */

(function (CS) {

  const { uid, deepClone, clamp } = CS.util;
  const { defaultParams, defs } = CS.Instruments;

  const STEPS_PER_BAR = 16;
  const STEPS_PER_BEAT = 4;

  /* ---------------- Пресеты браузера ---------------- */

  const drumPresets = [
    { label: "Kick", type: "kick" },
    { label: "Kick 808", type: "kick", params: { tune: 42, decay: 1.1, punch: 0.35, drive: 0.5 }, color: "#ff5f4d" },
    { label: "Snare", type: "snare" },
    { label: "Clap", type: "clap" },
    { label: "Hat закрытый", type: "hat", params: { decay: 0.045 } },
    { label: "Hat открытый", type: "hat", params: { decay: 0.34, metal: 0.85 }, color: "#5fe0b0" },
    { label: "Tom", type: "tom" },
    { label: "Cymbal", type: "cymbal" },
    { label: "Rim", type: "rim" }
  ];

  const synthPresets = [
    {
      label: "Bass (саб)", type: "synth", color: "#7d8cff", key: 36,
      params: { w1: "sine", m1: 1, w2: "sawtooth", c2: 0, f2: 4, m2: 0.35, w3: "square", c3: -12, f3: 0, m3: 0.2,
                cutoff: 900, res: 3, fEnv: 0.3, fd: 0.15, a: 0.004, d: 0.3, s: 0.75, r: 0.12 }
    },
    {
      label: "Reese Bass", type: "synth", color: "#5a6cff", key: 36,
      params: { w1: "sawtooth", m1: 1, w2: "sawtooth", c2: 0, f2: 22, m2: 1, w3: "sawtooth", c3: -12, f3: -14, m3: 0.7,
                uni: 2, spread: 24, cutoff: 700, res: 5, fEnv: 0.2, a: 0.01, d: 0.6, s: 0.9, r: 0.2 }
    },
    {
      label: "Pluck", type: "synth", color: "#ffd166", key: 60,
      params: { w1: "sawtooth", m1: 0.9, w2: "square", c2: 12, f2: 6, m2: 0.35, m3: 0,
                cutoff: 4200, res: 6, fEnv: 0.55, fd: 0.12, a: 0.002, d: 0.16, s: 0.0, r: 0.16 }
    },
    {
      label: "Lead", type: "synth", color: "#ff9f43", key: 72,
      params: { w1: "sawtooth", m1: 1, w2: "sawtooth", c2: 0, f2: 12, m2: 0.8, w3: "square", c3: 12, f3: -8, m3: 0.3,
                uni: 3, spread: 18, cutoff: 6500, res: 2, fEnv: 0.3, a: 0.01, d: 0.4, s: 0.65, r: 0.25 }
    },
    {
      label: "Pad / Strings", type: "synth", color: "#b48cff", key: 60,
      params: { w1: "sawtooth", m1: 0.8, w2: "triangle", c2: 7, f2: 8, m2: 0.6, w3: "sawtooth", c3: -12, f3: -9, m3: 0.5,
                uni: 2, spread: 20, cutoff: 2400, res: 1, fEnv: 0.25, fa: 0.35, fd: 1.4, a: 0.55, d: 1.2, s: 0.8, r: 1.4 }
    },
    {
      label: "Organ", type: "synth", color: "#8ef0c8", key: 60,
      params: { w1: "sine", m1: 1, w2: "sine", c2: 12, f2: 0, m2: 0.55, w3: "sine", c3: 19, f3: 0, m3: 0.32,
                cutoff: 9000, res: 0.7, fEnv: 0.05, a: 0.008, d: 0.1, s: 0.95, r: 0.1 }
    },
    {
      label: "Chip Square", type: "synth", color: "#a0e7ff", key: 72,
      params: { w1: "square", m1: 1, m2: 0, m3: 0, cutoff: 12000, res: 0.5, fEnv: 0, a: 0.002, d: 0.1, s: 0.6, r: 0.05 }
    }
  ];

  /* ---------------- Цвета каналов ---------------- */

  const palette = ["#ff7a59", "#ffd166", "#8ef0c8", "#6fc3ff", "#b48cff", "#f6a1ff", "#ffa94d", "#a0e7ff", "#7d8cff", "#c9f57a"];
  let colorIdx = 0;
  const nextColor = () => palette[(colorIdx++) % palette.length];

  /* ============================================================
     Фабрики
     ============================================================ */

  function makeChannel(type, name, params, extra) {
    const d = defs[type] || defs.synth;
    return Object.assign({
      id: uid("ch"),
      name: name || d.name,
      type,
      color: nextColor(),
      params: Object.assign(defaultParams(type), params || {}),
      key: d.key || 60,          // нота по умолчанию для степ-секвенсора
      vol: 0.8,
      pan: 0,
      mute: false,
      solo: false,
      insert: 1
    }, extra || {});
  }

  function makePattern(name, length) {
    return {
      id: uid("pat"),
      name: name || "Паттерн",
      color: nextColor(),
      length: length || 16,
      notes: {}
    };
  }

  function makeInsert(name) {
    return { name, vol: 0.8, pan: 0, mute: false, solo: false, fx: [] };
  }

  function makeFx(type, params) {
    return { type, params: Object.assign(CS.Effects.defaultParams(type), params || {}), enabled: true };
  }

  function emptyProject() {
    const inserts = [makeInsert("Мастер")];
    for (let i = 1; i <= 12; i++) inserts.push(makeInsert("Инсерт " + i));
    return {
      version: 1,
      name: "Новый проект",
      bpm: 128,
      swing: 0,
      masterVol: 0.8,
      metronome: false,
      channels: [],
      patterns: [],
      playlist: {
        tracks: [{ name: "Трек 1" }, { name: "Трек 2" }, { name: "Трек 3" }, { name: "Трек 4" }, { name: "Трек 5" }],
        clips: []
      },
      inserts,
      currentPattern: null
    };
  }

  /* ============================================================
     Демо-проект: играбельный трек сразу после запуска
     ============================================================ */

  function demoProject() {
    const p = emptyProject();
    p.name = "Citrus Demo";
    p.bpm = 126;
    p.swing = 0.12;

    const preset = (list, label) => list.find((x) => x.label === label);

    const kick = makeChannel("kick", "Kick", { decay: 0.5, punch: 0.6, drive: 0.3 }, { insert: 1, color: "#ff7a59" });
    const clap = makeChannel("clap", "Clap", null, { insert: 2, color: "#f6a1ff", vol: 0.7 });
    const hat = makeChannel("hat", "Hat", { decay: 0.045 }, { insert: 3, color: "#8ef0c8", vol: 0.55 });
    const ohat = makeChannel("hat", "Open Hat", { decay: 0.3, metal: 0.85 }, { insert: 3, color: "#5fe0b0", vol: 0.4 });
    const snare = makeChannel("snare", "Snare", null, { insert: 2, color: "#ffd166", vol: 0.6 });

    const bp = preset(synthPresets, "Bass (саб)");
    const bass = makeChannel("synth", "Bass", bp.params, { insert: 4, color: bp.color, key: 36, vol: 0.75 });

    const cp = preset(synthPresets, "Pad / Strings");
    const chords = makeChannel("synth", "Chords", cp.params, { insert: 5, color: cp.color, key: 60, vol: 0.5 });

    const lp = preset(synthPresets, "Pluck");
    const lead = makeChannel("synth", "Pluck", lp.params, { insert: 6, color: lp.color, key: 72, vol: 0.55 });

    p.channels = [kick, clap, hat, ohat, snare, bass, chords, lead];

    // --- эффекты на инсертах ---
    p.inserts[3].fx.push(makeFx("filter", { mode: "highpass", cutoff: 320, q: 0.7 }));
    p.inserts[5].fx.push(makeFx("chorus", { mix: 0.4 }));
    p.inserts[5].fx.push(makeFx("reverb", { size: 3.2, mix: 0.4 }));
    p.inserts[6].fx.push(makeFx("delay", { time: 285, feedback: 0.35, mix: 0.3 }));
    p.inserts[6].fx.push(makeFx("reverb", { size: 2, mix: 0.22 }));
    p.inserts[0].fx.push(makeFx("comp", { threshold: -14, ratio: 3, makeup: 2 }));
    p.inserts[0].fx.push(makeFx("eq3", { low: 1.5, high: 1.5 }));

    // --- вспомогательное ---
    const N = (t, key, dur, vel) => ({ t, dur: dur === undefined ? 1 : dur, key, vel: vel === undefined ? 0.85 : vel });

    function pattern(name, length, fill) {
      const pat = makePattern(name, length);
      fill(pat, (ch, arr) => { pat.notes[ch.id] = arr; });
      p.patterns.push(pat);
      return pat;
    }

    // Ударные A
    const drumsA = pattern("Ударные A", 16, (pat, set) => {
      set(kick, [0, 4, 8, 12].map((t) => N(t, 60, 1, 1)));
      set(clap, [4, 12].map((t) => N(t, 60, 1, 0.9)));
      set(hat, [0, 2, 4, 6, 8, 10, 12, 14].map((t, i) => N(t, 60, 1, i % 2 ? 0.5 : 0.8)));
      set(ohat, [6, 14].map((t) => N(t, 60, 1, 0.5)));
    });

    // Ударные B — с сбивкой
    const drumsB = pattern("Ударные B", 16, (pat, set) => {
      set(kick, [0, 4, 8, 10].map((t) => N(t, 60, 1, 1)));
      set(clap, [4, 12].map((t) => N(t, 60, 1, 0.9)));
      set(hat, [0, 2, 4, 6, 8, 10, 12, 13, 14, 15].map((t, i) => N(t, 60, 1, i % 2 ? 0.5 : 0.8)));
      set(snare, [12, 13, 14, 15].map((t, i) => N(t, 60, 1, 0.4 + i * 0.16)));
    });

    // Басовая линия: Cm - Ab - Eb - Bb (4 такта)
    const bassPat = pattern("Бас", 64, (pat, set) => {
      const roots = [36, 32, 39, 34]; // C3, Ab2, Eb3, Bb2 (нумерация FL: C5 = MIDI 60)
      const arr = [];
      roots.forEach((root, bar) => {
        const base = bar * 16;
        [0, 3, 6, 8, 11, 14].forEach((off, i) => {
          arr.push(N(base + off, root + (i === 4 ? 12 : 0), 2.4, 0.9));
        });
      });
      set(bass, arr);
    });

    // Аккорды
    const chordPat = pattern("Аккорды", 64, (pat, set) => {
      const chords4 = [[60, 63, 67], [56, 60, 63], [63, 67, 70], [58, 62, 65]];
      const arr = [];
      chords4.forEach((ch, bar) => {
        const base = bar * 16;
        ch.forEach((k) => {
          arr.push(N(base, k, 14, 0.65));
        });
      });
      set(chords, arr);
    });

    // Мелодия
    const leadPat = pattern("Мелодия", 64, (pat, set) => {
      const seq = [
        [0, 75], [2, 72], [4, 70], [7, 75], [10, 72], [12, 79], [14, 75],
        [16, 68], [18, 72], [20, 75], [23, 72], [26, 68], [28, 75], [30, 72],
        [32, 70], [34, 75], [36, 79], [39, 75], [42, 82], [44, 79], [46, 75],
        [48, 74], [50, 70], [52, 77], [55, 74], [58, 70], [60, 77], [62, 79]
      ];
      set(lead, seq.map(([t, k]) => N(t, k, 1.6, 0.8)));
    });

    // --- аранжировка (в шагах) ---
    const clip = (pattern, track, startBar) => ({
      id: uid("clip"),
      pattern: pattern.id,
      track,
      start: startBar * STEPS_PER_BAR,
      length: pattern.length
    });

    const clips = [];
    for (let bar = 0; bar < 8; bar++) {
      clips.push(clip(bar % 4 === 3 ? drumsB : drumsA, 0, bar));
    }
    clips.push(clip(bassPat, 1, 0));
    clips.push(clip(bassPat, 1, 4));
    clips.push(clip(chordPat, 2, 0));
    clips.push(clip(chordPat, 2, 4));
    clips.push(clip(leadPat, 3, 4));

    p.playlist.clips = clips;
    p.currentPattern = drumsA.id;
    return p;
  }

  /* ============================================================
     Модуль проекта
     ============================================================ */

  const Project = {

    state: null,

    init(obj) {
      this.state = obj || demoProject();
      this._history = [];
      this._future = [];
      CS.bus.emit("project:loaded", this.state);
      return this.state;
    },

    /* ---- доступ ---- */

    channel(id) { return this.state.channels.find((c) => c.id === id) || null; },
    pattern(id) { return this.state.patterns.find((p) => p.id === id) || null; },
    currentPattern() {
      return this.pattern(this.state.currentPattern) || this.state.patterns[0] || null;
    },
    setCurrentPattern(id) {
      if (!this.pattern(id)) return;
      this.state.currentPattern = id;
      CS.bus.emit("pattern:changed", id);
    },

    notes(patternId, channelId) {
      const pat = this.pattern(patternId);
      if (!pat) return [];
      if (!pat.notes[channelId]) pat.notes[channelId] = [];
      return pat.notes[channelId];
    },

    /* ---- каналы ---- */

    addChannel(type, name, params, extra) {
      const ch = makeChannel(type, name, params, extra);
      // раскидываем по свободным инсертам
      const used = this.state.channels.map((c) => c.insert);
      let ins = 1;
      while (used.indexOf(ins) >= 0 && ins < this.state.inserts.length - 1) ins++;
      ch.insert = extra && extra.insert !== undefined ? extra.insert : ins;
      this.state.channels.push(ch);
      CS.bus.emit("channels:changed");
      return ch;
    },

    removeChannel(id) {
      const i = this.state.channels.findIndex((c) => c.id === id);
      if (i < 0) return;
      this.state.channels.splice(i, 1);
      for (const pat of this.state.patterns) delete pat.notes[id];
      CS.bus.emit("channels:changed");
    },

    moveChannel(id, dir) {
      const i = this.state.channels.findIndex((c) => c.id === id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= this.state.channels.length) return;
      const arr = this.state.channels;
      [arr[i], arr[j]] = [arr[j], arr[i]];
      CS.bus.emit("channels:changed");
    },

    cloneChannel(id) {
      const src = this.channel(id);
      if (!src) return;
      const copy = deepClone(src);
      copy.id = uid("ch");
      copy.name = src.name + " копия";
      copy._buffer = src._buffer;
      const i = this.state.channels.indexOf(src);
      this.state.channels.splice(i + 1, 0, copy);
      // копируем ноты во всех паттернах
      for (const pat of this.state.patterns) {
        if (pat.notes[id]) pat.notes[copy.id] = deepClone(pat.notes[id]);
      }
      CS.bus.emit("channels:changed");
      return copy;
    },

    anySolo() { return this.state.channels.some((c) => c.solo); },

    channelAudible(ch) {
      if (ch.mute) return false;
      if (this.anySolo() && !ch.solo) return false;
      const ins = this.state.inserts[ch.insert];
      if (ins && ins.mute) return false;
      const soloIns = this.state.inserts.some((x) => x.solo);
      if (soloIns && ins && !ins.solo && ch.insert !== 0) return false;
      return true;
    },

    /* ---- паттерны ---- */

    addPattern(name, length) {
      const pat = makePattern(name || "Паттерн " + (this.state.patterns.length + 1), length);
      this.state.patterns.push(pat);
      this.state.currentPattern = pat.id;
      CS.bus.emit("patterns:changed");
      return pat;
    },

    clonePattern(id) {
      const src = this.pattern(id);
      if (!src) return null;
      const copy = deepClone(src);
      copy.id = uid("pat");
      copy.name = src.name + " копия";
      this.state.patterns.push(copy);
      this.state.currentPattern = copy.id;
      CS.bus.emit("patterns:changed");
      return copy;
    },

    removePattern(id) {
      if (this.state.patterns.length <= 1) return;
      const i = this.state.patterns.findIndex((p) => p.id === id);
      if (i < 0) return;
      this.state.patterns.splice(i, 1);
      this.state.playlist.clips = this.state.playlist.clips.filter((c) => c.pattern !== id);
      if (this.state.currentPattern === id) this.state.currentPattern = this.state.patterns[0].id;
      CS.bus.emit("patterns:changed");
    },

    setPatternLength(id, len) {
      const pat = this.pattern(id);
      if (!pat) return;
      pat.length = clamp(len, 4, 256);
      // обрезаем ноты за пределами
      for (const chId in pat.notes) {
        pat.notes[chId] = pat.notes[chId].filter((n) => n.t < pat.length);
      }
      for (const c of this.state.playlist.clips) if (c.pattern === id) c.length = pat.length;
      CS.bus.emit("pattern:resized", id);
    },

    /* ---- плейлист ---- */

    addClip(patternId, track, start) {
      const pat = this.pattern(patternId);
      if (!pat) return null;
      const clip = { id: uid("clip"), pattern: patternId, track, start, length: pat.length };
      this.state.playlist.clips.push(clip);
      CS.bus.emit("playlist:changed");
      return clip;
    },

    removeClip(id) {
      const i = this.state.playlist.clips.findIndex((c) => c.id === id);
      if (i >= 0) {
        this.state.playlist.clips.splice(i, 1);
        CS.bus.emit("playlist:changed");
      }
    },

    songLength() {
      let max = 0;
      for (const c of this.state.playlist.clips) max = Math.max(max, c.start + c.length);
      return Math.max(max, STEPS_PER_BAR);
    },

    /* ---- история (Ctrl+Z) ---- */

    _history: [],
    _future: [],

    snapshot() {
      const snap = this.serialize();
      this._history.push(snap);
      if (this._history.length > 60) this._history.shift();
      this._future.length = 0;
    },

    undo() {
      if (!this._history.length) return false;
      const cur = this.serialize();
      const prev = this._history.pop();
      this._future.push(cur);
      this._restore(prev);
      return true;
    },

    redo() {
      if (!this._future.length) return false;
      const cur = this.serialize();
      const next = this._future.pop();
      this._history.push(cur);
      this._restore(next);
      return true;
    },

    _restore(data) {
      const buffers = {};
      for (const c of this.state.channels) if (c._buffer) buffers[c.id] = c._buffer;
      const obj = JSON.parse(data);
      for (const c of obj.channels) if (buffers[c.id]) c._buffer = buffers[c.id];
      this.state = obj;
      CS.bus.emit("project:loaded", this.state);
    },

    /* ---- сериализация ---- */

    serialize() {
      return JSON.stringify(this.state, (k, v) => (k === "_buffer" ? undefined : v));
    },

    save(filename) {
      const blob = new Blob([this.serialize()], { type: "application/json" });
      CS.util.downloadBlob(blob, (filename || this.state.name || "project") + ".citrus");
    },

    autosave() {
      try { localStorage.setItem("citrus.autosave", this.serialize()); } catch (e) { /* переполнение */ }
    },

    loadAutosave() {
      try {
        const raw = localStorage.getItem("citrus.autosave");
        if (!raw) return null;
        return JSON.parse(raw);
      } catch (e) { return null; }
    },

    loadFromText(text) {
      const obj = JSON.parse(text);
      if (!obj.channels || !obj.patterns) throw new Error("Не похоже на проект Citrus");
      // подстраховка для старых/битых файлов
      obj.playlist = obj.playlist || { tracks: [{ name: "Трек 1" }], clips: [] };
      obj.inserts = obj.inserts || emptyProject().inserts;
      this.init(obj);
      return obj;
    }
  };

  CS.Project = Project;
  CS.presets = { drums: drumPresets, synths: synthPresets };
  CS.makeChannel = makeChannel;
  CS.makeFx = makeFx;
  CS.makeInsert = makeInsert;
  CS.demoProject = demoProject;
  CS.emptyProject = emptyProject;
  CS.STEPS_PER_BAR = STEPS_PER_BAR;
  CS.STEPS_PER_BEAT = STEPS_PER_BEAT;

})(window.CS);
