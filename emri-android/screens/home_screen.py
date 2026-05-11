from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.metrics import dp
from kivy.uix.image import Image


class HomeScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "home"
        self._build()

    def _build(self):
        root = MDBoxLayout(
            orientation="vertical",
            padding=dp(32),
            spacing=dp(20),
        )

        root.add_widget(MDLabel(size_hint_y=None, height=dp(40)))

        title = MDLabel(
            text="EMRI Lab",
            halign="center",
            theme_text_color="Primary",
            font_style="H3",
            size_hint_y=None,
            height=dp(60),
        )
        root.add_widget(title)

        subtitle = MDLabel(
            text="Extreme Mass-Ratio Inspiral Simulator",
            halign="center",
            theme_text_color="Secondary",
            font_style="Subtitle1",
            size_hint_y=None,
            height=dp(40),
        )
        root.add_widget(subtitle)

        root.add_widget(MDLabel(size_hint_y=None, height=dp(10)))

        desc = MDLabel(
            text=(
                "Simulate gravitational-wave signals from compact\n"
                "objects spiralling into massive black holes.\n\n"
                "Schwarzschild geometry · 2.5 PN fluxes · RK4 integrator"
            ),
            halign="center",
            theme_text_color="Secondary",
            font_style="Body1",
        )
        root.add_widget(desc)

        root.add_widget(MDLabel())  # spacer

        btn_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(12),
            size_hint_y=None,
            height=dp(140),
            padding=[dp(40), 0],
        )

        btn_run = MDRaisedButton(
            text="NEW SIMULATION",
            size_hint_x=1,
            height=dp(50),
            md_bg_color=(0.2, 0.6, 1.0, 1),
            on_release=self._go_params,
        )
        btn_box.add_widget(btn_run)

        btn_about = MDFlatButton(
            text="ABOUT",
            size_hint_x=1,
            height=dp(44),
            on_release=self._go_about,
        )
        btn_box.add_widget(btn_about)

        root.add_widget(btn_box)
        root.add_widget(MDLabel(size_hint_y=None, height=dp(20)))

        self.add_widget(root)

    def _go_params(self, *_):
        self.manager.current = "params"

    def _go_about(self, *_):
        self.manager.current = "about"
