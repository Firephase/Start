"use strict";

/* ============================================================
   Citrus Studio — эффекты микшера
   Каждый эффект: { type, input, output, update(params) }
   Обёртка dry/wet общая для всех.
   ============================================================ */

(function (CS) {

  const { clamp } = CS.util;

  /* ---------- Описания параметров (по ним строится UI) ---------- */

  const defs = {
    eq3: {
      name: "EQ 3",
      params: [
        { key: "low", label: "Низ", min: -18, max: 18, def: 0, unit: "дБ" },
        { key: "mid", label: "Серед", min: -18, max: 18, def: 0, unit: "дБ" },
        { key: "high", label: "Верх", min: -18, max: 18, def: 0, unit: "дБ" },
        { key: "midFreq", label: "Част", min: 200, max: 6000, def: 1200, curve: "log", unit: "Гц" }
      ]
    },
    filter: {
      name: "Фильтр",
      params: [
        { key: "mode", label: "Тип", type: "enum", options: ["lowpass", "highpass", "bandpass", "notch"], def: "lowpass" },
        { key: "cutoff", label: "Срез", min: 30, max: 18000, def: 3000, curve: "log", unit: "Гц" },
        { key: "q", label: "Рез", min: 0.1, max: 24, def: 1, curve: "log" }
      ]
    },
    dist: {
      name: "Дисторшн",
      params: [
        { key: "drive", label: "Драйв", min: 1, max: 100, def: 12, curve: "log" },
        { key: "tone", label: "Тон", min: 500, max: 16000, def: 8000, curve: "log", unit: "Гц" },
        { key: "mix", label: "Микс", min: 0, max: 1, def: 0.6 }
      ]
    },
    chorus: {
      name: "Хорус",
      params: [
        { key: "rate", label: "Скор", min: 0.05, max: 8, def: 0.8, curve: "log", unit: "Гц" },
        { key: "depth", label: "Глуб", min: 0, max: 12, def: 4, unit: "мс" },
        { key: "spread", label: "Стерео", min: 0, max: 1, def: 0.8 },
        { key: "mix", label: "Микс", min: 0, max: 1, def: 0.45 }
      ]
    },
    delay: {
      name: "Дилей",
      params: [
        { key: "time", label: "Время", min: 20, max: 1200, def: 340, curve: "log", unit: "мс" },
        { key: "feedback", label: "Фидбек", min: 0, max: 0.92, def: 0.38 },
        { key: "damp", label: "Демпф", min: 400, max: 16000, def: 4200, curve: "log", unit: "Гц" },
        { key: "pingpong", label: "Пинг-понг", type: "bool", def: true },
        { key: "mix", label: "Микс", min: 0, max: 1, def: 0.3 }
      ]
    },
    reverb: {
      name: "Реверб",
      params: [
        { key: "size", label: "Размер", min: 0.2, max: 6, def: 2.2, unit: "с" },
        { key: "damp", label: "Демпф", min: 800, max: 16000, def: 5200, curve: "log", unit: "Гц" },
        { key: "predelay", label: "Предзад", min: 0, max: 120, def: 18, unit: "мс" },
        { key: "mix", label: "Микс", min: 0, max: 1, def: 0.28 }
      ]
    },
    comp: {
      name: "Компрессор",
      params: [
        { key: "threshold", label: "Порог", min: -60, max: 0, def: -20, unit: "дБ" },
        { key: "ratio", label: "Ратио", min: 1, max: 20, def: 4 },
        { key: "attack", label: "Атака", min: 0.001, max: 0.3, def: 0.006, curve: "log", unit: "с" },
        { key: "release", label: "Релиз", min: 0.02, max: 1.2, def: 0.22, curve: "log", unit: "с" },
        { key: "makeup", label: "Гейн", min: 0, max: 18, def: 3, unit: "дБ" }
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

  /* ---------- Вспомогательное ---------- */

  const dbToGain = (db) => Math.pow(10, db / 20);

  function makeDistCurve(drive) {
    const n = 1024;
    const curve = new Float32Array(n);
    const k = drive;
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * 2 - 1;
      curve[i] = ((1 + k) * x) / (1 + k * Math.abs(x));
    }
    return curve;
  }

  function makeImpulse(ctx, seconds, damp) {
    const rate = ctx.sampleRate;
    const len = Math.max(1, Math.floor(seconds * rate));
    const buf = ctx.createBuffer(2, len, rate);
    // однополюсный фильтр по хвосту — имитация поглощения ВЧ
    const coef = clamp(damp / (rate / 2), 0.02, 0.99);
    for (let ch = 0; ch < 2; ch++) {
      const data = buf.getChannelData(ch);
      let last = 0;
      for (let i = 0; i < len; i++) {
        const t = i / len;
        const decay = Math.pow(1 - t, 2.6);
        const white = Math.random() * 2 - 1;
        last = last + coef * (white - last);
        data[i] = last * decay;
      }
      // ранние отражения
      for (let k = 0; k < 8; k++) {
        const pos = Math.floor((0.005 + Math.random() * 0.06) * rate);
        if (pos < len) data[pos] += (Math.random() * 2 - 1) * 0.5;
      }
    }
    return buf;
  }

  /* ============================================================
     Фабрика одного эффекта
     ============================================================ */

  function create(ctx, type, params) {
    const p = Object.assign(defaultParams(type), params || {});

    const input = ctx.createGain();
    const output = ctx.createGain();
    const dry = ctx.createGain();
    const wet = ctx.createGain();

    input.connect(dry);
    dry.connect(output);
    wet.connect(output);

    const fx = { type, input, output, params: p, ctx, _dry: dry, _wet: wet };

    const setMix = (m) => {
      const mix = m === undefined ? 1 : clamp(m, 0, 1);
      dry.gain.value = 1 - mix;
      wet.gain.value = mix;
    };

    switch (type) {

      case "eq3": {
        const low = ctx.createBiquadFilter();
        low.type = "lowshelf";
        low.frequency.value = 220;
        const mid = ctx.createBiquadFilter();
        mid.type = "peaking";
        mid.Q.value = 0.9;
        const high = ctx.createBiquadFilter();
        high.type = "highshelf";
        high.frequency.value = 4800;

        input.connect(low);
        low.connect(mid);
        mid.connect(high);
        high.connect(wet);
        dry.gain.value = 0;
        wet.gain.value = 1;

        fx.update = (np) => {
          Object.assign(p, np);
          low.gain.value = p.low;
          mid.gain.value = p.mid;
          mid.frequency.value = p.midFreq;
          high.gain.value = p.high;
        };
        break;
      }

      case "filter": {
        const f = ctx.createBiquadFilter();
        input.connect(f);
        f.connect(wet);
        dry.gain.value = 0;
        wet.gain.value = 1;
        fx.update = (np) => {
          Object.assign(p, np);
          f.type = p.mode;
          f.frequency.value = p.cutoff;
          f.Q.value = p.q;
        };
        break;
      }

      case "dist": {
        const pre = ctx.createGain();
        const shaper = ctx.createWaveShaper();
        shaper.oversample = "4x";
        const tone = ctx.createBiquadFilter();
        tone.type = "lowpass";
        const post = ctx.createGain();

        input.connect(pre);
        pre.connect(shaper);
        shaper.connect(tone);
        tone.connect(post);
        post.connect(wet);

        fx.update = (np) => {
          Object.assign(p, np);
          shaper.curve = makeDistCurve(p.drive);
          tone.frequency.value = p.tone;
          pre.gain.value = 1;
          post.gain.value = 1 / (1 + Math.log10(p.drive) * 0.6);
          setMix(p.mix);
        };
        break;
      }

      case "chorus": {
        const splitDelays = [];
        const lfos = [];
        const merger = ctx.createGain();
        const panL = ctx.createStereoPanner();
        const panR = ctx.createStereoPanner();
        const voices = 2;

        for (let i = 0; i < voices; i++) {
          const d = ctx.createDelay(0.08);
          d.delayTime.value = 0.018 + i * 0.007;
          const lfo = ctx.createOscillator();
          lfo.type = "sine";
          const depth = ctx.createGain();
          lfo.connect(depth);
          depth.connect(d.delayTime);
          lfo.start();
          input.connect(d);
          d.connect(i === 0 ? panL : panR);
          splitDelays.push({ d, depth });
          lfos.push(lfo);
        }
        panL.connect(merger);
        panR.connect(merger);
        merger.connect(wet);

        fx.update = (np) => {
          Object.assign(p, np);
          lfos.forEach((l, i) => { l.frequency.value = p.rate * (i === 0 ? 1 : 1.31); });
          splitDelays.forEach((s) => { s.depth.gain.value = (p.depth / 1000) * 0.5; });
          panL.pan.value = -p.spread;
          panR.pan.value = p.spread;
          setMix(p.mix);
        };
        fx.dispose = () => lfos.forEach((l) => { try { l.stop(); } catch (e) {} });
        break;
      }

      case "delay": {
        const dl = ctx.createDelay(2.5);
        const dr = ctx.createDelay(2.5);
        const fbL = ctx.createGain();
        const fbR = ctx.createGain();
        const dampL = ctx.createBiquadFilter();
        const dampR = ctx.createBiquadFilter();
        dampL.type = dampR.type = "lowpass";
        const pL = ctx.createStereoPanner();
        const pR = ctx.createStereoPanner();
        pL.pan.value = -0.75;
        pR.pan.value = 0.75;

        input.connect(dl);
        input.connect(dr);
        dl.connect(dampL);
        dr.connect(dampR);
        dampL.connect(pL);
        dampR.connect(pR);
        pL.connect(wet);
        pR.connect(wet);

        fx.update = (np) => {
          Object.assign(p, np);
          const t = p.time / 1000;
          dl.delayTime.value = t;
          dr.delayTime.value = p.pingpong ? t * 1.5 : t;
          dampL.frequency.value = p.damp;
          dampR.frequency.value = p.damp;
          fbL.gain.value = p.feedback;
          fbR.gain.value = p.feedback;
          setMix(p.mix);
        };

        // перекрёстная обратная связь (пинг-понг)
        dampL.connect(fbL);
        dampR.connect(fbR);
        fbL.connect(dr);
        fbR.connect(dl);
        break;
      }

      case "reverb": {
        const pre = ctx.createDelay(0.5);
        const conv = ctx.createConvolver();
        const damp = ctx.createBiquadFilter();
        damp.type = "lowpass";
        input.connect(pre);
        pre.connect(conv);
        conv.connect(damp);
        damp.connect(wet);

        let irKey = "";
        fx.update = (np) => {
          Object.assign(p, np);
          pre.delayTime.value = p.predelay / 1000;
          damp.frequency.value = p.damp;
          const key = p.size.toFixed(2) + "/" + Math.round(p.damp);
          if (key !== irKey) {
            irKey = key;
            conv.buffer = makeImpulse(ctx, p.size, p.damp);
          }
          setMix(p.mix);
        };
        break;
      }

      case "comp": {
        const c = ctx.createDynamicsCompressor();
        const makeup = ctx.createGain();
        input.connect(c);
        c.connect(makeup);
        makeup.connect(wet);
        dry.gain.value = 0;
        wet.gain.value = 1;
        fx.reduction = () => c.reduction;
        fx.update = (np) => {
          Object.assign(p, np);
          c.threshold.value = p.threshold;
          c.ratio.value = p.ratio;
          c.attack.value = p.attack;
          c.release.value = p.release;
          c.knee.value = 6;
          makeup.gain.value = dbToGain(p.makeup);
        };
        break;
      }

      default: {
        input.connect(wet);
        dry.gain.value = 0;
        wet.gain.value = 1;
        fx.update = () => {};
      }
    }

    fx.update(p);
    return fx;
  }

  /* ============================================================
     Цепочка эффектов инсерта
     ============================================================ */

  function buildChain(ctx, fxList) {
    const input = ctx.createGain();
    const output = ctx.createGain();
    const nodes = [];
    let last = input;

    for (const item of fxList || []) {
      if (item.enabled === false) continue;
      const fx = create(ctx, item.type, item.params);
      fx.source = item;                     // ссылка на объект из проекта
      last.connect(fx.input);
      last = fx.output;
      nodes.push(fx);
    }
    last.connect(output);
    return { input, output, nodes };
  }

  CS.Effects = { defs, create, buildChain, defaultParams, dbToGain, makeImpulse };

})(window.CS);
