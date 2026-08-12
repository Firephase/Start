"use strict";

/* ============================================================
   Citrus Studio — микшер: инсерты, фейдеры, разводка каналов
   ============================================================ */

(function (CS) {

  const { $, el, clamp, prompt } = CS.util;
  const { Project, Engine, Effects } = CS;

  const Mixer = {

    strips: [],
    selected: 0,

    init() {
      this.host = $("#mixer-strips");
      CS.bus.on("project:loaded", () => this.render());
      CS.bus.on("channels:changed", () => this.render());
      CS.bus.on("mixer:changed", () => this.updateValues());
      CS.bus.on("graph:rebuilt", () => this.updateValues());
      this.render();
    },

    render() {
      if (!this.host) return;
      this.host.innerHTML = "";
      this.strips = [];

      Project.state.inserts.forEach((ins, idx) => {
        const strip = el("div", { class: "strip" + (idx === 0 ? " master" : "") + (idx === this.selected ? " selected" : "") });

        strip.addEventListener("mousedown", () => this.select(idx));

        // имя
        const name = el("div", {
          class: "strip-name",
          text: ins.name,
          title: "Двойной клик — переименовать",
          ondblclick: () => prompt("Имя инсерта", "Название", ins.name, (v) => {
            ins.name = v || ins.name;
            this.render();
          })
        });
        strip.appendChild(name);

        // панорама
        const panKnob = new CS.Knob({
          label: "PAN", min: -1, max: 1, def: 0, size: 26,
          value: idx === 0 ? 0 : ins.pan,
          format: (v) => (Math.abs(v) < 0.02 ? "C" : (v < 0 ? "L" : "R") + Math.round(Math.abs(v) * 100)),
          onChange: (v) => { if (idx > 0) { ins.pan = v; CS.bus.emit("mixer:changed"); } }
        });
        panKnob.el.classList.add("mini");
        strip.appendChild(panKnob.el);

        // фейдер + индикатор
        const meter = el("canvas", { class: "strip-meter", width: 8, height: 150 });
        const fader = this.makeFader(idx, ins);
        const faderRow = el("div", { class: "strip-fader-row" }, [meter, fader.el]);
        strip.appendChild(faderRow);

        // mute / solo
        const mute = el("button", {
          class: "strip-btn mute" + (ins.mute ? " on" : ""), text: "M", title: "Мьют",
          onclick: (e) => {
            e.stopPropagation();
            ins.mute = !ins.mute;
            mute.classList.toggle("on", ins.mute);
            CS.bus.emit("mixer:changed");
          }
        });
        const solo = el("button", {
          class: "strip-btn solo" + (ins.solo ? " on" : ""), text: "S", title: "Соло",
          onclick: (e) => {
            e.stopPropagation();
            const was = ins.solo;
            Project.state.inserts.forEach((x, i) => { if (i > 0) x.solo = false; });
            ins.solo = !was;
            this.render();
            CS.bus.emit("mixer:changed");
          }
        });
        if (idx > 0) strip.appendChild(el("div", { class: "strip-btns" }, [mute, solo]));
        else strip.appendChild(el("div", { class: "strip-btns" }, [el("div", { class: "strip-master-tag", text: "MASTER" })]));

        // эффекты
        const fxList = el("div", { class: "strip-fx" });
        ins.fx.forEach((item) => {
          const d = Effects.defs[item.type];
          fxList.appendChild(el("div", {
            class: "strip-fx-item" + (item.enabled ? "" : " off"),
            text: d ? d.name : item.type
          }));
        });
        fxList.appendChild(el("div", {
          class: "strip-fx-add", text: "+ FX",
          onclick: (e) => { e.stopPropagation(); this.select(idx); CS.showView("mixer"); }
        }));
        strip.appendChild(fxList);

        // какие каналы сюда идут
        const routed = Project.state.channels.filter((c) => c.insert === idx);
        const dots = el("div", { class: "strip-routed" });
        for (const c of routed.slice(0, 8)) {
          dots.appendChild(el("span", { class: "routed-dot", style: `background:${c.color}`, title: c.name }));
        }
        strip.appendChild(dots);

        this.host.appendChild(strip);
        this.strips.push({ idx, el: strip, meter, fader, panKnob, mute, solo });
      });
    },

    makeFader(idx, ins) {
      const track = el("div", { class: "fader-track" });
      const fill = el("div", { class: "fader-fill" });
      const cap = el("div", { class: "fader-cap" });
      track.appendChild(fill);
      track.appendChild(cap);

      const get = () => (idx === 0 ? Project.state.masterVol : ins.vol);
      const set = (v) => {
        const val = clamp(v, 0, 1.25);
        if (idx === 0) Project.state.masterVol = val;
        else ins.vol = val;
        update();
        CS.bus.emit("mixer:changed");
      };

      const update = () => {
        const t = get() / 1.25;
        fill.style.height = (t * 100) + "%";
        cap.style.bottom = "calc(" + (t * 100) + "% - 6px)";
        track.title = Math.round(get() * 100) + "%";
      };

      const startDrag = (e) => {
        const rect = track.getBoundingClientRect();
        const apply = (ev) => set((1 - (ev.clientY - rect.top) / rect.height) * 1.25);
        apply(e);
        const up = () => {
          window.removeEventListener("mousemove", apply);
          window.removeEventListener("mouseup", up);
        };
        window.addEventListener("mousemove", apply);
        window.addEventListener("mouseup", up);
        e.preventDefault();
        e.stopPropagation();
      };

      track.addEventListener("mousedown", startDrag);
      track.addEventListener("dblclick", () => set(0.8));
      update();

      return { el: track, update };
    },

    select(idx) {
      this.selected = idx;
      for (const s of this.strips) s.el.classList.toggle("selected", s.idx === idx);
      CS.Inspector.showInsert(idx);
      const ins = Project.state.inserts[idx];
      $("#mixer-hint").textContent = ins ? `${ins.name} — эффекты редактируются в панели справа` : "";
    },

    updateValues() {
      for (const s of this.strips) {
        const ins = Project.state.inserts[s.idx];
        if (!ins) continue;
        s.fader.update();
        s.panKnob.setValue(s.idx === 0 ? 0 : ins.pan);
        s.mute.classList.toggle("on", !!ins.mute);
        s.solo.classList.toggle("on", !!ins.solo);
      }
    },

    /** Индикаторы уровня — вызывается из главного цикла отрисовки. */
    updateMeters() {
      for (const s of this.strips) {
        const level = Engine.insertLevel(s.idx);
        const ctx = s.meter.getContext("2d");
        const h = s.meter.height;
        const w = s.meter.width;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#14171b";
        ctx.fillRect(0, 0, w, h);

        const db = level > 0 ? 20 * Math.log10(level) : -60;
        const t = clamp((db + 54) / 54, 0, 1);
        const barH = t * h;
        const grad = ctx.createLinearGradient(0, h, 0, 0);
        grad.addColorStop(0, "#4fd07a");
        grad.addColorStop(0.7, "#e2d24a");
        grad.addColorStop(1, "#ff5f4d");
        ctx.fillStyle = grad;
        ctx.fillRect(0, h - barH, w, barH);
      }
    }
  };

  CS.Mixer = Mixer;

})(window.CS);
