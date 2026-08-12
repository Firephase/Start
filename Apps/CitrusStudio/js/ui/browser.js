"use strict";

/* ============================================================
   Citrus Studio — браузер: инструменты, пресеты, паттерны
   ============================================================ */

(function (CS) {

  const { $, el, prompt } = CS.util;
  const { Project, Instruments } = CS;

  const BrowserPanel = {

    init() {
      this.renderPresets();
      this.renderPatterns();

      $("#file-sample").addEventListener("change", (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f) return;
        const ch = Project.addChannel("sampler", f.name.replace(/\.[^.]+$/, ""));
        CS.loadSampleInto(ch, f, () => {
          CS.Inspector.showChannel(ch.id);
          CS.selectChannel(ch.id);
        });
        e.target.value = "";
      });

      CS.bus.on("project:loaded", () => this.renderPatterns());
      CS.bus.on("patterns:changed", () => this.renderPatterns());
      CS.bus.on("pattern:changed", () => this.renderPatterns());
    },

    renderPresets() {
      const drums = $("#browser-drums");
      const synths = $("#browser-synths");
      drums.innerHTML = "";
      synths.innerHTML = "";

      for (const p of CS.presets.drums) {
        drums.appendChild(this.presetItem(p));
      }
      for (const p of CS.presets.synths) {
        synths.appendChild(this.presetItem(p));
      }
    },

    presetItem(preset) {
      const color = preset.color || (Instruments.defs[preset.type] || {}).color || "#f0a03c";
      return el("div", {
        class: "browser-item",
        title: "Добавить канал",
        onclick: () => this.addPreset(preset)
      }, [
        el("span", { class: "bi-dot", style: `background:${color}` }),
        el("span", { text: preset.label })
      ]);
    },

    addPreset(preset) {
      Project.snapshot();
      const ch = Project.addChannel(preset.type, preset.label, preset.params, {
        color: preset.color,
        key: preset.key
      });
      CS.Inspector.showChannel(ch.id);
      CS.selectChannel(ch.id);
      CS.setStatus(`Добавлен канал «${ch.name}»`);
      return ch;
    },

    /** Пункты меню «+ Канал» в Channel Rack. */
    addMenuItems() {
      const items = [];
      for (const p of CS.presets.drums) items.push({ label: p.label, action: () => this.addPreset(p) });
      items.push("-");
      for (const p of CS.presets.synths) items.push({ label: p.label, action: () => this.addPreset(p) });
      items.push("-");
      items.push({ label: "Сэмплер (загрузить файл)", action: () => $("#file-sample").click() });
      return items;
    },

    renderPatterns() {
      const host = $("#browser-patterns");
      if (!host) return;
      host.innerHTML = "";
      for (const pat of Project.state.patterns) {
        const active = pat.id === Project.state.currentPattern;
        host.appendChild(el("div", {
          class: "browser-item" + (active ? " active" : ""),
          onclick: () => Project.setCurrentPattern(pat.id),
          oncontextmenu: (e) => {
            e.preventDefault();
            CS.util.popupMenu(e.clientX, e.clientY, [
              { label: "Переименовать", action: () => prompt("Паттерн", "Название", pat.name, (v) => {
                  pat.name = v || pat.name;
                  CS.bus.emit("patterns:changed");
                }) },
              { label: "Клонировать", action: () => { Project.snapshot(); Project.clonePattern(pat.id); } },
              { label: "Удалить", danger: true, action: () => { Project.snapshot(); Project.removePattern(pat.id); } }
            ]);
          }
        }, [
          el("span", { class: "bi-dot", style: `background:${pat.color}` }),
          el("span", { text: pat.name }),
          el("span", { class: "bi-len", text: pat.length / 16 + " т." })
        ]));
      }
    }
  };

  CS.BrowserPanel = BrowserPanel;

})(window.CS);
