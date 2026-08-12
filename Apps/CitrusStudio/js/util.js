"use strict";

/* ============================================================
   Citrus Studio — утилиты, виджеты, шина событий
   ============================================================ */

window.CS = window.CS || {};

(function (CS) {

  /* ---------------- DOM ---------------- */

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        const v = attrs[k];
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k === "html") node.innerHTML = v;
        else if (k === "style") node.setAttribute("style", v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (k === "dataset") for (const d in v) node.dataset[d] = v[d];
        else node.setAttribute(k, v);
      }
    }
    if (children) for (const c of [].concat(children)) if (c) node.appendChild(c);
    return node;
  }

  /* ---------------- Математика ---------------- */

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const round2 = (v) => Math.round(v * 100) / 100;

  // Логарифмическая шкала — для частот и времени
  const toLog = (v, lo, hi) => Math.log(v / lo) / Math.log(hi / lo);
  const fromLog = (t, lo, hi) => lo * Math.pow(hi / lo, t);

  let idCounter = 1;
  const uid = (prefix) => (prefix || "id") + "_" + (idCounter++) + "_" + Math.random().toString(36).slice(2, 7);

  /* ---------------- Ноты ---------------- */

  const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

  // MIDI 60 = C5 (нумерация октав как в FL Studio)
  const midiToFreq = (m) => 440 * Math.pow(2, (m - 69) / 12);
  const noteName = (m) => NOTE_NAMES[((m % 12) + 12) % 12] + Math.floor(m / 12);
  const isBlackKey = (m) => [1, 3, 6, 8, 10].indexOf(((m % 12) + 12) % 12) >= 0;

  /* ---------------- Разное ---------------- */

  function deepClone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: filename });
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  /* ---------------- Шина событий ---------------- */

  const listeners = new Map();

  const bus = {
    on(name, fn) {
      if (!listeners.has(name)) listeners.set(name, []);
      listeners.get(name).push(fn);
      return () => bus.off(name, fn);
    },
    off(name, fn) {
      const arr = listeners.get(name);
      if (!arr) return;
      const i = arr.indexOf(fn);
      if (i >= 0) arr.splice(i, 1);
    },
    emit(name, payload) {
      const arr = listeners.get(name);
      if (arr) for (const fn of arr.slice()) fn(payload);
    }
  };

  /* ---------------- Canvas с учётом DPI ---------------- */

  function fitCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width * dpr));
    const h = Math.max(1, Math.floor(rect.height * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w: rect.width, h: rect.height };
  }

  /* ============================================================
     Крутилка (knob) в духе FL: тянешь мышью вверх/вниз
     ============================================================ */

  class Knob {
    /**
     * @param {object} opts
     *   label     — подпись
     *   min, max  — диапазон
     *   value     — стартовое значение
     *   def       — значение по умолчанию (двойной клик)
     *   step      — шаг округления
     *   curve     — "lin" | "log"
     *   unit      — единицы для подписи
     *   size      — диаметр, px
     *   format    — функция форматирования значения
     *   onChange  — колбэк (value)
     */
    constructor(opts) {
      this.o = Object.assign(
        { label: "", min: 0, max: 1, value: 0.5, step: 0, curve: "lin", unit: "", size: 34, color: "#f0a03c" },
        opts
      );
      if (this.o.def === undefined) this.o.def = this.o.value;
      this.value = this.o.value;

      this.el = el("div", { class: "knob" });
      this.dial = el("div", { class: "knob-dial", style: `width:${this.o.size}px;height:${this.o.size}px` });
      this.canvas = el("canvas", { width: this.o.size * 2, height: this.o.size * 2 });
      this.canvas.style.width = this.o.size + "px";
      this.canvas.style.height = this.o.size + "px";
      this.dial.appendChild(this.canvas);

      this.labelEl = el("div", { class: "knob-label", text: this.o.label });
      this.valueEl = el("div", { class: "knob-value" });

      this.el.appendChild(this.labelEl);
      this.el.appendChild(this.dial);
      this.el.appendChild(this.valueEl);

      this._bindDrag();
      this.draw();
    }

    _norm(v) {
      const { min, max, curve } = this.o;
      if (curve === "log") return toLog(clamp(v, min, max), min, max);
      return (clamp(v, min, max) - min) / (max - min);
    }

    _denorm(t) {
      const { min, max, curve, step } = this.o;
      let v = curve === "log" ? fromLog(clamp(t, 0, 1), min, max) : min + clamp(t, 0, 1) * (max - min);
      if (step) v = Math.round(v / step) * step;
      return clamp(v, min, max);
    }

    _bindDrag() {
      let dragging = false;
      let startY = 0;
      let startT = 0;

      const move = (e) => {
        if (!dragging) return;
        const fine = e.shiftKey ? 0.25 : 1;
        const dy = (startY - e.clientY) * fine;
        this.setValue(this._denorm(startT + dy / 160), true);
        e.preventDefault();
      };
      const up = () => {
        dragging = false;
        document.body.classList.remove("knob-dragging");
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
      };

      this.dial.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        dragging = true;
        startY = e.clientY;
        startT = this._norm(this.value);
        document.body.classList.add("knob-dragging");
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
        e.preventDefault();
      });

      this.dial.addEventListener("dblclick", () => this.setValue(this.o.def, true));

      this.dial.addEventListener("wheel", (e) => {
        const dir = e.deltaY < 0 ? 1 : -1;
        const amount = e.shiftKey ? 0.005 : 0.02;
        this.setValue(this._denorm(this._norm(this.value) + dir * amount), true);
        e.preventDefault();
      }, { passive: false });
    }

    setValue(v, fire) {
      const next = clamp(v, this.o.min, this.o.max);
      if (next === this.value && fire !== true) return;
      this.value = next;
      this.draw();
      if (fire && this.o.onChange) this.o.onChange(this.value);
    }

    formatted() {
      if (this.o.format) return this.o.format(this.value);
      const v = this.value;
      const txt = Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
      return txt + this.o.unit;
    }

    draw() {
      const c = this.canvas;
      const ctx = c.getContext("2d");
      const s = c.width;
      const r = s / 2;
      ctx.clearRect(0, 0, s, s);

      const t = this._norm(this.value);
      const a0 = Math.PI * 0.75;
      const a1 = Math.PI * 2.25;
      const ang = a0 + (a1 - a0) * t;

      // корпус
      const grad = ctx.createLinearGradient(0, 0, 0, s);
      grad.addColorStop(0, "#4a5058");
      grad.addColorStop(1, "#23272d");
      ctx.beginPath();
      ctx.arc(r, r, r * 0.66, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.strokeStyle = "#15181c";
      ctx.lineWidth = s * 0.03;
      ctx.stroke();

      // фоновая дуга
      ctx.beginPath();
      ctx.arc(r, r, r * 0.86, a0, a1);
      ctx.strokeStyle = "#191c21";
      ctx.lineWidth = s * 0.09;
      ctx.lineCap = "round";
      ctx.stroke();

      // активная дуга
      ctx.beginPath();
      ctx.arc(r, r, r * 0.86, a0, ang);
      ctx.strokeStyle = this.o.color;
      ctx.lineWidth = s * 0.09;
      ctx.stroke();

      // указатель
      ctx.beginPath();
      ctx.moveTo(r + Math.cos(ang) * r * 0.22, r + Math.sin(ang) * r * 0.22);
      ctx.lineTo(r + Math.cos(ang) * r * 0.6, r + Math.sin(ang) * r * 0.6);
      ctx.strokeStyle = "#e8edf2";
      ctx.lineWidth = s * 0.07;
      ctx.stroke();

      this.valueEl.textContent = this.formatted();
    }
  }

  /* ============================================================
     Выпадающее меню по клику (контекстные меню каналов и т.п.)
     ============================================================ */

  function popupMenu(x, y, items) {
    closePopup();
    const menu = el("div", { class: "popup-menu", style: `left:${x}px;top:${y}px` });
    for (const it of items) {
      if (it === "-") {
        menu.appendChild(el("div", { class: "popup-sep" }));
        continue;
      }
      const row = el("div", {
        class: "popup-item" + (it.danger ? " danger" : "") + (it.checked ? " checked" : ""),
        text: it.label,
        onclick: () => { closePopup(); it.action && it.action(); }
      });
      menu.appendChild(row);
    }
    document.body.appendChild(menu);

    // не вылезать за экран
    const r = menu.getBoundingClientRect();
    if (r.right > window.innerWidth) menu.style.left = Math.max(4, window.innerWidth - r.width - 6) + "px";
    if (r.bottom > window.innerHeight) menu.style.top = Math.max(4, window.innerHeight - r.height - 6) + "px";

    // клик вне меню закрывает его; клик внутри должен успеть дойти до пункта
    const outside = (e) => {
      if (menu.contains(e.target)) return;
      closePopup();
    };
    setTimeout(() => {
      window.addEventListener("mousedown", outside);
      window.addEventListener("wheel", closePopup, { once: true });
    }, 0);

    CS._popup = menu;
    CS._popupOutside = outside;
    return menu;
  }

  function closePopup() {
    if (CS._popupOutside) {
      window.removeEventListener("mousedown", CS._popupOutside);
      CS._popupOutside = null;
    }
    if (CS._popup && CS._popup.parentNode) CS._popup.parentNode.removeChild(CS._popup);
    CS._popup = null;
  }

  /* ============================================================
     Модальные окна
     ============================================================ */

  function modal(title, bodyNode, actions) {
    const root = $("#modal");
    $("#modal-title").textContent = title;
    const body = $("#modal-body");
    body.innerHTML = "";
    if (typeof bodyNode === "string") body.appendChild(el("div", { text: bodyNode }));
    else if (bodyNode) body.appendChild(bodyNode);

    const act = $("#modal-actions");
    act.innerHTML = "";
    for (const a of actions || [{ label: "Ок" }]) {
      act.appendChild(el("button", {
        class: "tb-btn wide" + (a.accent ? " accent" : ""),
        text: a.label,
        onclick: () => { if (!a.action || a.action() !== false) closeModal(); }
      }));
    }
    root.classList.remove("hidden");
    return root;
  }

  function closeModal() {
    $("#modal").classList.add("hidden");
  }

  function prompt(title, label, value, onOk) {
    const input = el("input", { class: "modal-input", type: "text", value: value || "" });
    const box = el("div", {}, [el("label", { class: "modal-label", text: label }), input]);
    modal(title, box, [
      { label: "Отмена" },
      { label: "Ок", accent: true, action: () => onOk(input.value) }
    ]);
    setTimeout(() => { input.focus(); input.select(); }, 30);
  }

  function confirm(title, text, onOk) {
    modal(title, text, [
      { label: "Отмена" },
      { label: "Да", accent: true, action: onOk }
    ]);
  }

  /* ---------------- Экспорт ---------------- */

  CS.util = {
    $, $$, el, clamp, lerp, round2, toLog, fromLog, uid,
    midiToFreq, noteName, isBlackKey, NOTE_NAMES,
    deepClone, downloadBlob, formatTime, fitCanvas,
    popupMenu, closePopup, modal, closeModal, prompt, confirm
  };
  CS.Knob = Knob;
  CS.bus = bus;

})(window.CS);
