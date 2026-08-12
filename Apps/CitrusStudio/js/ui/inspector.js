"use strict";

/* ============================================================
   Citrus Studio — инспектор: «окно плагина» и настройки инсерта.
   UI параметров строится автоматически по описаниям (defs).
   ============================================================ */

(function (CS) {

  const { $, el, popupMenu, noteName, prompt } = CS.util;
  const { Project, Engine, Instruments, Effects } = CS;

  /* ---------- Генератор контролов по спецификации ---------- */

  function control(spec, getValue, setValue, color) {
    if (spec.type === "enum") {
      const sel = el("select", { class: "param-select" });
      for (const opt of spec.options) {
        sel.appendChild(el("option", { value: opt, text: labelForOption(opt), selected: getValue() === opt }));
      }
      sel.addEventListener("change", () => setValue(sel.value));
      return el("div", { class: "param-field" }, [el("label", { class: "param-label", text: spec.label }), sel]);
    }

    if (spec.type === "bool") {
      const input = el("input", { type: "checkbox" });
      input.checked = !!getValue();
      input.addEventListener("change", () => setValue(input.checked));
      return el("label", { class: "param-check" }, [input, el("span", { text: spec.label })]);
    }

    const knob = new CS.Knob({
      label: spec.label,
      min: spec.min,
      max: spec.max,
      def: spec.def,
      step: spec.step || 0,
      curve: spec.curve || "lin",
      unit: spec.unit || "",
      value: getValue(),
      color: color || "#f0a03c",
      onChange: setValue
    });
    return knob.el;
  }

  const OPTION_LABELS = {
    sawtooth: "пила", square: "квадрат", triangle: "треугольник", sine: "синус",
    lowpass: "НЧ", highpass: "ВЧ", bandpass: "полоса", notch: "режекция"
  };
  const labelForOption = (o) => OPTION_LABELS[o] || o;

  function paramGrid(specs, params, onChange, color) {
    const grid = el("div", { class: "param-grid" });
    for (const spec of specs) {
      grid.appendChild(control(
        spec,
        () => params[spec.key],
        (v) => { params[spec.key] = v; onChange && onChange(spec.key, v); },
        color
      ));
    }
    return grid;
  }

  /* ============================================================
     Инспектор
     ============================================================ */

  const Inspector = {

    target: null,   // { kind: "channel"|"insert", id }

    showChannel(id) {
      this.target = { kind: "channel", id };
      this.render();
    },

    showInsert(index) {
      this.target = { kind: "insert", id: index };
      this.render();
    },

    refresh() {
      if (this.target) this.render();
    },

    render() {
      const body = $("#inspector-body");
      const title = $("#inspector-title");
      body.innerHTML = "";
      if (!this.target) return;

      if (this.target.kind === "channel") {
        const ch = Project.channel(this.target.id);
        if (!ch) { this.target = null; title.textContent = "Настройки"; return; }
        title.textContent = "Канал";
        body.appendChild(this.channelView(ch));
      } else {
        const idx = this.target.id;
        const ins = Project.state.inserts[idx];
        if (!ins) { this.target = null; return; }
        title.textContent = "Инсерт";
        body.appendChild(this.insertView(idx, ins));
      }
    },

    /* ---------------- Канал ---------------- */

    channelView(ch) {
      const def = Instruments.defs[ch.type];
      const root = el("div", { class: "insp" });

      root.appendChild(el("div", { class: "insp-head" }, [
        el("span", { class: "insp-dot", style: `background:${ch.color}` }),
        el("div", { class: "insp-titles" }, [
          el("div", { class: "insp-name", text: ch.name }),
          el("div", { class: "insp-sub", text: def ? def.name : ch.type })
        ]),
        el("button", {
          class: "tb-mini", text: "✎", title: "Переименовать",
          onclick: () => prompt("Имя канала", "Название", ch.name, (v) => {
            ch.name = v || ch.name;
            CS.bus.emit("channels:changed");
            this.refresh();
          })
        })
      ]));

      // микс-секция канала
      const mix = el("div", { class: "insp-block" });
      mix.appendChild(el("div", { class: "insp-block-title", text: "Микс" }));
      const mixGrid = el("div", { class: "param-grid" });

      const volKnob = new CS.Knob({
        label: "Громк", min: 0, max: 1.25, def: 0.8, value: ch.vol, color: ch.color,
        format: (v) => Math.round(v * 100) + "%",
        onChange: (v) => { ch.vol = v; CS.bus.emit("channels:mix", ch.id); }
      });
      const panKnob = new CS.Knob({
        label: "Панорама", min: -1, max: 1, def: 0, value: ch.pan, color: ch.color,
        format: (v) => (Math.abs(v) < 0.02 ? "центр" : (v < 0 ? "L" : "R") + Math.round(Math.abs(v) * 100)),
        onChange: (v) => { ch.pan = v; CS.bus.emit("channels:mix", ch.id); }
      });
      mixGrid.appendChild(volKnob.el);
      mixGrid.appendChild(panKnob.el);

      const insSel = el("select", { class: "param-select" });
      for (let i = 0; i < Project.state.inserts.length; i++) {
        insSel.appendChild(el("option", { value: i, text: i === 0 ? "Мастер" : "Инсерт " + i, selected: ch.insert === i }));
      }
      insSel.addEventListener("change", () => {
        ch.insert = parseInt(insSel.value, 10);
        CS.bus.emit("channels:changed");
      });
      mixGrid.appendChild(el("div", { class: "param-field" }, [
        el("label", { class: "param-label", text: "Инсерт" }), insSel
      ]));

      const keySel = el("select", { class: "param-select" });
      for (let k = 24; k <= 96; k++) {
        keySel.appendChild(el("option", { value: k, text: noteName(k), selected: ch.key === k }));
      }
      keySel.addEventListener("change", () => { ch.key = parseInt(keySel.value, 10); });
      mixGrid.appendChild(el("div", { class: "param-field" }, [
        el("label", { class: "param-label", text: "Нота шага" }), keySel
      ]));

      mix.appendChild(mixGrid);
      root.appendChild(mix);

      // сэмплер: загрузка файла
      if (ch.type === "sampler") {
        const info = el("div", { class: "insp-sample-info", text: ch._sampleName || "сэмпл не загружен" });
        const input = el("input", { type: "file", accept: "audio/*", hidden: true });
        input.addEventListener("change", () => {
          const f = input.files && input.files[0];
          if (f) CS.loadSampleInto(ch, f, () => { info.textContent = ch._sampleName; });
        });
        const block = el("div", { class: "insp-block" }, [
          el("div", { class: "insp-block-title", text: "Сэмпл" }),
          info,
          el("button", { class: "tb-btn wide", text: "Загрузить файл…", onclick: () => input.click() }),
          input
        ]);
        root.appendChild(block);
      }

      // параметры инструмента
      if (def) {
        const onChange = () => { /* параметры читаются при каждом триггере */ };
        if (def.groups) {
          for (const g of def.groups) {
            const specs = g.keys.map((k) => def.params.find((s) => s.key === k)).filter(Boolean);
            const block = el("div", { class: "insp-block" }, [
              el("div", { class: "insp-block-title", text: g.title }),
              paramGrid(specs, ch.params, onChange, ch.color)
            ]);
            root.appendChild(block);
          }
        } else {
          root.appendChild(el("div", { class: "insp-block" }, [
            el("div", { class: "insp-block-title", text: "Параметры" }),
            paramGrid(def.params, ch.params, onChange, ch.color)
          ]));
        }
      }

      // превью
      root.appendChild(el("button", {
        class: "tb-btn wide accent", text: "▶ Проиграть",
        onclick: () => Engine.preview(ch, ch.key, 0.6)
      }));

      return root;
    },

    /* ---------------- Инсерт ---------------- */

    insertView(idx, ins) {
      const root = el("div", { class: "insp" });

      root.appendChild(el("div", { class: "insp-head" }, [
        el("span", { class: "insp-dot", style: "background:#f0a03c" }),
        el("div", { class: "insp-titles" }, [
          el("div", { class: "insp-name", text: ins.name }),
          el("div", { class: "insp-sub", text: idx === 0 ? "мастер-шина" : "инсерт " + idx })
        ])
      ]));

      const mixGrid = el("div", { class: "param-grid" });
      if (idx > 0) {
        mixGrid.appendChild(new CS.Knob({
          label: "Громк", min: 0, max: 1.25, def: 0.8, value: ins.vol,
          format: (v) => Math.round(v * 100) + "%",
          onChange: (v) => { ins.vol = v; CS.bus.emit("mixer:changed"); }
        }).el);
        mixGrid.appendChild(new CS.Knob({
          label: "Панорама", min: -1, max: 1, def: 0, value: ins.pan,
          format: (v) => (Math.abs(v) < 0.02 ? "центр" : (v < 0 ? "L" : "R") + Math.round(Math.abs(v) * 100)),
          onChange: (v) => { ins.pan = v; CS.bus.emit("mixer:changed"); }
        }).el);
      } else {
        mixGrid.appendChild(new CS.Knob({
          label: "Мастер", min: 0, max: 1.25, def: 0.8, value: Project.state.masterVol,
          format: (v) => Math.round(v * 100) + "%",
          onChange: (v) => { Project.state.masterVol = v; CS.bus.emit("mixer:changed"); }
        }).el);
      }
      root.appendChild(el("div", { class: "insp-block" }, [
        el("div", { class: "insp-block-title", text: "Микс" }), mixGrid
      ]));

      // цепочка эффектов
      const fxWrap = el("div", { class: "insp-block" });
      fxWrap.appendChild(el("div", { class: "insp-block-title", text: "Эффекты" }));

      ins.fx.forEach((item, i) => {
        const d = Effects.defs[item.type];
        const head = el("div", { class: "fx-head" + (item.enabled ? "" : " off") }, [
          el("button", {
            class: "fx-power" + (item.enabled ? " on" : ""), text: "⏻", title: "Вкл/выкл",
            onclick: () => { item.enabled = !item.enabled; Engine.rebuild(); this.refresh(); }
          }),
          el("span", { class: "fx-name", text: d ? d.name : item.type }),
          el("button", {
            class: "fx-btn", text: "▲", title: "Выше",
            onclick: () => { if (i > 0) { ins.fx.splice(i - 1, 0, ins.fx.splice(i, 1)[0]); Engine.rebuild(); this.refresh(); } }
          }),
          el("button", {
            class: "fx-btn", text: "▼", title: "Ниже",
            onclick: () => { if (i < ins.fx.length - 1) { ins.fx.splice(i + 1, 0, ins.fx.splice(i, 1)[0]); Engine.rebuild(); this.refresh(); } }
          }),
          el("button", {
            class: "fx-btn danger", text: "✕", title: "Удалить",
            onclick: () => { ins.fx.splice(i, 1); Engine.rebuild(); this.refresh(); }
          })
        ]);
        fxWrap.appendChild(head);

        if (d && item.enabled) {
          fxWrap.appendChild(paramGrid(d.params, item.params, (key) => {
            const spec = d.params.find((s) => s.key === key);
            if (spec && (spec.type === "enum" || spec.type === "bool")) Engine.updateFx(item);
            else Engine.updateFx(item);
          }, "#6fc3ff"));
        }
      });

      fxWrap.appendChild(el("button", {
        class: "tb-btn wide", text: "+ Эффект",
        onclick: (e) => {
          const items = Object.keys(Effects.defs).map((type) => ({
            label: Effects.defs[type].name,
            action: () => {
              ins.fx.push(CS.makeFx(type));
              Engine.rebuild();
              this.refresh();
            }
          }));
          const r = e.currentTarget.getBoundingClientRect();
          popupMenu(r.left, r.bottom + 4, items);
        }
      }));

      root.appendChild(fxWrap);
      return root;
    }
  };

  CS.Inspector = Inspector;

})(window.CS);
