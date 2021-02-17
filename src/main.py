from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivymd.uix.filemanager import MDFileManager
from os.path import join as pjoin
from kivy.properties import StringProperty, ObjectProperty, NumericProperty, BooleanProperty
from kivy.event import EventDispatcher
from kivymd.uix.picker import MDTimePicker, MDDatePicker
from datetime import datetime
from kivymd.uix.menu import MDDropdownMenu
from gse import Project
from kivy.core.window import Window
from kivymd.uix.selectioncontrol import MDCheckbox
from kivy.clock import mainthread
from threading import Lock
from util.mythreading import MyThread, default_exc_callback
from time import sleep
from tempfile import mkdtemp
from shutil import rmtree
from util.mytqdm import MyLogger
from kivymd.uix.navigationdrawer import MDNavigationLayout
from kivymd.uix.screen import MDScreen
from util.screens.screens import Welcome, Background, Colors, Time, Ready
from util.widgets.widgets import LeftMenu
from os.path import expanduser, dirname, abspath


def my_callback(self, format_dict):
    if app.sm.current == "advanced":
        time = self.format_interval(format_dict["elapsed_s"] + format_dict["remaining_s"])
        app.advanced.update_time(format_dict["n"] * 10, time)


def exc_callback(*not_using):
    default_exc_callback(*not_using)
    if app.ctrl.do_lock.locked():
        app.ctrl.do_lock.release()


class Advanced(MDScreen):
    mask_menu = scaler_menu = compression_menu = video_codec_menu = audio_codec_menu = None
    video_codec_menu_items = [{"text": i} for i in ["default", "libx264 (.mp4)", "mpeg4 (.mp4)", "rawvideo (.avi)",
                                                    "png (.avi)", "libvorbis (.ogv)", "libvpx (.webm)"]]
    audio_codec_menu_items = [{"text": i} for i in ["default", "libmp3lame (.mp3)", "libvorbis (.ogg)",
                                                    "libfdk_aac (.m4a)", "pcm_s16le (.wav)", "pcm_s32le (.wav)"]]
    compression_menu_items = [{"text": i} for i in ["ultrafast", "superfast", "veryfast", "faster", "fast",
                                                    "medium", "slow", "slower", "veryslow", "placebo"]]
    scaler_menu_items = [{"text": i} for i in ["fast_bilinear", "bilinear", "bicubic", "experimental", "neighbor",
                                               "area", "bicublin", "gauss", "sinc", "lanczos", "spline"]]
    mask_menu_items = [{"text": i} for i in ["A.I.", "Video/Image"]]

    tempdir = mkdtemp()
    frame_filename = pjoin(tempdir, "temp_preview.jpg")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.video_codec_menu = MDDropdownMenu(
            caller=self.ids.video_codec_button,
            items=self.video_codec_menu_items,
            width_mult=4,
        )
        self.video_codec_menu.bind(on_release=self.video_codec_menu_callback)

        self.audio_codec_menu = MDDropdownMenu(
            caller=self.ids.audio_codec_button,
            items=self.audio_codec_menu_items,
            width_mult=4,
        )
        self.audio_codec_menu.bind(on_release=self.audio_codec_menu_callback)

        self.compression_menu = MDDropdownMenu(
            caller=self.ids.compression_button,
            items=self.compression_menu_items,
            width_mult=4,
        )
        self.compression_menu.bind(on_release=self.compression_menu_callback)

        self.scaler_menu = MDDropdownMenu(
            caller=self.ids.scaler_button,
            items=self.scaler_menu_items,
            width_mult=4,
        )
        self.scaler_menu.bind(on_release=self.scaler_menu_callback)

        self.mask_menu = MDDropdownMenu(
            caller=self.ids.mask_button,
            items=self.mask_menu_items,
            width_mult=4,
        )
        self.mask_menu.bind(on_release=self.mask_menu_callback)

    def on_enter(self, *args):
        MyThread(target=self.preview_queue, exc_callback=exc_callback).start()
        MyThread(target=self.time_queue, exc_callback=exc_callback).start()

    @staticmethod
    def video_codec_menu_callback(instance_menu, instance_menu_item):
        if "default" in instance_menu_item.text:
            app.ctrl.video_codec = None
        else:
            app.ctrl.video_codec = instance_menu_item.text.split()[0]
        instance_menu.caller.text = instance_menu_item.text
        instance_menu.dismiss()

    @staticmethod
    def audio_codec_menu_callback(instance_menu, instance_menu_item):
        if "default" in instance_menu_item.text:
            app.ctrl.audio_codec = None
        else:
            app.ctrl.audio_codec = instance_menu_item.text.split()[0]
        instance_menu.caller.text = instance_menu_item.text
        instance_menu.dismiss()

    @staticmethod
    def compression_menu_callback(instance_menu, instance_menu_item):
        app.ctrl.compression = instance_menu.caller.text = instance_menu_item.text
        instance_menu.dismiss()

    @staticmethod
    def scaler_menu_callback(instance_menu, instance_menu_item):
        app.ctrl.scaler = instance_menu.caller.text = instance_menu_item.text
        app.ctrl.do_again(1)
        instance_menu.dismiss()

    @staticmethod
    def mask_menu_callback(instance_menu, instance_menu_item):
        if instance_menu_item.text == "A.I.":
            app.ctrl.mask = ""
            instance_menu.caller.text = "A.I."
        else:
            app.file_manager_open()
            app.go_to = ["advanced"]
        app.ctrl.do_again(1)
        instance_menu.dismiss()

    def threads_button(self, up):
        if up:
            app.ctrl.threads = app.ctrl.p.var("threads", int) + 1
        else:
            app.ctrl.threads = app.ctrl.p.var("threads", int) - 1
        self.ids.threads_label.text = f'{app.ctrl.p.var("threads", int)} threads'

    def preview_queue(self):
        while app.sm.current == "advanced":
            sleep(1)
            if self.ids.preview_spinner.active:
                self.first_step_preview()

    def time_queue(self):
        while app.sm.current == "advanced":
            sleep(1)
            if not self.ids.time_bar.value:
                self.first_step_time()

    def first_step_preview(self):
        app.ctrl.call(2)
        app.ctrl.lock_wait("done", 2)
        self.update_preview_slider()
        self.second_step_preview()

    def second_step_preview(self):
        tim = app.ctrl.fake_get_frame / app.ctrl.p.final_clip.fps
        app.ctrl.p.processes(3, False, output=self.frame_filename, get_frame_from_time=tim)
        app.ctrl.do_lock.release()
        self.update_preview_image()
        print("Image preview updated")

    def first_step_time(self):
        app.ctrl.call(2)
        app.ctrl.lock_wait("done", 2)
        self.second_step_time()

    def second_step_time(self):
        txt = self.ids.video_codec_button.text
        ext = "mp4" if txt == "default" else txt.split(".")[-1].split(")")[0]
        filename = pjoin(self.tempdir, f"temp_video.{ext}")

        app.ctrl.p.processes(3, False, output=filename, logger=MyLogger(my_callback))
        app.ctrl.do_lock.release()

    @mainthread
    def update_preview_spinner(self, _bool):
        if _bool:
            if self.ids.preview_slider.value:
                self.ids.preview_spinner.active = True
        else:
            self.ids.preview_spinner.active = False

    @mainthread
    def update_preview_slider(self):
        self.ids.preview_slider.max = app.ctrl.p.final_clip.fps

    @mainthread
    def update_preview_image(self):
        self.ids.preview_image.reload()
        self.update_preview_spinner(False)

    @mainthread
    def update_time(self, bar, label):
        self.ids.time_bar.value = bar
        self.ids.time_label.text = label


class Monitor(MDCheckbox):
    def monitor_radio(self):
        app.ctrl.monitor = self.op


def property_callback(instance, value, var_name):
    instance.p.__dict__[var_name] = value
    write = f'"{value}"' if type(value) == str else value
    parent_class_name = type(instance).__qualname__
    class_name = type(instance.p).__qualname__
    print(f'{class_name}.{var_name} changed to {write} - at {parent_class_name}')


this_dir = dirname(abspath(__file__))


class Control(EventDispatcher):
    p = Project(pjoin(this_dir, '../data/config.json'))

    conf = {'input': (str, False),
            'output_dir': (str, False),
            'output_name': (str, False),
            'extension': (str, False),
            'video_codec': (str, True),
            'audio_codec': (str, True),
            'background': ((str, list), False),
            'relative_mask_resolution': (int, False),
            'relative_mask_fps': (int, False),
            'threads': (int, False),
            'cuda': (bool, False),
            'compression': (str, False),
            'scaler': (str, False),
            'monitor': (str, True),
            'log': (bool, False),
            'get_frame': (int, False),
            'mask': (str, False)}
    property_to = {str: StringProperty,
                   int: NumericProperty,
                   bool: BooleanProperty,
                   (str, list): ObjectProperty}

    for var_name, variable in p.__dict__.items():
        if var_name in conf.keys():
            types, allownone = conf[var_name]
            vars()[var_name] = property_to[types](variable, allownone=allownone)
            vars()['on_' + var_name] = lambda _, i, v, vn=var_name: property_callback(i, v, vn)

    ps = range(4)
    do_lock = Lock()

    fake_get_frame = NumericProperty(50)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cs = [self.call_input, self.call_mask, self.call_background, self.call_save]
        self.doing = [False for _ in self.ps]
        self.done = [False for _ in self.ps]
        do_again1 = lambda obj, value: self.do_again(1)
        self.bind(relative_mask_fps=do_again1, relative_mask_resolution=do_again1)

    def is_(self, state, ps):
        self.do_lock.acquire()
        return self.__dict__[state][ps]

    def wait(self, state, ps):
        while not self.__dict__[state][ps]:
            sleep(1)

    def lock_wait(self, state, ps):
        while not self.is_(state, ps):
            self.do_lock.release()
            sleep(1)

    def do_again(self, n):
        MyThread(target=self.do_again_base, args=(n,), exc_callback=exc_callback).start()

    def do_again_base(self, n):
        maxp = len(self.ps)
        with self.do_lock:
            for x in range(n, maxp):
                self.done[x] = self.doing[x] = False
        print(f"Processes from {n} until {maxp - 1} scheduled")

    def call(self, n):
        MyThread(target=self.cs[n], exc_callback=exc_callback).start()

    def base_call(self, n):
        if not self.done[n]:
            self.doing[n] = True
            print(f"Process {n} started")
            if n == 3:
                self.p.processes(3, False, logger=MyLogger(my_callback))
            else:
                self.p.processes(n)
            self.done[n] = True
            print(f"Process {n} finished")

    def base_check(self, needed, next_one):
        if needed is not None:
            if not self.is_("doing", needed):
                self.do_lock.release()
                self.call(needed)
            self.lock_wait("done", needed)
        else:
            self.do_lock.acquire()
        self.base_call(next_one)
        self.do_lock.release()

    def call_input(self):
        self.base_check(None, 0)
        # self.do_again(1)

    def call_mask(self):
        self.base_check(0, 1)
        # self.do_again(2)

    def call_background(self):
        self.base_check(1, 2)
        # self.do_again(3)

    def call_save(self):
        self.base_check(2, 3)


class GSE(MDApp):
    sm = advanced = None
    go_to = ["welcome"]
    ctrl = Control()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.manager_open = False
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager,
            select_path=self.select_path,
        )
        self.drawer = None

    def ready_output(self, inst):
        strs = inst.text.split(".")
        if len(strs) == 2:
            inst.hint_text = inst.text
            self.ctrl.output_name = strs[0]
            self.ctrl.extension = strs[1]
        else:
            pass  # error

    def file_manager_open(self):
        # parent = os.path.dirname(os.path.abspath(os.getcwd()))
        home = expanduser("~")
        self.file_manager.show(home)
        self.manager_open = True

    def select_path(self, path):
        self.exit_manager()
        if self.sm.current == "welcome":
            self.ctrl.input = path
            self.ctrl.do_again(0)
        elif self.sm.current == "background":
            self.ctrl.background = path
            self.ctrl.do_again(2)
        elif self.sm.current == "ready":
            self.ctrl.output_dir = pjoin(path, "")
        elif self.sm.current == "advanced":
            self.ctrl.mask = path

        self.change()

    def exit_manager(self, *args):
        self.manager_open = False
        self.file_manager.close()

    def show_date_picker(self):
        date_dialog = MDDatePicker(callback=self.get_date)
        date_dialog.open()

    def get_date(self, date):
        self.show_time_picker()

    def show_time_picker(self):
        time_dialog = MDTimePicker()
        time_dialog.bind(time=self.get_time)
        previous_time = datetime.now()
        time_dialog.set_time(previous_time)
        time_dialog.open()

    def get_time(self, instance, time):
        self.change()
        return time

    def change(self, to=None):
        if to:
            self.sm.current = to
        elif len(self.go_to) > 0:
            self.sm.current = self.go_to[-1]
            self.go_to.pop()

    def build(self):
        self.theme_cls.primary_palette = "LightGreen"
        # self.theme_cls.theme_style = "Dark"
        self.sm = ScreenManager()
        self.sm.add_widget(Welcome())
        self.sm.add_widget(Background())
        self.sm.add_widget(Colors())
        self.sm.add_widget(Time())
        self.sm.add_widget(Ready())
        self.advanced = Advanced()
        self.sm.add_widget(self.advanced)

        self.change()

        self.drawer = LeftMenu(type="standard")

        nav = MDNavigationLayout()
        nav.add_widget(self.sm)
        nav.add_widget(self.drawer)

        return nav


if __name__ == "__main__":
    Window.maximize()
    app = GSE()
    app.run()
    rmtree(app.advanced.tempdir)
