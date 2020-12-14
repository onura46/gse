from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.filemanager import MDFileManager
import os
from kivy.properties import StringProperty, ObjectProperty, NumericProperty, BooleanProperty
from kivy.event import EventDispatcher
from kivymd.uix.picker import MDTimePicker, MDDatePicker
from datetime import datetime
from gse import Process


class Welcome(MDScreen):
    pass


class Background(MDScreen):
    pass

class Colors(MDScreen):
    pass


class Time(MDScreen):
    pass


class Advanced(MDScreen):
    pass

class Ready(MDScreen):
    pass


class Control(EventDispatcher):
    p = Process()
    conf = {'input': ["old_one.mp4", "str", False],
            'output_dir': ["", "str", False],
            'output_name': ["new_one", "str", False],
            'extension': ["mp4", "str", False],
            'video_codec': [None, "str", True],
            'audio_codec': [None, "str", True],
            'background': [[0, 255, 0], "obj", False],
            'relative_mask_resolution': [80, "num", False],
            'relative_mask_fps': [50, "num", False],
            'threads': [4, "num", False],
            'cuda': [True, "bool", False],
            'compression': ["medium", "str", False],
            'scaler': ["bicubic", "str", False],
            'monitor': ["bar", "str", True],
            'log': [False, "bool", False],
            'get_frame': [0, "num", False],
            'mask': ["", "str", False]}

    for key in conf:
        if conf[key][1] == "str":
            func = StringProperty
        elif conf[key][1] == "num":
            func = NumericProperty
        elif conf[key][1] == "bool":
            func = BooleanProperty
        else:
            func = ObjectProperty
        exec(f"""
{key} = func(conf[key][0], allownone=conf[key][2])
def on_{key}(self, instance, value):
    self.p.{key} = value
    print(f'{key} changed to "{{value}}"')""")


class GSE(MDApp):
    sm = video_codec_menu = audio_codec_menu = advanced = None
    ctrl = Control()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.manager_open = False
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager,
            select_path=self.select_path,
        )

    def file_manager_open(self):
        # parent = os.path.dirname(os.path.abspath(os.getcwd()))
        home = os.path.expanduser("~")
        self.file_manager.show(home)  # output manager to the screen
        self.manager_open = True

    def select_path(self, path):
        self.exit_manager()
        if self.sm.current == "welcome":
            self.ctrl.input = path
            self.sm.current = "background"
        elif self.sm.current == "background":
            self.ctrl.background = path
            self.sm.current = "time"
        elif self.sm.current == "ready":
            self.ctrl.output_dir = os.path.join(path, "")

    def exit_manager(self, *args):
        self.manager_open = False
        self.file_manager.close()

    def show_date_picker(self):
        date_dialog = MDDatePicker(callback=self.get_date)
        date_dialog.open()

    def get_date(self, date):
        '''
        :type date: <class 'datetime.date'>
        '''
        self.show_time_picker()

    def show_time_picker(self):
        time_dialog = MDTimePicker()
        time_dialog.bind(time=self.get_time)
        previous_time = datetime.now()
        time_dialog.set_time(previous_time)
        time_dialog.open()

    def get_time(self, instance, time):
        '''
        The method returns the set time.

        :type instance: <kivymd.uix.picker.MDTimePicker object>
        :type time: <class 'datetime.time'>
        '''
        if self.sm.current == "time":
            self.sm.current = "ready"
        return time

    def build(self):
        self.theme_cls.primary_palette = "LightGreen"
        # self.theme_cls.theme_style = "Dark"
        self.sm = ScreenManager()
        self.advanced = Advanced()
        self.sm.add_widget(self.advanced)
        self.sm.add_widget(Welcome())
        self.sm.add_widget(Background())
        self.sm.add_widget(Colors())
        self.sm.add_widget(Time())
        self.sm.add_widget(Ready())
        return self.sm


if __name__ == '__main__':
    GSE().run()
