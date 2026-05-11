"""Results screen — renders inspiral + waveform plots via matplotlib."""

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.card import MDCard
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.graphics import Color, Rectangle

import numpy as np

_MPL_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
    _MPL_AVAILABLE = True
except Exception:
    pass


def _dark_fig(nrows=1, ncols=1, figsize=(6, 3.5)):
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, facecolor="#1a1a2e")
    axs = np.atleast_1d(axes)
    for ax in axs.flat:
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="#aaaacc", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333355")
        ax.xaxis.label.set_color("#aaaacc")
        ax.yaxis.label.set_color("#aaaacc")
        ax.title.set_color("#ccccff")
    return fig, axes


class TabItem(BoxLayout, MDTabsBase):
    pass


class _MetricCard(MDCard):
    def __init__(self, label, value, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(0.45, None),
            height=dp(72),
            padding=dp(8),
            radius=[dp(8)],
            md_bg_color=(0.12, 0.12, 0.22, 1),
            **kwargs,
        )
        self.add_widget(MDLabel(text=label, font_style="Caption", theme_text_color="Secondary", halign="center"))
        self.add_widget(MDLabel(text=str(value), font_style="H6", theme_text_color="Primary", halign="center"))


class ResultsScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "results"
        self._result = None
        self._build()

    def _build(self):
        outer = MDBoxLayout(orientation="vertical")

        # toolbar
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            padding=[dp(8), dp(4)],
            md_bg_color=(0.13, 0.13, 0.18, 1),
        )
        back = MDIconButton(icon="arrow-left", on_release=lambda *_: setattr(self.manager, "current", "params"))
        toolbar.add_widget(back)
        toolbar.add_widget(MDLabel(text="Results", font_style="H6", theme_text_color="Primary"))
        outer.add_widget(toolbar)

        # placeholder until data loaded
        self._content_box = MDBoxLayout(orientation="vertical")
        self._placeholder = MDLabel(
            text="No simulation results yet.",
            halign="center",
            theme_text_color="Secondary",
        )
        self._content_box.add_widget(self._placeholder)
        outer.add_widget(self._content_box)
        self.add_widget(outer)
        self._outer = outer

    def load_result(self, result: dict):
        if result is None:
            return
        self._result = result
        self._outer.remove_widget(self._content_box)

        scroll = ScrollView()
        body = MDBoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(12),
            size_hint_y=None,
        )
        body.bind(minimum_height=body.setter("height"))

        inspiral = result["inspiral"]
        waveform = result["waveform"]
        params = result["params"]

        # ---- Metrics row ----
        metrics = self._compute_metrics(inspiral, waveform)
        mrow1 = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(80), spacing=dp(8))
        mrow2 = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(80), spacing=dp(8))
        mrow1.add_widget(_MetricCard("Duration [M]", metrics["duration"]))
        mrow1.add_widget(_MetricCard("Final r [M]", metrics["r_final"]))
        mrow2.add_widget(_MetricCard("GW cycles", metrics["gw_cycles"]))
        mrow2.add_widget(_MetricCard("Peak f [mHz]", metrics["f_peak_mhz"]))
        body.add_widget(mrow1)
        body.add_widget(mrow2)

        plunge_lbl = MDLabel(
            text="⚠ Plunge detected" if inspiral["plunged"] else "✓ Inspiral completed",
            halign="center",
            theme_text_color="Error" if inspiral["plunged"] else "Primary",
            font_style="Caption",
            size_hint_y=None,
            height=dp(28),
        )
        body.add_widget(plunge_lbl)

        if _MPL_AVAILABLE:
            body.add_widget(self._waveform_plot(waveform))
            body.add_widget(self._inspiral_plot(inspiral))
            body.add_widget(self._freq_plot(waveform))
        else:
            body.add_widget(MDLabel(
                text="[matplotlib not available — install kivy-garden-matplotlib]",
                halign="center",
                theme_text_color="Error",
                size_hint_y=None,
                height=dp(60),
            ))

        new_sim_btn = MDRaisedButton(
            text="NEW SIMULATION",
            size_hint_x=1,
            height=dp(48),
            md_bg_color=(0.2, 0.6, 1.0, 1),
            on_release=lambda *_: setattr(self.manager, "current", "params"),
        )
        body.add_widget(new_sim_btn)
        body.add_widget(MDLabel(size_hint_y=None, height=dp(24)))

        scroll.add_widget(body)
        self._outer.add_widget(scroll)

    def _compute_metrics(self, inspiral, waveform):
        t = inspiral["t"]
        r = inspiral["r_circ"]
        omf = inspiral["omega_phi"]
        gw_freq = waveform["f_gw"]

        duration = f"{t[-1]:.2e}"
        r_final = f"{r[-1]:.2f}"

        # GW cycles ≈ total phase / (2π)
        from emri_core import _cumtrapz
        phi_gw = _cumtrapz(2 * omf, t)
        gw_cycles = f"{phi_gw[-1] / (2 * 3.14159):.1f}"

        # Peak GW frequency in mHz (assuming M = 1e6 solar masses)
        M_SI = 1e6 * 2e30
        t_M = M_SI * 6.674e-11 / (3e8)**3
        f_peak_hz = float(np.max(gw_freq)) / t_M
        f_peak_mhz = f"{f_peak_hz * 1e3:.3f}"

        return {
            "duration": duration,
            "r_final": r_final,
            "gw_cycles": gw_cycles,
            "f_peak_mhz": f_peak_mhz,
        }

    def _waveform_plot(self, waveform) -> BoxLayout:
        fig, ax = _dark_fig(figsize=(6, 3.2))
        ax = ax[0] if hasattr(ax, "__len__") else ax
        t = waveform["t"] / 1e6
        ax.plot(t, waveform["h_plus"], color="#4fc3f7", lw=0.8, label=r"$h_+$")
        ax.plot(t, waveform["h_cross"], color="#f48fb1", lw=0.8, alpha=0.7, label=r"$h_\times$")
        ax.set_xlabel("t  [10⁶ M]")
        ax.set_ylabel("Strain")
        ax.set_title("Gravitational-wave strain")
        ax.legend(fontsize=7, loc="upper right")
        fig.tight_layout(pad=0.5)
        box = BoxLayout(size_hint_y=None, height=dp(220))
        box.add_widget(FigureCanvasKivyAgg(fig))
        return box

    def _inspiral_plot(self, inspiral) -> BoxLayout:
        fig, axes = _dark_fig(nrows=1, ncols=2, figsize=(6, 2.8))
        ax1, ax2 = axes
        t = inspiral["t"] / 1e6
        ax1.plot(t, inspiral["r_circ"], color="#a5d6a7", lw=1.0)
        ax1.axhline(6.0, color="#ef9a9a", lw=0.8, ls="--", label="ISCO")
        ax1.set_xlabel("t [10⁶ M]")
        ax1.set_ylabel("r [M]")
        ax1.set_title("Orbital radius")
        ax1.legend(fontsize=6)

        ax2.plot(inspiral["p"], inspiral["e"], color="#ce93d8", lw=1.0)
        p_sep = 6.0 + 2.0 * inspiral["e"]
        ax2.plot(p_sep, inspiral["e"], color="#ef9a9a", lw=0.8, ls="--", label="sep.")
        ax2.set_xlabel("p [M]")
        ax2.set_ylabel("e")
        ax2.set_title("(p, e) evolution")
        ax2.legend(fontsize=6)

        fig.tight_layout(pad=0.5)
        box = BoxLayout(size_hint_y=None, height=dp(200))
        box.add_widget(FigureCanvasKivyAgg(fig))
        return box

    def _freq_plot(self, waveform) -> BoxLayout:
        t = waveform["t"]
        f = waveform["f_gw"]
        fig, ax = _dark_fig(figsize=(6, 2.4))
        ax = ax[0] if hasattr(ax, "__len__") else ax
        ax.semilogy(t / 1e6, f, color="#ffcc80", lw=1.0)
        ax.set_xlabel("t [10⁶ M]")
        ax.set_ylabel("f_GW [M⁻¹]")
        ax.set_title("Instantaneous GW frequency")
        fig.tight_layout(pad=0.5)
        box = BoxLayout(size_hint_y=None, height=dp(180))
        box.add_widget(FigureCanvasKivyAgg(fig))
        return box


class AboutScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "about"
        self._build()

    def _build(self):
        root = MDBoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        back = MDIconButton(
            icon="arrow-left",
            size_hint_y=None,
            height=dp(48),
            on_release=lambda *_: setattr(self.manager, "current", "home"),
        )
        root.add_widget(back)
        root.add_widget(MDLabel(text="About EMRI Lab", font_style="H5", size_hint_y=None, height=dp(48)))
        text = (
            "EMRI Lab simulates gravitational-wave signals\n"
            "from extreme mass-ratio inspirals.\n\n"
            "Physics model:\n"
            "• Schwarzschild background (G=c=M=1)\n"
            "• (p, e) orbital parametrisation\n"
            "• Adiabatic 2.5 PN Peters–Mathews fluxes\n"
            "• Extended test-mass horizon corrections\n"
            "• RK4 time integrator\n"
            "• Harmonic mode summation h = Σ Aₙₘ e^{iΦₙₘ}\n\n"
            "Version: 0.1.0\n"
            "Licence: MIT"
        )
        root.add_widget(MDLabel(text=text, font_style="Body2"))
        self.add_widget(root)
