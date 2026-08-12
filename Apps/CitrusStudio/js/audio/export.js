"use strict";

/* ============================================================
   Citrus Studio — офлайн-рендер в WAV
   Использует тот же граф и те же инструменты, что и живой движок.
   ============================================================ */

(function (CS) {

  const { Project, audio, Instruments } = CS;
  const TPS = audio.TICKS_PER_STEP;

  /* ---------- Кодирование WAV (16 бит PCM) ---------- */

  function encodeWAV(buffer) {
    const numCh = buffer.numberOfChannels;
    const len = buffer.length;
    const rate = buffer.sampleRate;
    const bytesPerSample = 2;
    const blockAlign = numCh * bytesPerSample;
    const dataSize = len * blockAlign;

    const ab = new ArrayBuffer(44 + dataSize);
    const view = new DataView(ab);

    const writeStr = (offset, s) => {
      for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
    };

    writeStr(0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);          // размер fmt-блока
    view.setUint16(20, 1, true);           // PCM
    view.setUint16(22, numCh, true);
    view.setUint32(24, rate, true);
    view.setUint32(28, rate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, dataSize, true);

    const channels = [];
    for (let c = 0; c < numCh; c++) channels.push(buffer.getChannelData(c));

    let offset = 44;
    for (let i = 0; i < len; i++) {
      for (let c = 0; c < numCh; c++) {
        let s = channels[c][i];
        s = s < -1 ? -1 : s > 1 ? 1 : s;
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        offset += 2;
      }
    }
    return new Blob([ab], { type: "audio/wav" });
  }

  /* ---------- Рендер ---------- */

  /**
   * @param opts { mode: "song"|"pattern", repeats, tail, sampleRate }
   * @returns Promise<Blob>
   */
  async function render(opts) {
    const o = Object.assign({ mode: "song", repeats: 2, tail: 2.5, sampleRate: 44100 }, opts || {});
    const state = Project.state;
    const stepDur = 60 / state.bpm / 4;
    const tickDur = stepDur / TPS;

    let lengthSteps;
    if (o.mode === "pattern") {
      const pat = Project.currentPattern();
      lengthSteps = (pat ? pat.length : 16) * Math.max(1, o.repeats);
    } else {
      lengthSteps = Project.songLength();
    }

    const seconds = lengthSteps * stepDur + o.tail;
    const frames = Math.ceil(seconds * o.sampleRate);

    const OfflineCtx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    const ctx = new OfflineCtx(2, frames, o.sampleRate);

    const graph = audio.buildGraph(ctx, state, { destination: ctx.destination });
    // громкости/панорамы фиксируем на старте
    audio.syncMix(graph, state);

    const totalTicks = lengthSteps * TPS;
    const patternMode = o.mode === "pattern" ? "pat" : "song";

    for (let tick = 0; tick < totalTicks; tick++) {
      const events = audio.collectEvents(state, tick, patternMode, []);
      if (!events.length) continue;
      const step = Math.floor(tick / TPS);
      const swingOffset = (step % 2 === 1) ? state.swing * 0.5 * stepDur : 0;
      const when = tick * tickDur + swingOffset + 0.02;

      for (const ev of events) {
        if (!Project.channelAudible(ev.channel)) continue;
        const node = audio.channelNode(graph, ev.channel);
        Instruments.trigger(ctx, node.gain, ev.channel, {
          key: ev.note.key,
          vel: ev.note.vel,
          dur: Math.max(0.02, (ev.note.dur || 1) * stepDur)
        }, when);
      }
    }

    const rendered = await ctx.startRendering();
    return encodeWAV(rendered);
  }

  CS.Exporter = { render, encodeWAV };

})(window.CS);
