"""EMRI Lab — Android/Desktop Kivy application entry point."""

import os
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivymd.app import MDApp
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from screens.home_screen import HomeScreen
from screens.params_screen import ParamsScreen
from screens.run_screen import RunScreen
from screens.results_screen import ResultsScreen, AboutScreen


class EMRILabApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.accent_palette = "Cyan"
        self.title = "EMRI Lab"

        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(HomeScreen())
        sm.add_widget(ParamsScreen())
        sm.add_widget(RunScreen())
        sm.add_widget(ResultsScreen())
        sm.add_widget(AboutScreen())
        return sm


if __name__ == "__main__":
    EMRILabApp().run()
