import os
import time

import cv2
import numpy as np
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(
    BASE_DIR,
    "uploads",
    "20260715164526-church",
    "20260715174402-church-mosaic.jpg",
)


def build_matrix() -> RGBMatrix:
    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 32
    options.chain_length = 1
    options.hardware_mapping = "adafruit-hat"
    options.led_rgb_sequence = "GBR"
    options.pwm_bits = 11
    options.gpio_slowdown = 1
    options.pwm_lsb_nanoseconds = 55
    options.pwm_dither_bits = 1
    options.brightness = 100
    return RGBMatrix(options=options)


def load_image(path: str) -> np.ndarray:
    image = cv2.imread(path)
    if image is None:
        raise FileNotFoundError(f"Could not load image: {path}")
    return image


def prepare_image(image: np.ndarray) -> Image.Image:
    height, width = image.shape[:2]
    min_dim = min(height, width)
    start_x = max((width - min_dim) // 2, 0)
    start_y = max((height - min_dim) // 2, 0)
    cropped = image[start_y:start_y + min_dim, start_x:start_x + min_dim]
    resized = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_AREA)
    tiled = np.concatenate([resized, resized, resized, resized], axis=1)
    rgb = cv2.cvtColor(tiled, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def main() -> None:
    matrix = build_matrix()
    image = load_image(IMAGE_PATH)
    matrix_image = prepare_image(image)

    while True:
        matrix.SetImage(matrix_image)
        time.sleep(1)


if __name__ == "__main__":
    main()
