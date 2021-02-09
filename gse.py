from torch.hub import load as hub_load
from torch import FloatTensor, no_grad, tanh, ones_like
from torch.cuda import is_available as cuda_available
from torch.nn.functional import relu, conv2d, hardtanh
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from torchvision.transforms import Compose, Normalize
from json import load as jload
from json import dump as jdump
from moviepy.video.fx.loop import loop
from moviepy.video.fx.resize import resize
from time import perf_counter
from imghdr import what as is_image
from dill import dump as ddump
from dill import load as dload
from os.path import dirname, basename, splitext, abspath
from os.path import join as join_path
from ast import literal_eval
from typing import Union, Optional, Callable, Any, IO, Iterable, NewType, List
from os import PathLike
from numpy import ndarray


class MakeMask:
    def __init__(self, cuda: bool):

        self.cuda = cuda
        self.model = hub_load('pytorch/vision', 'deeplabv3_resnet101', pretrained=True)
        self.people_class = 15

        self.model.eval()
        print("Model Loaded")

        self.blur = FloatTensor([[[[1.0, 2.0, 1.0], [2.0, 4.0, 2.0], [1.0, 2.0, 1.0]]]]) / 16.0

        # move the input and model to GPU for speed if available ?
        if self.cuda and cuda_available():
            print("Using GPU (CUDA) to process the images")
            self.model.to('cuda')
            self.blur = self.blur.to('cuda')

        self.preprocess = Compose(
            [Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), ])

    def __call__(self, img: ndarray) -> ndarray:
        frame_data = FloatTensor(img) / 255.0

        input_tensor = self.preprocess(frame_data.permute(2, 0, 1))
        input_batch = input_tensor.unsqueeze(0)  # create a mini-batch as expected by the model

        # move the input and model to GPU for speed if available ?
        if self.cuda and cuda_available():
            input_batch = input_batch.to('cuda')

        with no_grad():
            output = self.model(input_batch)['out'][0]

        segmentation = output.argmax(0)

        bgout = output[0:1][:][:]
        a = (1.0 - relu(tanh(bgout * 0.30 - 1.0))).pow(0.5) * 2.0

        people = segmentation.eq(ones_like(segmentation).long().fill_(self.people_class)).float()

        people.unsqueeze_(0).unsqueeze_(0)

        for i in range(3):
            people = conv2d(people, self.blur, stride=1, padding=1)

        # combined_mask = tnf.hardtanh(a * b)
        combined_mask = relu(hardtanh(a * (people.squeeze().pow(1.5))))
        combined_mask = combined_mask.expand(1, 3, -1, -1)

        newimg = (combined_mask * 255.0).cpu().squeeze().byte().permute(1, 2, 0).numpy()

        return newimg


ClipType = Union[VideoFileClip, ImageClip]
FinalClipType = NewType('FinalClipType', Union[ClipType, CompositeVideoClip])
PathType = Union[str, bytes, PathLike]


def get_input_clip(path: PathType, **videofileclip_args) -> ClipType:
    if is_image(path):
        print(f"Loading {path} as the main image source")
        return ImageClip(path, duration=1).set_fps(1)
    else:
        print(f"Loading {path} as the main video source")
        return VideoFileClip(path, **videofileclip_args)


def get_mask_clip(input_clip: ClipType, relative_mask_fps: int = 100, relative_mask_resolution: int = 100,
                  mask_path: PathType = "", cuda: bool = True, **videofileclip_args) -> ClipType:
    if mask_path != "":  # if given
        if is_image(mask_path):
            print(f"Loading the image {mask_path} as the mask for {input_clip.filename}")
            return ImageClip(mask_path, duration=input_clip.duration)
        else:
            print(f"Loading the video {mask_path} as the mask for {input_clip.filename}")
            return VideoFileClip(mask_path, **videofileclip_args) \
                .fx(loop, duration=input_clip.duration).set_duration(input_clip.duration)
    else:  # if should be result of A.I.
        process_clip = input_clip.copy()
        fps = relative_mask_fps * 0.01
        if fps != 1:  # if asked to change fps
            newfps = input_clip.fps * fps
            process_clip = process_clip.set_fps(newfps)
            print(f"Mask fps decreased in {(1 - fps) * 100}%. {process_clip.fps}fps now")
        res = relative_mask_resolution * 0.01
        if res != 1:  # if asked to resize
            process_clip = process_clip.fx(resize, res)
            w, h = process_clip.size
            print(f"Mask resolution decreased in {(1 - res) * 100}%, {w}x{h} now")
        return process_clip.fl_image(MakeMask(cuda))


def get_final_clip(mask_clip: ClipType, input_clip: ClipType, background: Union[List[float], PathType],
                   **videofileclip_args) -> FinalClipType:
    if background != "":
        usable_mask = mask_clip.fx(resize, input_clip.size).to_mask()
        masked_clip = input_clip.set_mask(usable_mask)
        if type(background) == list:  # if color
            rgb = (background[0], background[1], background[2])
            print(f"Using the RGB color {rgb} as the background of {input_clip.filename}")
            to_return = masked_clip.on_color(color=rgb)
        elif is_image(background):
            print(f"Using {background} as image source to the background of {input_clip.filename}")
            background_clip = ImageClip(background, duration=masked_clip.duration)
            to_return = smooth_composite(background_clip, masked_clip)
        else:
            print(f"Using {background} as video source to the background of {input_clip.filename}")
            background_clip = VideoFileClip(background, **videofileclip_args) \
                .fx(loop, duration=masked_clip.duration).set_duration(input_clip.duration)
            to_return = smooth_composite(background_clip, masked_clip)
        to_return.filename = input_clip.filename
        return to_return
    else:
        print("No background selected, skipping compositing")
        return mask_clip


def smooth_composite(back: ClipType, front: ClipType):
    wf, hf = front.size
    wb, hb = back.size
    rf = wf / hf
    rb = wb / hb
    if rf > rb:
        back = back.fx(resize, width=wf)
    else:
        back = back.fx(resize, height=hf)
    return CompositeVideoClip([back, front.set_position("center")], size=front.size)


def save_to_file(clip: FinalClipType, path: PathType, frame_from_time: int = 0, frame: int = 0,
                 alpha: bool = False, **write_videofile_args):
    if is_image(clip.filename) or frame or frame_from_time:
        if frame:
            frame_from_time = clip.fps / frame
        elif not frame_from_time:
            frame_from_time = clip.duration / 2
        print(f'Saving as image to {path}')
        clip.save_frame(path, t=frame_from_time, withmask=alpha)
    else:
        temp_audiofile = abspath(join_path(dirname(path), splitext(basename(path))[0] + '.mp3'))
        clip.write_videofile(path, temp_audiofile=temp_audiofile, **write_videofile_args)


class Project:
    def __init__(self, config: Optional[PathType] = None):
        self.input_clip = self.mask_clip = self.final_clip = None
        self.audio = True
        if config:
            self.load(config)

    def var(self, var: str, converter: Union[type, str, None] = None, asker: Callable[[str], Any] = input) -> Any:
        if var in self.__dict__.keys():
            return self.__dict__[var]
        if asker == input:
            to_return = input(f'Variable {var}: ')
        else:
            to_return = asker(var)
        if not converter:
            return to_return
        elif converter == "auto":
            try:
                return literal_eval(to_return)
            except (ValueError, SyntaxError):
                return to_return
        else:
            return converter(to_return)

    @staticmethod
    def serialize(obj):
        obj_type = type(obj).__qualname__
        return f'<<non-serializable {obj_type}>>'

    def save(self, path: Union[IO[str], PathType]) -> None:
        file_type = splitext(path)[1]
        with open(f'{path}', "wb") as project_file:
            if file_type == ".gse":
                ddump(self, project_file)
            elif file_type == ".json":
                jdump(self.__dict__, path, default=self.serialize)
                print(f'Attention: .json projects do not keep non-serializable variables.')
            else:
                raise Exception(f'Impossible to load file with extension "{file_type}". Accepted: ".gse" and ".json"')
        print(f'Saved to {path}\n{self.__dict__}')

    def load(self, path: PathType) -> None:
        file_type = splitext(path)[1]
        with open(path, "rb") as project_file:
            if file_type == ".gse":
                self.__dict__.update(dload(project_file).__dict__)
            elif file_type == ".json":
                for var_name, value in jload(project_file).items():
                    if var_name[0] == '_' or (type(value) == str and value[:18] == '<<non-serializable'):
                        pass
                    else:
                        self.__dict__[var_name] = value
            else:
                raise Exception(f'Impossible to load file with extension "{file_type}". Accepted: ".gse" and ".json"')
        print(f'Loaded from {path}\n{self.__dict__}')

    def processes(self, processes: Iterable[int] = range(4), asker: Callable[[Any], Any] = input, **update_args):
        if 0 in processes:
            args = {"path": self.var("input", str, asker=asker),
                    "resize_algorithm": self.var("scaler", str, asker=asker)}

            args.update(update_args)

            self.input_clip = get_input_clip(**args)
        if 1 in processes:
            args = {"input_clip": self.input_clip,
                    "relative_mask_fps": self.var("relative_mask_fps", int, asker),
                    "relative_mask_resolution": self.var("relative_mask_resolution", int, asker),
                    "mask_path": self.var("mask", str, asker),
                    "cuda": self.var("cuda", bool, asker),
                    "resize_algorithm": self.var("scaler", str, asker)}

            args.update(update_args)

            self.mask_clip = get_mask_clip(**args)
        if 2 in processes:
            if self.var("background", "auto", asker) == "":
                self.audio = False

            args = {"mask_clip": self.mask_clip,
                    "input_clip": self.input_clip,
                    "background": self.var("background", "auto", asker),
                    "resize_algorithm": self.var("scaler", str, asker)}

            args.update(update_args)

            self.final_clip = get_final_clip(**args)
        if 3 in processes:
            file = '.'.join([self.var("output_name", str, asker), self.var("extension", str, asker)])
            path = abspath(join_path(self.var("output_dir", str, asker), file))

            args = {"clip": self.final_clip,
                    "path": path,
                    "frame": self.var("get_frame", int, asker),
                    "preset": self.var("compression", str, asker),
                    "audio": self.audio,
                    "write_logfile": self.var("log", bool, asker),
                    "threads": self.var("threads", int, asker)}
            if self.var("video_codec", "auto", asker):
                args["codec"] = self.var("video_codec", str, asker)
            if self.var("audio_codec", "auto", asker):
                args["audio_codec"] = self.var("audio_codec", str, asker)

            args.update(update_args)

            save_to_file(**args)


class Timer:
    def __init__(self):
        self.hours = self.minutes = self.seconds = self.starttime = self.stoptime = 0
        self.start()

    def start(self):
        self.starttime = self.stoptime = perf_counter()

    def stop(self):
        self.stoptime = perf_counter()

    def sec_duration(self):
        return self.stoptime - self.starttime

    def set_hours(self):
        duration = self.sec_duration()
        if duration > 3600:
            self.hours = duration / 3600
            self.minutes = (duration % 3600) / 60
            self.seconds = (duration % 3600) % 60
        elif duration > 60:
            self.minutes = (duration % 3600) / 60
            self.seconds = (duration % 3600) % 60
        else:
            self.seconds = duration

    def print_time(self):
        print(f"Finished in {int(self.hours)} hour(s), {int(self.minutes)} minute(s) and {int(self.seconds)} second(s)")

    def finish(self):
        self.stop()
        self.set_hours()
        self.print_time()


if __name__ == '__main__':
    t = Timer()

    p = Project("config.json")
    p.processes()

    t.finish()
