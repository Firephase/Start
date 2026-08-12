"use strict";

/* ============================================================
   Citrus Studio — Channel Rack (степ-секвенсор)
   Шаг = нота в текущем паттерне на позиции шага.
   Те же ноты редактируются в Piano Roll.
   ============================================================ */

(function (CS) {

  const { $, el, popupMenu, prompt, confirm } = CS.util;
  const { Project, Engine } = CS;

  const Rack = {

    rows: [],          // [{ channel, stepEls: [], el }]
    _curStep: -1,

    init() {
      this.list = $("#rack-list");

      $("#rack-add").addEventListener("click", (e) => {
        const r = e.currentTarget.getBoundingClientRect();
        popupMenu(r.left, r.bottom + 4, CS.BrowserPanel.addMenuItems());
      });

      $("#rack-length").addEventListener("change", (e) => {
        const pat = Project.currentPattern();
        if (!pat) return;
        Project.snapshot();
        Project.setPatternLength(pat.id, parseInt(e.target.value, 10));
      });

      CS.bus.on("project:loaded", () => this.render());
      CS.bus.on("channels:changed", () => this.render());
      CS.bus.on("patterns:changed", () => this.render());
      CS.bus.on("pattern:changed", () => this.render());
      CS.bus.on("pattern:resized", () => this.render());
      CS.bus.on("notes:changed", (chId) => {
        if (chId) this.updateRow(chId);
        else this.updateAll();
      });
      CS.bus.on("channels:mix", () => this.updateKnobs());
    },

    /* ---------------- Отрисовка ---------------- */

    render() {
      if (!this.list) return;
      const pat = Project.currentPattern();
      const len = pat ? pat.length : 16;
      $("#rack-length").value = String(len);

      this.list.innerHTML = "";
      this.rows = [];
      this._curStep = -1;

      // шапка с номерами долей
      const header = el("div", { class: "rack-row rack-header" });
      header.appendChild(el("div", { class: "rack-ctrl-head", text: "Каналы" }));
      const hsteps = el("div", { class: "rack-steps" });
      for (let i = 0; i < len; i++) {
        hsteps.appendChild(el("div", {
          class: "rack-step-num" + (i % 4 === 0 ? " beat" : ""),
          text: i % 4 === 0 ? String(i / 4 + 1) : ""
        }));
      }
      header.appendChild(hsteps);
      this.list.appendChild(header);

      for (const ch of Project.state.channels) {
        this.list.appendChild(this.renderRow(ch, len, pat));
      }

      if (!Project.state.channels.length) {
        this.list.appendChild(el("div", {
          class: "rack-empty",
          text: "Каналов нет. Нажми «+ Канал» или выбери инструмент в браузере слева."
        }));
      }
    },

    renderRow(ch, len, pat) {
      const row = el("div", { class: "rack-row" });

      /* --- левая часть: управление каналом --- */
      const ctrl = el("div", { class: "rack-ctrl" });

      const led = el("button", {
        class: "ch-led" + (ch.mute ? " muted" : ""),
        style: `--ch-color:${ch.color}`,
        title: "Вкл/выкл канал (ПКМ — соло)",
        onclick: () => {
          ch.mute = !ch.mute;
          led.classList.toggle("muted", ch.mute);
        },
        oncontextmenu: (e) => {
          e.preventDefault();
          const wasSolo = ch.solo;
          for (const c of Project.state.channels) c.solo = false;
          ch.solo = !wasSolo;
          this.updateSolo();
        }
      });
      if (ch.solo) led.classList.add("solo");

      const name = el("button", {
        class: "ch-name",
        text: ch.name,
        title: "Клик — настройки, ПКМ — меню",
        onclick: () => {
          CS.Inspector.showChannel(ch.id);
          CS.selectChannel(ch.id);
        },
        oncontextmenu: (e) => { e.preventDefault(); this.channelMenu(ch, e.clientX, e.clientY); }
      });

      const piano = el("button", {
        class: "ch-piano", text: "🎹", title: "Открыть Piano Roll",
        onclick: () => {
          CS.selectChannel(ch.id);
          CS.showView("piano");
        }
      });

      const volKnob = new CS.Knob({
        label: "", min: 0, max: 1.25, def: 0.8, value: ch.vol, size: 22, color: ch.color,
        format: (v) => Math.round(v * 100) + "%",
        onChange: (v) => { ch.vol = v; CS.bus.emit("channels:mix", ch.id); }
      });
      volKnob.el.classList.add("mini");
      volKnob.el.title = "Громкость";

      const panKnob = new CS.Knob({
        label: "", min: -1, max: 1, def: 0, value: ch.pan, size: 22, color: "#8fa3b8",
        format: (v) => (Math.abs(v) < 0.02 ? "C" : (v < 0 ? "L" : "R") + Math.round(Math.abs(v) * 100)),
        onChange: (v) => { ch.pan = v; CS.bus.emit("channels:mix", ch.id); }
      });
      panKnob.el.classList.add("mini");
      panKnob.el.title = "Панорама";

      const insBtn = el("button", {
        class: "ch-insert", text: ch.insert === 0 ? "M" : String(ch.insert),
        title: "Инсерт микшера",
        onclick: () => { CS.Inspector.showInsert(ch.insert); CS.showView("mixer"); }
      });

      ctrl.appendChild(led);
      ctrl.appendChild(name);
      ctrl.appendChild(piano);
      ctrl.appendChild(volKnob.el);
      ctrl.appendChild(panKnob.el);
      ctrl.appendChild(insBtn);
      row.appendChild(ctrl);

      /* --- правая часть: шаги --- */
      const stepsWrap = el("div", { class: "rack-steps" });
      const stepEls = [];
      const notes = pat ? Project.notes(pat.id, ch.id) : [];

      for (let i = 0; i < len; i++) {
        const stepEl = el("div", {
          class: "step" + (i % 4 === 0 ? " beat" : ""),
          style: `--ch-color:${ch.color}`,
          dataset: { step: i }
        });
        stepEls.push(stepEl);
        stepsWrap.appendChild(stepEl);
      }

      row.appendChild(stepsWrap);

      const rowObj = { channel: ch, stepEls, el: row, volKnob, panKnob, led };
      this.rows.push(rowObj);
      this.paintRow(rowObj, notes);
      this.bindSteps(rowObj, stepsWrap);
      return row;
    },

    /* ---------------- Взаимодействие ---------------- */

    bindSteps(rowObj, wrap) {
      const ch = rowObj.channel;
      let painting = null;   // true — ставим, false — стираем

      const stepFromEvent = (e) => {
        const t = document.elementFromPoint(e.clientX, e.clientY);
        if (!t || !t.classList.contains("step")) return -1;
        if (!wrap.contains(t)) return -1;
        return parseInt(t.dataset.step, 10);
      };

      const apply = (step) => {
        if (step < 0) return;
        const pat = Project.currentPattern();
        if (!pat) return;
        const notes = Project.notes(pat.id, ch.id);
        const has = notes.some((n) => Math.floor(n.t) === step);
        if (painting && !has) {
          notes.push({ t: step, dur: 1, key: ch.key, vel: 0.85 });
          Engine.preview(ch, ch.key, 0.3);
        } else if (!painting && has) {
          const kept = notes.filter((n) => Math.floor(n.t) !== step);
          pat.notes[ch.id] = kept;
        } else {
          return;
        }
        this.updateRow(ch.id);
        CS.bus.emit("notes:edited", ch.id);
      };

      wrap.addEventListener("mousedown", (e) => {
        const step = stepFromEvent(e);
        if (step < 0) return;
        e.preventDefault();
        Project.snapshot();
        const pat = Project.currentPattern();
        const notes = pat ? Project.notes(pat.id, ch.id) : [];
        const has = notes.some((n) => Math.floor(n.t) === step);
        painting = e.button === 2 ? false : !has;
        apply(step);

        const move = (ev) => apply(stepFromEvent(ev));
        const up = () => {
          window.removeEventListener("mousemove", move);
          window.removeEventListener("mouseup", up);
          painting = null;
        };
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
      });

      wrap.addEventListener("contextmenu", (e) => e.preventDefault());
    },

    channelMenu(ch, x, y) {
      const pat = Project.currentPattern();
      popupMenu(x, y, [
        { label: "Настройки инструмента", action: () => { CS.Inspector.showChannel(ch.id); CS.selectChannel(ch.id); } },
        { label: "Открыть Piano Roll", action: () => { CS.selectChannel(ch.id); CS.showView("piano"); } },
        "-",
        { label: "Переименовать", action: () => prompt("Имя канала", "Название", ch.name, (v) => {
            Project.snapshot(); ch.name = v || ch.name; CS.bus.emit("channels:changed");
          }) },
        { label: "Клонировать", action: () => { Project.snapshot(); Project.cloneChannel(ch.id); } },
        { label: "Выше", action: () => { Project.snapshot(); Project.moveChannel(ch.id, -1); } },
        { label: "Ниже", action: () => { Project.snapshot(); Project.moveChannel(ch.id, 1); } },
        "-",
        { label: "Заполнить каждые 2", action: () => this.fill(ch, 2) },
        { label: "Заполнить каждые 4", action: () => this.fill(ch, 4) },
        { label: "Случайно", action: () => this.randomFill(ch) },
        { label: "Очистить шаги", action: () => {
            Project.snapshot();
            if (pat) pat.notes[ch.id] = [];
            this.updateRow(ch.id);
            CS.bus.emit("notes:edited", ch.id);
          } },
        "-",
        { label: "Удалить канал", danger: true, action: () => confirm("Удалить канал", `Удалить «${ch.name}» вместе с нотами?`, () => {
            Project.snapshot();
            Project.removeChannel(ch.id);
          }) }
      ]);
    },

    fill(ch, every) {
      const pat = Project.currentPattern();
      if (!pat) return;
      Project.snapshot();
      const notes = [];
      for (let i = 0; i < pat.length; i += every) notes.push({ t: i, dur: 1, key: ch.key, vel: 0.85 });
      pat.notes[ch.id] = notes;
      this.updateRow(ch.id);
      CS.bus.emit("notes:edited", ch.id);
    },

    randomFill(ch) {
      const pat = Project.currentPattern();
      if (!pat) return;
      Project.snapshot();
      const notes = [];
      for (let i = 0; i < pat.length; i++) {
        if (Math.random() < 0.28) notes.push({ t: i, dur: 1, key: ch.key, vel: 0.6 + Math.random() * 0.4 });
      }
      pat.notes[ch.id] = notes;
      this.updateRow(ch.id);
      CS.bus.emit("notes:edited", ch.id);
    },

    /* ---------------- Обновления ---------------- */

    paintRow(rowObj, notes) {
      const ch = rowObj.channel;
      const map = new Map();
      for (const n of notes) {
        const s = Math.floor(n.t);
        if (s < 0 || s >= rowObj.stepEls.length) continue;
        const prev = map.get(s);
        if (!prev || n.vel > prev.vel) map.set(s, n);
      }
      rowObj.stepEls.forEach((elm, i) => {
        const n = map.get(i);
        if (n) {
          elm.classList.add("on");
          elm.classList.toggle("off-key", n.key !== ch.key);
          elm.style.setProperty("--vel", String(0.45 + n.vel * 0.55));
        } else {
          elm.classList.remove("on", "off-key");
        }
      });
    },

    updateRow(chId) {
      const rowObj = this.rows.find((r) => r.channel.id === chId);
      const pat = Project.currentPattern();
      if (!rowObj || !pat) return;
      this.paintRow(rowObj, Project.notes(pat.id, chId));
    },

    updateAll() {
      const pat = Project.currentPattern();
      if (!pat) return;
      for (const r of this.rows) this.paintRow(r, Project.notes(pat.id, r.channel.id));
    },

    updateKnobs() {
      for (const r of this.rows) {
        r.volKnob.setValue(r.channel.vol);
        r.panKnob.setValue(r.channel.pan);
      }
    },

    updateSolo() {
      for (const r of this.rows) {
        r.led.classList.toggle("solo", !!r.channel.solo);
        r.led.classList.toggle("muted", !!r.channel.mute);
      }
    },

    /** Подсветка текущего шага при воспроизведении. */
    setStep(step) {
      if (step === this._curStep) return;
      for (const r of this.rows) {
        if (this._curStep >= 0 && r.stepEls[this._curStep]) r.stepEls[this._curStep].classList.remove("playing");
        if (step >= 0 && r.stepEls[step]) r.stepEls[step].classList.add("playing");
      }
      this._curStep = step;
    }
  };

  CS.Rack = Rack;

})(window.CS);
