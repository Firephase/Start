"use strict";

/* ============================================================
   Citrus Studio — сборка приложения:
   транспорт, вкладки, горячие клавиши, цикл отрисовки
   ============================================================ */

(function (CS) {

  const { $, $$, el, clamp, noteName, prompt, confirm, modal, closeModal, downloadBlob } = CS.util;
  const { Project, Engine, Exporter } = CS;

  let currentView = "rack";
  let selectedChannelId = null;
  let octave = 4;                    // база для набора с клавиатуры (C5 = 60)
  const pressedKeys = new Map();

  /* ============================================================
     Публичные помощники
     ============================================================ */

  CS.setStatus = (text) => { $("#status-text").textContent = text; };

  CS.selectChannel = (id, silent) => {
    selectedChannelId = id;
    if (!silent) CS.bus.emit("channel:selected", id);
  };

  CS.selectedChannel = () => Project.channel(selectedChannelId) || Project.state.channels[0] || null;

  CS.showView = (name) => {
    currentView = name;
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
    $$("#tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
    if (name === "piano") { CS.PianoRoll.syncChannels(); CS.PianoRoll.draw(); }
    if (name === "playlist") CS.Playlist.draw();
    if (name === "mixer") CS.Mixer.render();
  };

  CS.loadSampleInto = (channel, file, done) => {
    const reader = new FileReader();
    reader.onload = () => {
      const ctx = Engine.ensureContext();
      ctx.decodeAudioData(reader.result,
        (buffer) => {
          channel._buffer = buffer;
          channel._sampleName = file.name;
          CS.setStatus(`Сэмпл «${file.name}» загружен (${buffer.duration.toFixed(2)} с)`);
          done && done();
        },
        () => CS.setStatus("Не удалось декодировать аудиофайл")
      );
    };
    reader.readAsArrayBuffer(file);
  };

  /* ============================================================
     Транспорт
     ============================================================ */

  function initTransport() {
    $("#btn-play").addEventListener("click", () => Engine.toggle());
    $("#btn-stop").addEventListener("click", () => Engine.stop());
    $("#btn-rec").addEventListener("click", () => {
      Engine.recording = !Engine.recording;
      $("#btn-rec").classList.toggle("on", Engine.recording);
      CS.setStatus(Engine.recording
        ? "Запись включена: играй на клавиатуре во время проигрывания"
        : "Запись выключена");
    });

    $("#mode-pat").addEventListener("click", () => Engine.setMode("pat"));
    $("#mode-song").addEventListener("click", () => Engine.setMode("song"));

    CS.bus.on("transport:play", () => $("#btn-play").classList.add("on"));
    CS.bus.on("transport:pause", () => $("#btn-play").classList.remove("on"));
    CS.bus.on("transport:stop", () => {
      $("#btn-play").classList.remove("on");
      CS.Rack.setStep(-1);
      redrawActive();
    });
    CS.bus.on("transport:mode", (mode) => {
      $("#mode-pat").classList.toggle("active", mode === "pat");
      $("#mode-song").classList.toggle("active", mode === "song");
    });
    CS.bus.on("transport:seek", () => redrawActive());

    /* --- поле темпа --- */
    const field = $("#tempo-field");
    const setBpm = (v) => {
      Project.state.bpm = clamp(Math.round(v * 10) / 10, 20, 300);
      $("#tempo-value").textContent = Project.state.bpm.toFixed(1);
    };
    field.addEventListener("mousedown", (e) => {
      const startY = e.clientY;
      const start = Project.state.bpm;
      const move = (ev) => setBpm(start + (startY - ev.clientY) * (ev.shiftKey ? 0.1 : 0.5));
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
      e.preventDefault();
    });
    field.addEventListener("wheel", (e) => {
      setBpm(Project.state.bpm + (e.deltaY < 0 ? 1 : -1) * (e.shiftKey ? 0.1 : 1));
      e.preventDefault();
    }, { passive: false });
    field.addEventListener("dblclick", () => {
      prompt("Темп", "BPM", String(Project.state.bpm), (v) => {
        const n = parseFloat(v.replace(",", "."));
        if (!isNaN(n)) setBpm(n);
      });
    });
  }

  /* ============================================================
     Ручки в тулбаре: свинг, мастер, метроном
     ============================================================ */

  function initMasterKnobs() {
    const host = $("#master-knobs");

    const swing = new CS.Knob({
      label: "Свинг", min: 0, max: 0.7, def: 0, value: Project.state.swing, size: 30,
      format: (v) => Math.round(v * 100) + "%",
      onChange: (v) => { Project.state.swing = v; }
    });

    const master = new CS.Knob({
      label: "Мастер", min: 0, max: 1.25, def: 0.8, value: Project.state.masterVol, size: 30,
      color: "#7de07d",
      format: (v) => Math.round(v * 100) + "%",
      onChange: (v) => { Project.state.masterVol = v; CS.bus.emit("mixer:changed"); }
    });

    const metro = el("button", {
      class: "tb-btn metro" + (Project.state.metronome ? " on" : ""),
      text: "🕭", title: "Метроном",
      onclick: () => {
        Project.state.metronome = !Project.state.metronome;
        metro.classList.toggle("on", Project.state.metronome);
      }
    });

    host.innerHTML = "";
    host.appendChild(swing.el);
    host.appendChild(master.el);
    host.appendChild(metro);

    CS.bus.on("project:loaded", () => {
      swing.setValue(Project.state.swing);
      master.setValue(Project.state.masterVol);
      metro.classList.toggle("on", !!Project.state.metronome);
      $("#tempo-value").textContent = Project.state.bpm.toFixed(1);
    });
    CS.bus.on("mixer:changed", () => master.setValue(Project.state.masterVol));
  }

  /* ============================================================
     Паттерны в тулбаре
     ============================================================ */

  function initPatternPicker() {
    const sel = $("#pattern-select");

    const sync = () => {
      sel.innerHTML = "";
      for (const p of Project.state.patterns) {
        sel.appendChild(el("option", { value: p.id, text: p.name, selected: p.id === Project.state.currentPattern }));
      }
    };

    sel.addEventListener("change", () => Project.setCurrentPattern(sel.value));

    $("#btn-pat-add").addEventListener("click", () => {
      Project.snapshot();
      Project.addPattern();
    });
    $("#btn-pat-clone").addEventListener("click", () => {
      Project.snapshot();
      Project.clonePattern(Project.state.currentPattern);
    });
    $("#btn-pat-rename").addEventListener("click", () => {
      const pat = Project.currentPattern();
      if (!pat) return;
      prompt("Паттерн", "Название", pat.name, (v) => {
        pat.name = v || pat.name;
        CS.bus.emit("patterns:changed");
      });
    });
    $("#btn-pat-del").addEventListener("click", () => {
      const pat = Project.currentPattern();
      if (!pat) return;
      confirm("Удалить паттерн", `Удалить «${pat.name}» и его клипы из аранжировки?`, () => {
        Project.snapshot();
        Project.removePattern(pat.id);
      });
    });

    CS.bus.on("patterns:changed", sync);
    CS.bus.on("pattern:changed", sync);
    CS.bus.on("project:loaded", sync);
    sync();
  }

  /* ============================================================
     Файлы
     ============================================================ */

  function initFiles() {
    $("#btn-new").addEventListener("click", () => {
      confirm("Новый проект", "Текущий проект будет закрыт. Продолжить?", () => {
        const p = CS.emptyProject();
        Project.init(p);
        Project.addPattern("Паттерн 1", 16);
        CS.BrowserPanel.addPreset(CS.presets.drums[0]);
        Engine.rebuild();
        CS.setStatus("Создан новый проект");
      });
    });

    $("#btn-save").addEventListener("click", () => {
      prompt("Сохранить проект", "Имя файла", Project.state.name, (v) => {
        Project.state.name = v || "project";
        Project.save(Project.state.name);
        CS.setStatus("Проект сохранён: " + Project.state.name + ".citrus");
      });
    });

    $("#btn-load").addEventListener("click", () => $("#file-project").click());

    $("#file-project").addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (!f) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          Project.loadFromText(reader.result);
          Engine.rebuild();
          CS.setStatus("Загружен проект: " + f.name);
        } catch (err) {
          CS.setStatus("Ошибка загрузки: " + err.message);
        }
      };
      reader.readAsText(f);
      e.target.value = "";
    });

    $("#btn-export").addEventListener("click", showExportDialog);
  }

  function showExportDialog() {
    const modeSel = el("select", { class: "param-select" }, [
      el("option", { value: "song", text: "Вся песня (плейлист)" }),
      el("option", { value: "pattern", text: "Текущий паттерн" })
    ]);
    const repeats = el("input", { class: "modal-input", type: "number", value: "2", min: "1", max: "32" });
    const rate = el("select", { class: "param-select" }, [
      el("option", { value: "44100", text: "44100 Гц" }),
      el("option", { value: "48000", text: "48000 Гц" })
    ]);

    const body = el("div", {}, [
      el("label", { class: "modal-label", text: "Что рендерим" }), modeSel,
      el("label", { class: "modal-label", text: "Повторов (для паттерна)" }), repeats,
      el("label", { class: "modal-label", text: "Частота дискретизации" }), rate,
      el("div", { class: "modal-note", text: "Рендер офлайн — быстрее реального времени. Мьюты и соло учитываются." })
    ]);

    modal("Экспорт в WAV", body, [
      { label: "Отмена" },
      {
        label: "Рендер", accent: true, action: () => {
          const opts = {
            mode: modeSel.value,
            repeats: parseInt(repeats.value, 10) || 2,
            sampleRate: parseInt(rate.value, 10)
          };
          setTimeout(() => runExport(opts), 50);
        }
      }
    ]);
  }

  async function runExport(opts) {
    CS.setStatus("Рендер…");
    modal("Экспорт в WAV", el("div", { class: "modal-note", text: "Рендер идёт, подожди немного…" }), []);
    try {
      const blob = await Exporter.render(opts);
      closeModal();
      const name = (Project.state.name || "citrus") + (opts.mode === "pattern" ? "-pattern" : "") + ".wav";
      downloadBlob(blob, name);
      CS.setStatus("Готово: " + name + " (" + (blob.size / 1048576).toFixed(1) + " МБ)");
    } catch (err) {
      closeModal();
      CS.setStatus("Ошибка рендера: " + err.message);
      console.error(err);
    }
  }

  /* ============================================================
     Вкладки и горячие клавиши
     ============================================================ */

  function initTabs() {
    $$("#tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => CS.showView(tab.dataset.view));
    });
  }

  // Раскладка «печатной клавиатуры» как в FL: два ряда = две октавы
  const KEYMAP = {
    KeyZ: 0, KeyS: 1, KeyX: 2, KeyD: 3, KeyC: 4, KeyV: 5, KeyG: 6, KeyB: 7,
    KeyH: 8, KeyN: 9, KeyJ: 10, KeyM: 11, Comma: 12, KeyL: 13, Period: 14,
    KeyQ: 12, Digit2: 13, KeyW: 14, Digit3: 15, KeyE: 16, KeyR: 17, Digit5: 18,
    KeyT: 19, Digit6: 20, KeyY: 21, Digit7: 22, KeyU: 23, KeyI: 24, Digit9: 25, KeyO: 26
  };

  function initKeyboard() {
    window.addEventListener("keydown", (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "select" || tag === "textarea") return;

      // транспорт и окна
      if (e.code === "Space") { Engine.toggle(); e.preventDefault(); return; }
      if (e.code === "F5") { CS.showView("playlist"); e.preventDefault(); return; }
      if (e.code === "F6") { CS.showView("rack"); e.preventDefault(); return; }
      if (e.code === "F7") { CS.showView("piano"); e.preventDefault(); return; }
      if (e.code === "F9") { CS.showView("mixer"); e.preventDefault(); return; }
      if (e.code === "KeyL" && (e.ctrlKey || e.metaKey)) {
        Engine.setMode(Engine.mode === "pat" ? "song" : "pat");
        e.preventDefault();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyZ") {
        if (e.shiftKey ? Project.redo() : Project.undo()) {
          Engine.rebuild();
          CS.setStatus(e.shiftKey ? "Повтор действия" : "Отмена действия");
        }
        e.preventDefault();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyS") {
        Project.save(Project.state.name);
        CS.setStatus("Проект сохранён");
        e.preventDefault();
        return;
      }
      if (e.code === "Delete" || e.code === "Backspace") {
        if (currentView === "piano") { CS.PianoRoll.deleteSelection(); e.preventDefault(); }
        return;
      }
      if (e.code === "BracketLeft") { octave = clamp(octave - 1, 0, 8); CS.setStatus("Октава: C" + (octave + 1)); return; }
      if (e.code === "BracketRight") { octave = clamp(octave + 1, 0, 8); CS.setStatus("Октава: C" + (octave + 1)); return; }
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      // игра нотами
      if (!$("#chk-typing").checked) return;
      const offset = KEYMAP[e.code];
      if (offset === undefined || pressedKeys.has(e.code)) return;
      const ch = CS.selectedChannel();
      if (!ch) return;
      const key = clamp(octave * 12 + 12 + offset, 0, 127);
      Engine.noteOn(ch, key, 0.85);
      pressedKeys.set(e.code, key);
      if (Engine.recording && Engine.playing) recordNote(ch, key);
      e.preventDefault();
    });

    window.addEventListener("keyup", (e) => {
      const key = pressedKeys.get(e.code);
      if (key === undefined) return;
      const ch = CS.selectedChannel();
      if (ch) Engine.noteOff(ch, key);
      pressedKeys.delete(e.code);
    });
  }

  function recordNote(ch, key) {
    const pat = Project.currentPattern();
    if (!pat) return;
    let pos = Engine.positionSteps();
    if (Engine.mode === "song") pos = pos % pat.length;
    const snapped = Math.round(pos);
    const notes = Project.notes(pat.id, ch.id);
    notes.push({ t: clamp(snapped, 0, pat.length - 1), dur: 1, key, vel: 0.85 });
    CS.bus.emit("notes:changed", ch.id);
  }

  /* ============================================================
     Цикл отрисовки
     ============================================================ */

  const meterCanvas = () => $("#master-meter");
  let peakHold = 0;

  function drawMasterMeter() {
    const c = meterCanvas();
    const ctx = c.getContext("2d");
    const w = c.width, h = c.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#14171b";
    ctx.fillRect(0, 0, w, h);

    const level = Engine.ctx ? Engine.masterLevel() : 0;
    const db = level > 0 ? 20 * Math.log10(level) : -60;
    const t = clamp((db + 54) / 54, 0, 1);
    peakHold = Math.max(peakHold * 0.94, t);

    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, "#4fd07a");
    grad.addColorStop(0.75, "#e2d24a");
    grad.addColorStop(1, "#ff5f4d");
    ctx.fillStyle = grad;
    ctx.fillRect(2, 4, (w - 4) * t, h - 8);

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(2 + (w - 4) * peakHold, 4, 1.5, h - 8);

    // деления
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    for (let i = 1; i < 6; i++) ctx.fillRect(2 + ((w - 4) * i) / 6, 4, 1, h - 8);
  }

  function updateLcd(pos) {
    const step = Math.floor(pos);
    const bar = Math.floor(step / 16) + 1;
    const beat = Math.floor((step % 16) / 4) + 1;
    const tick = (step % 4) + 1;
    $("#lcd-time").textContent =
      String(bar).padStart(3, "0") + ":" + beat + ":" + String(tick).padStart(2, "0");
  }

  function redrawActive() {
    if (currentView === "piano") CS.PianoRoll.draw();
    else if (currentView === "playlist") CS.Playlist.draw();
  }

  function frame() {
    Engine.pumpCursor();
    const playing = Engine.playing;
    const pos = playing ? Engine.positionSteps() : (Engine._pausedStep || 0);

    updateLcd(pos);

    if (currentView === "rack") {
      const pat = Project.currentPattern();
      const len = pat ? pat.length : 16;
      CS.Rack.setStep(playing ? Math.floor(pos) % len : -1);
    } else if (playing) {
      redrawActive();
    }

    if (currentView === "mixer") CS.Mixer.updateMeters();
    drawMasterMeter();

    requestAnimationFrame(frame);
  }

  /* ============================================================
     Старт
     ============================================================ */

  function boot() {
    // проект: восстановление автосейва или демо
    let initial = null;
    const auto = Project.loadAutosave ? Project.loadAutosave() : null;
    if (auto && auto.channels && auto.channels.length) initial = auto;
    Project.init(initial || CS.demoProject());

    CS.BrowserPanel.init();
    CS.Rack.init();
    CS.PianoRoll.init();
    CS.Playlist.init();
    CS.Mixer.init();

    initTransport();
    initMasterKnobs();
    initPatternPicker();
    initFiles();
    initTabs();
    initKeyboard();

    // первичная отрисовка всех панелей
    CS.bus.emit("project:loaded", Project.state);
    CS.selectChannel(Project.state.channels[0] ? Project.state.channels[0].id : null);
    if (Project.state.channels[0]) CS.Inspector.showChannel(Project.state.channels[0].id);
    CS.showView("rack");

    // аудиоконтекст создаётся при первом действии пользователя
    const wake = () => {
      Engine.ensureContext();
      window.removeEventListener("pointerdown", wake);
      window.removeEventListener("keydown", wake);
    };
    window.addEventListener("pointerdown", wake);
    window.addEventListener("keydown", wake);

    // автосохранение
    setInterval(() => Project.autosave(), 20000);
    window.addEventListener("beforeunload", () => Project.autosave());

    CS.setStatus(initial
      ? "Восстановлен последний проект. Пробел — старт."
      : "Демо-проект загружен. Жми ▶ или Пробел, переключись в SONG для всей аранжировки.");

    requestAnimationFrame(frame);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

})(window.CS);
