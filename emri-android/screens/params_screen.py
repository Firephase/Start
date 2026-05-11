from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.slider import MDSlider
from kivymd.uix.menu import MDDropdownMenu
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.properties import NumericProperty, StringProperty


class LabeledSlider(MDBoxLayout):
    """Row: label + value badge + MDSlider."""

    def __init__(self, label, min_val, max_val, default, fmt="{:.2f}", step=None, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(0), size_hint_y=None, **kwargs)
        self.fmt = fmt
        self._value = default

        header = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28))
        self.lbl = MDLabel(text=label, theme_text_color="Secondary", font_style="Caption")
        self.val_lbl = MDLabel(
            text=fmt.format(default),
            halign="right",
            theme_text_color="Primary",
            font_style="Caption",
        )
        header.add_widget(self.lbl)
        header.add_widget(self.val_lbl)

        sl_kwargs = dict(min=min_val, max=max_val, value=default, size_hint_y=None, height=dp(40))
        if step is not None:
            sl_kwargs["step"] = step
        self.slider = MDSlider(**sl_kwargs)
        self.slider.bind(value=self._on_value)

        self.add_widget(header)
        self.add_widget(self.slider)
        self.height = dp(68)

    def _on_value(self, inst, val):
        self._value = val
        self.val_lbl.text = self.fmt.format(val)

    @property
    def value(self):
        return self._value


class ParamsScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "params"
        self._flux_model = "BASELINE_PN"
        self._build()

    def _build(self):
        outer = MDBoxLayout(orientation="vertical")

        # ---- toolbar ----
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            padding=[dp(8), dp(4)],
            md_bg_color=(0.13, 0.13, 0.18, 1),
        )
        back_btn = MDIconButton(icon="arrow-left", on_release=lambda *_: setattr(self.manager, "current", "home"))
        title = MDLabel(text="Simulation Parameters", font_style="H6", theme_text_color="Primary")
        toolbar.add_widget(back_btn)
        toolbar.add_widget(title)
        outer.add_widget(toolbar)

        # ---- scrollable form ----
        scroll = ScrollView()
        form = MDBoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8),
            size_hint_y=None,
        )
        form.bind(minimum_height=form.setter("height"))

        def section(text):
            lbl = MDLabel(
                text=text,
                font_style="Subtitle2",
                theme_text_color="Primary",
                size_hint_y=None,
                height=dp(32),
            )
            return lbl

        # Orbital
        form.add_widget(section("Orbital Parameters"))
        self.sl_p = LabeledSlider("Semi-latus rectum  p  [M]", 7.0, 40.0, 12.0, "{:.1f}")
        self.sl_e = LabeledSlider("Eccentricity  e", 0.0, 0.95, 0.0, "{:.3f}", step=0.005)
        self.sl_iota = LabeledSlider("Inclination  ι  [rad]", 0.0, 1.5707, 0.0, "{:.3f}")
        form.add_widget(self.sl_p)
        form.add_widget(self.sl_e)
        form.add_widget(self.sl_iota)

        # Physics
        form.add_widget(section("Physics"))
        self.sl_eta = LabeledSlider("Mass ratio  η", 1e-7, 1e-3, 1e-5, "{:.2e}")
        form.add_widget(self.sl_eta)

        flux_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        flux_row.add_widget(MDLabel(text="Flux model", theme_text_color="Secondary"))
        self.flux_btn = MDRaisedButton(
            text="BASELINE PN",
            size_hint_x=None,
            width=dp(180),
            on_release=self._open_flux_menu,
        )
        flux_row.add_widget(self.flux_btn)
        form.add_widget(flux_row)

        horizon_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48))
        horizon_row.add_widget(MDLabel(text="Horizon flux correction", theme_text_color="Secondary"))
        self.sw_horizon = MDSwitch(active=False)
        horizon_row.add_widget(self.sw_horizon)
        form.add_widget(horizon_row)

        self.sl_dist = LabeledSlider("Distance  [Mpc]", 10.0, 10000.0, 100.0, "{:.0f}", step=10.0)
        form.add_widget(self.sl_dist)

        # Integration
        form.add_widget(section("Integration"))
        self.sl_tmax = LabeledSlider("t_max  [10⁶ M]", 0.5, 50.0, 5.0, "{:.1f}")
        self.sl_npts = LabeledSlider("Points  n", 200, 3000, 800, "{:.0f}", step=50)
        form.add_widget(self.sl_tmax)
        form.add_widget(self.sl_npts)

        # Waveform
        form.add_widget(section("Waveform"))
        self.sl_nmax = LabeledSlider("Max radial mode  n_max", 0, 5, 2, "{:.0f}", step=1)
        form.add_widget(self.sl_nmax)

        form.add_widget(MDLabel(size_hint_y=None, height=dp(16)))
        run_btn = MDRaisedButton(
            text="▶  RUN INSPIRAL",
            size_hint_x=1,
            height=dp(52),
            md_bg_color=(0.2, 0.6, 1.0, 1),
            on_release=self._on_run,
        )
        form.add_widget(run_btn)
        form.add_widget(MDLabel(size_hint_y=None, height=dp(24)))

        scroll.add_widget(form)
        outer.add_widget(scroll)
        self.add_widget(outer)

        # Dropdown menu for flux model
        menu_items = [
            {"text": "BASELINE PN", "on_release": lambda: self._set_flux("BASELINE_PN", "BASELINE PN")},
            {"text": "EXTENDED TEST MASS", "on_release": lambda: self._set_flux("EXTENDED_TEST_MASS", "EXTENDED TM")},
        ]
        self._menu = MDDropdownMenu(caller=self.flux_btn, items=menu_items, width_mult=4)

    def _open_flux_menu(self, *_):
        self._menu.open()

    def _set_flux(self, model_id, label):
        self._flux_model = model_id
        self.flux_btn.text = label
        self._menu.dismiss()

    def _on_run(self, *_):
        screen = self.manager.get_screen("run")
        screen.start_run(
            p=self.sl_p.value,
            e=self.sl_e.value,
            iota=self.sl_iota.value,
            eta=self.sl_eta.value,
            flux_model="EXTENDED_TEST_MASS" if self.sw_horizon.active else self._flux_model,
            distance_mpc=self.sl_dist.value,
            t_max=self.sl_tmax.value * 1e6,
            n_points=int(self.sl_npts.value),
            n_max=int(self.sl_nmax.value),
        )
        self.manager.current = "run"
