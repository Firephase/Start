"""Run screen — shows progress, runs simulation in background thread."""

import threading
from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDCircularProgressIndicator
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivy.metrics import dp
from kivy.clock import Clock


class RunScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "run"
        self._params = {}
        self._build()

    def _build(self):
        self._root = MDBoxLayout(
            orientation="vertical",
            padding=dp(32),
            spacing=dp(20),
        )

        self._root.add_widget(MDLabel())  # top spacer

        self._spinner = MDCircularProgressIndicator(
            size_hint=(None, None),
            size=(dp(64), dp(64)),
            pos_hint={"center_x": 0.5},
        )
        self._root.add_widget(self._spinner)

        self._status = MDLabel(
            text="Initialising…",
            halign="center",
            theme_text_color="Secondary",
            font_style="Body1",
            size_hint_y=None,
            height=dp(40),
        )
        self._root.add_widget(self._status)

        self._detail = MDLabel(
            text="",
            halign="center",
            theme_text_color="Secondary",
            font_style="Caption",
            size_hint_y=None,
            height=dp(30),
        )
        self._root.add_widget(self._detail)

        self._root.add_widget(MDLabel())  # bottom spacer

        self._btn_results = MDRaisedButton(
            text="VIEW RESULTS",
            size_hint_x=1,
            height=dp(50),
            md_bg_color=(0.2, 0.8, 0.4, 1),
            opacity=0,
            disabled=True,
            on_release=self._go_results,
        )
        self._root.add_widget(self._btn_results)

        self._btn_back = MDRaisedButton(
            text="BACK TO PARAMETERS",
            size_hint_x=1,
            height=dp(44),
            on_release=lambda *_: setattr(self.manager, "current", "params"),
        )
        self._root.add_widget(self._btn_back)

        self._root.add_widget(MDLabel(size_hint_y=None, height=dp(24)))
        self.add_widget(self._root)

    def start_run(self, **params):
        self._params = params
        self._btn_results.opacity = 0
        self._btn_results.disabled = True
        self._status.text = "Running inspiral…"
        self._detail.text = ""
        self._result = None
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        from emri_core import integrate_inspiral, build_waveform
        import math

        p = self._params
        Clock.schedule_once(lambda dt: self._set_status("Running RK4 integration…", ""), 0)

        inspiral = integrate_inspiral(
            p0=p["p"],
            e0=p["e"],
            eta=p["eta"],
            t_max=p["t_max"],
            n_points=p["n_points"],
            flux_model=p["flux_model"],
        )

        Clock.schedule_once(lambda dt: self._set_status("Building waveform…", ""), 0)

        n_max = p["n_max"]
        modes = [(n, 2) for n in range(-n_max, n_max + 1)]
        if not modes:
            modes = [(0, 2)]

        waveform = build_waveform(
            inspiral,
            eta=p["eta"],
            distance_mpc=p["distance_mpc"],
            modes=modes,
            iota=p["iota"],
        )

        self._result = {"inspiral": inspiral, "waveform": waveform, "params": p}

        steps = inspiral["n_steps"]
        plunged = inspiral["plunged"]
        msg = f"Done — {steps} steps{'  |  plunge detected' if plunged else ''}"
        Clock.schedule_once(lambda dt: self._on_done(msg), 0)

    def _set_status(self, status, detail):
        self._status.text = status
        self._detail.text = detail

    def _on_done(self, msg):
        self._status.text = msg
        self._spinner.active = False
        self._btn_results.opacity = 1
        self._btn_results.disabled = False
        results_screen = self.manager.get_screen("results")
        results_screen.load_result(self._result)

    def _go_results(self, *_):
        self.manager.current = "results"
