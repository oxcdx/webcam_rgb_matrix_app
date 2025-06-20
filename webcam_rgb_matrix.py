import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image

def main():
    pipeline = (
        "v4l2src device=/dev/video0 ! "
        "video/x-raw,width=320,height=180 ! "
        "videoconvert ! appsink"
    )

    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    options = RGBMatrixOptions()
    options.rows = 16
    options.cols = 32
    options.chain_length = 2
    options.hardware_mapping = 'adafruit-hat'
    options.pixel_mapper_config = "U-mapper"
    options.pwm_bits = 6
    options.pwm_lsb_nanoseconds = 800
    options.brightness = 50

    matrix = RGBMatrix(options=options)

    if not cap.isOpened():
        print("Cannot open camera")
        return

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            h, w = frame.shape[:2]
            min_dim = min(h, w)
            if min_dim <= 0:
                continue

            start_x = max((w - min_dim) // 2, 0)
            start_y = max((h - min_dim) // 2, 0)

            cropped = frame[start_y:start_y+min_dim, start_x:start_x+min_dim]
            if cropped.shape[0] <= 0 or cropped.shape[1] <= 0:
                continue

            try:
                resized = cv2.resize(cropped, (32, 32))
            except Exception as e:
                print(f"Resize error: {e}")
                continue

            if resized.shape[0] != 32 or resized.shape[1] != 32:
                print(f"Resized shape invalid: {resized.shape}")
                continue

            try:
                frame_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
            except Exception as e:
                print(f"Image conversion error: {e}")
                continue

            if image.size != (32, 32):
                print(f"Image size invalid: {image.size}")
                continue

            try:
                matrix.SetImage(image)
            except Exception as e:
                print(f"SetImage error: {e}")
                continue

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        matrix.Clear()

if __name__ == "__main__":
    main()