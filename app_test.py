import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
# Set PYTHONPATH to include the script directory
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, Response
import threading
import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time


TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates')
STATIC_PATH = os.path.join(BASE_DIR, 'static')

print("BASE_DIR:", BASE_DIR)
print("TEMPLATE_PATH:", TEMPLATE_PATH)
print("Templates:", os.listdir(TEMPLATE_PATH))

app = Flask(__name__,
            template_folder=TEMPLATE_PATH,
            static_folder=STATIC_PATH)

# app = Flask(__name__)

latest_frame = None
frame_lock = threading.Lock()

def gen_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_frame)
            if not ret:
                continue
            frameWeb = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frameWeb + b'\r\n')
        else:
            time.sleep(0.01)

def matrix_loop():
    global latest_frame
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

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        with frame_lock:
            latest_frame = frame.copy()
        time.sleep(0.01)

        h, w = latest_frame.shape[:2]
        min_dim = min(h, w)
        if min_dim <= 0:
            continue

        start_x = max((w - min_dim) // 2, 0)
        start_y = max((h - min_dim) // 2, 0)

        cropped = latest_frame[start_y:start_y+min_dim, start_x:start_x+min_dim]
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

@app.route("/")
def hello():
    return render_template("test.html")

@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

def run_flask():
    print("CWD:", os.getcwd())
    print("Template folder:", app.template_folder)
    print("Templates:", os.listdir(app.template_folder))
    app.run(debug=False, use_reloader=False, port=5000)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    matrix_loop()