"use strict";

/* ============================================================
   Citrus Studio — синтез инструментов
   Всё генерируется процедурно, внешних сэмплов нет.
   Каждая функция триггера работает с ЛЮБЫМ AudioContext,
   поэтому один и тот же код играет вживую и рендерит в WAV.
   ============================================================ */

(function (CS) {

  const { midiToFreq, clamp } = CS.util;

  /* ---------- Кэш шумового буфера на каждый контекст ---------- */

  const noiseCache = new WeakMap();

  function noiseBuffer(ctx) {
    if (noiseCache.has(ctx)) return noiseCache.get(ctx);
    const len = Math.floor(ctx.sampleRate * 2);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    noiseCache.set(ctx, buf);
    return buf;
  }

  function noiseSource(ctx) {
    const s = ctx.createBufferSource();
    s.buffer = noiseBuffer(ctx);
    s.loop = true;
    s.playbackRate.value = 0.9 + Math.random() * 0.2;
    return s;
  }

  /* ---------- Огибающие ---------- */

  const EPS = 0.0001;

  // Быстрое экспоненциальное затухание (перкуссия)
  function percEnv(param, time, peak, decay, attack) {
    const a = attack === undefined ? 0.001 : attack;
    param.setValueAtTime(EPS, time);
    param.exponentialRampToValueAtTime(Math.max(peak, EPS), time + a);
    param.exponentialRampToValueAtTime(EPS, time + a + decay);
  }

  // ADSR с явным моментом релиза
  function adsrEnv(param, time, peak, a, d, s, releaseTime, r) {
    const sustain = Math.max(peak * s, EPS);
    param.setValueAtTime(EPS, time);
    param.exponentialRampToValueAtTime(Math.max(peak, EPS), time + a);
    param.exponentialRampToValueAtTime(sustain, time + a + d);
    if (releaseTime !== null && releaseTime !== undefined) {
      const rt = Math.max(releaseTime, time + a + 0.001);
      if (param.cancelAndHoldAtTime) param.cancelAndHoldAtTime(rt);
      else param.cancelScheduledValues(rt);
      param.exponentialRampToValueAtTime(EPS, rt + r);
    }
  }

  function stopLater(ctx, nodes, when) {
    for (const n of nodes) {
      try { n.stop(when); } catch (e) { /* уже остановлен */ }
    }
  }

  const dbGain = (db) => Math.pow(10, db / 20);

  /* ============================================================
     Описания инструментов — по ним генерируется UI плагина
     ============================================================ */

  const defs = {

    kick: {
      name: "Kick", kind: "drum", color: "#ff7a59", key: 60,
      params: [
        { key: "tune", label: "Тон", min: 30, max: 140, def: 52, curve: "log", unit: "Гц" },
        { key: "punch", label: "Панч", min: 0, max: 1, def: 0.55 },
        { key: "decay", label: "Затух", min: 0.05, max: 1.6, def: 0.42, unit: "с" },
        { key: "click", label: "Клик", min: 0, max: 1, def: 0.3 },
        { key: "drive", label: "Драйв", min: 0, max: 1, def: 0.25 }
      ]
    },

    snare: {
      name: "Snare", kind: "drum", color: "#ffd166", key: 60,
      params: [
        { key: "tune", label: "Тон", min: 90, max: 400, def: 185, curve: "log", unit: "Гц" },
        { key: "decay", label: "Затух", min: 0.04, max: 0.9, def: 0.22, unit: "с" },
        { key: "snap", label: "Снэп", min: 0, max: 1, def: 0.7 },
        { key: "tone", label: "Окрас", min: 600, max: 6000, def: 1900, curve: "log", unit: "Гц" }
      ]
    },

    clap: {
      name: "Clap", kind: "drum", color: "#f6a1ff", key: 60,
      params: [
        { key: "decay", label: "Затух", min: 0.05, max: 0.8, def: 0.26, unit: "с" },
        { key: "spread", label: "Разброс", min: 4, max: 40, def: 13, unit: "мс" },
        { key: "tone", label: "Окрас", min: 700, max: 4000, def: 1500, curve: "log", unit: "Гц" }
      ]
    },

    hat: {
      name: "Hat", kind: "drum", color: "#8ef0c8", key: 60,
      params: [
        { key: "decay", label: "Затух", min: 0.01, max: 0.9, def: 0.06, curve: "log", unit: "с" },
        { key: "tone", label: "HP", min: 2000, max: 14000, def: 7200, curve: "log", unit: "Гц" },
        { key: "metal", label: "Металл", min: 0, max: 1, def: 0.7 }
      ]
    },

    tom: {
      name: "Tom", kind: "drum", color: "#ffa94d", key: 60,
      params: [
        { key: "tune", label: "Тон", min: 60, max: 420, def: 140, curve: "log", unit: "Гц" },
        { key: "decay", label: "Затух", min: 0.08, max: 1.4, def: 0.4, unit: "с" },
        { key: "bend", label: "Бенд", min: 0, max: 1, def: 0.4 }
      ]
    },

    cymbal: {
      name: "Cymbal", kind: "drum", color: "#a0e7ff", key: 60,
      params: [
        { key: "decay", label: "Затух", min: 0.2, max: 4, def: 1.6, unit: "с" },
        { key: "tone", label: "HP", min: 1500, max: 9000, def: 4200, curve: "log", unit: "Гц" }
      ]
    },

    rim: {
      name: "Rim", kind: "drum", color: "#c9b6ff", key: 60,
      params: [
        { key: "tune", label: "Тон", min: 200, max: 1600, def: 620, curve: "log", unit: "Гц" },
        { key: "decay", label: "Затух", min: 0.01, max: 0.3, def: 0.05, unit: "с" }
      ]
    },

    synth: {
      name: "Trio Osc", kind: "synth", color: "#6fc3ff", key: 60,
      groups: [
        { title: "Осциллятор 1", keys: ["w1", "m1"] },
        { title: "Осциллятор 2", keys: ["w2", "c2", "f2", "m2"] },
        { title: "Осциллятор 3", keys: ["w3", "c3", "f3", "m3"] },
        { title: "Унисон", keys: ["uni", "spread"] },
        { title: "Фильтр", keys: ["fType", "cutoff", "res", "fEnv", "fa", "fd"] },
        { title: "Огибающая", keys: ["a", "d", "s", "r"] }
      ],
      params: [
        { key: "w1", label: "Волна 1", type: "enum", options: ["sawtooth", "square", "triangle", "sine"], def: "sawtooth" },
        { key: "m1", label: "Ур. 1", min: 0, max: 1, def: 0.8 },
        { key: "w2", label: "Волна 2", type: "enum", options: ["sawtooth", "square", "triangle", "sine"], def: "sawtooth" },
        { key: "c2", label: "Полутон 2", min: -24, max: 24, def: 0, step: 1 },
        { key: "f2", label: "Расстр 2", min: -50, max: 50, def: 9, unit: "ц" },
        { key: "m2", label: "Ур. 2", min: 0, max: 1, def: 0.6 },
        { key: "w3", label: "Волна 3", type: "enum", options: ["sawtooth", "square", "triangle", "sine"], def: "sine" },
        { key: "c3", label: "Полутон 3", min: -24, max: 24, def: -12, step: 1 },
        { key: "f3", label: "Расстр 3", min: -50, max: 50, def: -7, unit: "ц" },
        { key: "m3", label: "Ур. 3", min: 0, max: 1, def: 0.5 },
        { key: "uni", label: "Голоса", min: 1, max: 4, def: 1, step: 1 },
        { key: "spread", label: "Расстр", min: 0, max: 40, def: 12, unit: "ц" },
        { key: "fType", label: "Фильтр", type: "enum", options: ["lowpass", "highpass", "bandpass"], def: "lowpass" },
        { key: "cutoff", label: "Срез", min: 60, max: 18000, def: 3200, curve: "log", unit: "Гц" },
        { key: "res", label: "Рез", min: 0.1, max: 20, def: 1.2, curve: "log" },
        { key: "fEnv", label: "Огиб→срез", min: 0, max: 1, def: 0.35 },
        { key: "fa", label: "Ф.атака", min: 0.001, max: 1, def: 0.005, curve: "log", unit: "с" },
        { key: "fd", label: "Ф.спад", min: 0.01, max: 3, def: 0.28, curve: "log", unit: "с" },
        { key: "a", label: "Атака", min: 0.001, max: 2, def: 0.006, curve: "log", unit: "с" },
        { key: "d", label: "Спад", min: 0.005, max: 3, def: 0.25, curve: "log", unit: "с" },
        { key: "s", label: "Сустейн", min: 0, max: 1, def: 0.7 },
        { key: "r", label: "Релиз", min: 0.005, max: 4, def: 0.22, curve: "log", unit: "с" }
      ]
    },

    sampler: {
      name: "Sampler", kind: "sampler", color: "#8ad7ff", key: 60,
      params: [
        { key: "root", label: "База", min: 24, max: 96, def: 60, step: 1 },
        { key: "start", label: "Старт", min: 0, max: 1, def: 0 },
        { key: "end", label: "Конец", min: 0, max: 1, def: 1 },
        { key: "a", label: "Атака", min: 0.001, max: 1, def: 0.002, curve: "log", unit: "с" },
        { key: "d", label: "Спад", min: 0.005, max: 4, def: 2, curve: "log", unit: "с" },
        { key: "s", label: "Сустейн", min: 0, max: 1, def: 1 },
        { key: "r", label: "Релиз", min: 0.005, max: 3, def: 0.06, curve: "log", unit: "с" },
        { key: "loop", label: "Цикл", type: "bool", def: false },
        { key: "reverse", label: "Реверс", type: "bool", def: false }
      ]
    }
  };

  function defaultParams(type) {
    const d = defs[type];
    if (!d) return {};
    const p = {};
    for (const spec of d.params) p[spec.key] = spec.def;
    return p;
  }

  function paramSpec(type, key) {
    const d = defs[type];
    if (!d) return null;
    return d.params.find((s) => s.key === key) || null;
  }

  /* ============================================================
     Триггеры инструментов
     Все возвращают { release(time), stopAt }
     ============================================================ */

  function triggerKick(ctx, dest, p, note, time) {
    const osc = ctx.createOscillator();
    osc.type = "sine";
    const semis = note.key - 60;
    const base = p.tune * Math.pow(2, semis / 12);
    const top = base * (1 + p.punch * 6);

    osc.frequency.setValueAtTime(top, time);
    osc.frequency.exponentialRampToValueAtTime(base, time + 0.02 + p.punch * 0.06);

    const g = ctx.createGain();
    percEnv(g.gain, time, note.vel, p.decay, 0.002);

    let out = g;
    if (p.drive > 0.01) {
      const sh = ctx.createWaveShaper();
      const n = 512;
      const curve = new Float32Array(n);
      const k = 1 + p.drive * 40;
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * 2 - 1;
        curve[i] = Math.tanh(x * k) / Math.tanh(k);
      }
      sh.curve = curve;
      const trim = ctx.createGain();
      trim.gain.value = 0.8;
      g.connect(sh);
      sh.connect(trim);
      out = trim;
    }

    osc.connect(g);
    out.connect(dest);

    // щелчок атаки
    if (p.click > 0.01) {
      const nz = noiseSource(ctx);
      const hp = ctx.createBiquadFilter();
      hp.type = "highpass";
      hp.frequency.value = 1200;
      const ng = ctx.createGain();
      percEnv(ng.gain, time, note.vel * p.click * 0.7, 0.02, 0.0005);
      nz.connect(hp);
      hp.connect(ng);
      ng.connect(dest);
      nz.start(time);
      nz.stop(time + 0.06);
    }

    osc.start(time);
    const stopAt = time + p.decay + 0.1;
    osc.stop(stopAt);
    return { stopAt, release() {} };
  }

  function triggerSnare(ctx, dest, p, note, time) {
    const semis = note.key - 60;
    const tune = p.tune * Math.pow(2, semis / 12);

    // тоновая часть
    const o1 = ctx.createOscillator();
    o1.type = "triangle";
    o1.frequency.setValueAtTime(tune * 1.6, time);
    o1.frequency.exponentialRampToValueAtTime(tune, time + 0.03);
    const o2 = ctx.createOscillator();
    o2.type = "triangle";
    o2.frequency.value = tune * 1.48;

    const tg = ctx.createGain();
    percEnv(tg.gain, time, note.vel * (1 - p.snap * 0.55), p.decay * 0.6, 0.001);
    o1.connect(tg);
    o2.connect(tg);
    tg.connect(dest);

    // шумовая часть
    const nz = noiseSource(ctx);
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = p.tone;
    bp.Q.value = 0.7;
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 400;
    const ng = ctx.createGain();
    percEnv(ng.gain, time, note.vel * (0.4 + p.snap * 0.8), p.decay, 0.001);

    nz.connect(bp);
    bp.connect(hp);
    hp.connect(ng);
    ng.connect(dest);

    o1.start(time); o2.start(time); nz.start(time);
    const stopAt = time + p.decay + 0.1;
    o1.stop(stopAt); o2.stop(stopAt); nz.stop(stopAt);
    return { stopAt, release() {} };
  }

  function triggerClap(ctx, dest, p, note, time) {
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = p.tone;
    bp.Q.value = 1.4;
    const out = ctx.createGain();
    out.gain.value = 1;
    bp.connect(out);
    out.connect(dest);

    const gap = p.spread / 1000;
    const sources = [];

    // три коротких всплеска + хвост
    for (let i = 0; i < 3; i++) {
      const nz = noiseSource(ctx);
      const g = ctx.createGain();
      const t = time + i * gap;
      percEnv(g.gain, t, note.vel * (0.85 - i * 0.15), 0.02, 0.0005);
      nz.connect(g);
      g.connect(bp);
      nz.start(t);
      nz.stop(t + 0.05);
      sources.push(nz);
    }
    const tail = noiseSource(ctx);
    const tg = ctx.createGain();
    const tt = time + 2 * gap;
    percEnv(tg.gain, tt, note.vel * 0.75, p.decay, 0.002);
    tail.connect(tg);
    tg.connect(bp);
    tail.start(tt);
    const stopAt = tt + p.decay + 0.1;
    tail.stop(stopAt);

    return { stopAt, release() {} };
  }

  function triggerHat(ctx, dest, p, note, time) {
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = p.tone;
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = p.tone * 1.4;
    bp.Q.value = 0.9;

    const g = ctx.createGain();
    percEnv(g.gain, time, note.vel * 0.7, p.decay, 0.0006);
    hp.connect(bp);
    bp.connect(g);
    g.connect(dest);

    const started = [];

    // металлическая составляющая — 6 прямоугольников (по мотивам 808)
    if (p.metal > 0.01) {
      const ratios = [1, 1.342, 1.2312, 1.6532, 1.9523, 2.1523];
      const base = 320 * Math.pow(2, (note.key - 60) / 12);
      for (const r of ratios) {
        const o = ctx.createOscillator();
        o.type = "square";
        o.frequency.value = base * r;
        const og = ctx.createGain();
        og.gain.value = (p.metal * 0.5) / ratios.length;
        o.connect(og);
        og.connect(hp);
        o.start(time);
        started.push(o);
      }
    }
    const nz = noiseSource(ctx);
    const ng = ctx.createGain();
    ng.gain.value = 0.5;
    nz.connect(ng);
    ng.connect(hp);
    nz.start(time);
    started.push(nz);

    const stopAt = time + p.decay + 0.08;
    stopLater(ctx, started, stopAt);
    return { stopAt, release() {} };
  }

  function triggerTom(ctx, dest, p, note, time) {
    const base = p.tune * Math.pow(2, (note.key - 60) / 12);
    const o = ctx.createOscillator();
    o.type = "sine";
    o.frequency.setValueAtTime(base * (1 + p.bend * 1.4), time);
    o.frequency.exponentialRampToValueAtTime(base, time + 0.06 + p.bend * 0.1);

    const g = ctx.createGain();
    percEnv(g.gain, time, note.vel, p.decay, 0.002);
    o.connect(g);
    g.connect(dest);

    const nz = noiseSource(ctx);
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = base * 3;
    const ng = ctx.createGain();
    percEnv(ng.gain, time, note.vel * 0.18, 0.05, 0.001);
    nz.connect(bp); bp.connect(ng); ng.connect(dest);
    nz.start(time); nz.stop(time + 0.1);

    o.start(time);
    const stopAt = time + p.decay + 0.1;
    o.stop(stopAt);
    return { stopAt, release() {} };
  }

  function triggerCymbal(ctx, dest, p, note, time) {
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = p.tone;
    const g = ctx.createGain();
    percEnv(g.gain, time, note.vel * 0.5, p.decay, 0.004);
    hp.connect(g);
    g.connect(dest);

    const started = [];
    const ratios = [1, 1.41, 1.79, 2.21, 2.73, 3.31];
    const base = 420 * Math.pow(2, (note.key - 60) / 12);
    for (const r of ratios) {
      const o = ctx.createOscillator();
      o.type = "square";
      o.frequency.value = base * r;
      const og = ctx.createGain();
      og.gain.value = 0.12;
      o.connect(og);
      og.connect(hp);
      o.start(time);
      started.push(o);
    }
    const nz = noiseSource(ctx);
    const ng = ctx.createGain();
    ng.gain.value = 0.55;
    nz.connect(ng);
    ng.connect(hp);
    nz.start(time);
    started.push(nz);

    const stopAt = time + p.decay + 0.1;
    stopLater(ctx, started, stopAt);
    return { stopAt, release() {} };
  }

  function triggerRim(ctx, dest, p, note, time) {
    const base = p.tune * Math.pow(2, (note.key - 60) / 12);
    const o = ctx.createOscillator();
    o.type = "square";
    o.frequency.value = base;
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = base * 1.5;
    bp.Q.value = 3;
    const g = ctx.createGain();
    percEnv(g.gain, time, note.vel * 0.8, p.decay, 0.0005);
    o.connect(bp); bp.connect(g); g.connect(dest);
    o.start(time);
    const stopAt = time + p.decay + 0.05;
    o.stop(stopAt);
    return { stopAt, release() {} };
  }

  /* ---------------- Синтезатор ---------------- */

  function triggerSynth(ctx, dest, p, note, time) {
    const freq = midiToFreq(note.key);

    const amp = ctx.createGain();
    amp.gain.value = EPS;

    const filt = ctx.createBiquadFilter();
    filt.type = p.fType;
    filt.Q.value = p.res;

    const mixer = ctx.createGain();
    mixer.connect(filt);
    filt.connect(amp);
    amp.connect(dest);

    const specs = [
      { wave: p.w1, coarse: 0, fine: 0, lvl: p.m1 },
      { wave: p.w2, coarse: p.c2, fine: p.f2, lvl: p.m2 },
      { wave: p.w3, coarse: p.c3, fine: p.f3, lvl: p.m3 }
    ];
    const total = Math.max(0.001, specs.reduce((s, o) => s + o.lvl, 0));
    const uni = Math.max(1, Math.round(p.uni));
    const oscs = [];

    for (const spec of specs) {
      if (spec.lvl <= 0.001) continue;
      for (let u = 0; u < uni; u++) {
        const o = ctx.createOscillator();
        o.type = spec.wave;
        o.frequency.value = freq * Math.pow(2, spec.coarse / 12);
        const spreadCents = uni > 1 ? (u - (uni - 1) / 2) * (p.spread / (uni - 1 || 1)) * 2 : 0;
        o.detune.value = spec.fine + spreadCents;
        const g = ctx.createGain();
        g.gain.value = (spec.lvl / total) * (0.85 / uni);
        o.connect(g);
        g.connect(mixer);
        oscs.push(o);
      }
    }

    // огибающая фильтра
    const envOct = p.fEnv * 5;
    const peakHz = clamp(p.cutoff * Math.pow(2, envOct), 30, 20000);
    filt.frequency.setValueAtTime(clamp(p.cutoff, 30, 20000), time);
    if (p.fEnv > 0.001) {
      filt.frequency.exponentialRampToValueAtTime(peakHz, time + p.fa);
      filt.frequency.exponentialRampToValueAtTime(clamp(p.cutoff, 30, 20000), time + p.fa + p.fd);
    }

    const releaseTime = note.dur ? time + note.dur : null;
    adsrEnv(amp.gain, time, note.vel, p.a, p.d, p.s, releaseTime, p.r);

    for (const o of oscs) o.start(time);

    let stopAt = releaseTime !== null ? releaseTime + p.r + 0.05 : time + 30;
    if (releaseTime !== null) stopLater(ctx, oscs, stopAt);

    return {
      stopAt,
      release(t) {
        const rt = Math.max(t, time + 0.005);
        if (amp.gain.cancelAndHoldAtTime) amp.gain.cancelAndHoldAtTime(rt);
        else amp.gain.cancelScheduledValues(rt);
        amp.gain.exponentialRampToValueAtTime(EPS, rt + p.r);
        stopAt = rt + p.r + 0.05;
        stopLater(ctx, oscs, stopAt);
      }
    };
  }

  /* ---------------- Сэмплер ---------------- */

  function triggerSampler(ctx, dest, p, note, time, channel) {
    const buffer = channel && channel._buffer;
    if (!buffer) return { stopAt: time, release() {} };

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.playbackRate.value = Math.pow(2, (note.key - p.root) / 12);
    src.loop = !!p.loop;

    const dur = buffer.duration;
    const offset = clamp(p.start, 0, 0.99) * dur;
    const end = clamp(p.end, 0.01, 1) * dur;
    const playLen = Math.max(0.01, (end - offset)) / src.playbackRate.value;

    if (p.loop) {
      src.loopStart = offset;
      src.loopEnd = end;
    }

    const amp = ctx.createGain();
    amp.gain.value = EPS;
    src.connect(amp);
    amp.connect(dest);

    const releaseTime = note.dur ? time + note.dur : null;
    adsrEnv(amp.gain, time, note.vel, p.a, p.d, p.s, releaseTime, p.r);

    src.start(time, offset);
    let stopAt = releaseTime !== null
      ? Math.min(releaseTime + p.r + 0.05, p.loop ? Infinity : time + playLen + 0.05)
      : time + playLen;
    if (stopAt !== Infinity) src.stop(stopAt);

    return {
      stopAt,
      release(t) {
        const rt = Math.max(t, time + 0.005);
        if (amp.gain.cancelAndHoldAtTime) amp.gain.cancelAndHoldAtTime(rt);
        else amp.gain.cancelScheduledValues(rt);
        amp.gain.exponentialRampToValueAtTime(EPS, rt + p.r);
        try { src.stop(rt + p.r + 0.05); } catch (e) {}
      }
    };
  }

  const triggers = {
    kick: triggerKick,
    snare: triggerSnare,
    clap: triggerClap,
    hat: triggerHat,
    tom: triggerTom,
    cymbal: triggerCymbal,
    rim: triggerRim,
    synth: triggerSynth,
    sampler: triggerSampler
  };

  /**
   * Воспроизвести ноту канала.
   * @param ctx     AudioContext (live или offline)
   * @param dest    узел назначения (вход канала в микшере)
   * @param channel объект канала проекта
   * @param note    { key, vel, dur? } — dur в секундах
   * @param time    абсолютное время контекста
   */
  function trigger(ctx, dest, channel, note, time) {
    const fn = triggers[channel.type];
    if (!fn) return null;
    const n = {
      key: note.key === undefined ? channel.key || 60 : note.key,
      vel: note.vel === undefined ? 0.8 : note.vel,
      dur: note.dur
    };
    try {
      return fn(ctx, dest, channel.params, n, Math.max(time, ctx.currentTime), channel);
    } catch (e) {
      console.warn("Ошибка триггера", channel.type, e);
      return null;
    }
  }

  /* ---------- Метроном ---------- */

  function metronome(ctx, dest, time, accent) {
    const o = ctx.createOscillator();
    o.type = "square";
    o.frequency.value = accent ? 1600 : 1050;
    const g = ctx.createGain();
    percEnv(g.gain, time, accent ? 0.32 : 0.18, 0.04, 0.0005);
    o.connect(g);
    g.connect(dest);
    o.start(time);
    o.stop(time + 0.08);
  }

  CS.Instruments = { defs, defaultParams, paramSpec, trigger, metronome, dbGain, noiseBuffer };

})(window.CS);
