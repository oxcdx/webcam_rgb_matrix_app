import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
# Set PYTHONPATH to include the script directory
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, Response, jsonify, request
import threading
import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time


TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates')
STATIC_PATH = os.path.join(BASE_DIR, 'static')

app = Flask(__name__,
            template_folder=TEMPLATE_PATH,
            static_folder=STATIC_PATH)

# app = Flask(__name__)

latest_frame = None
mosaic_frame = None
frame_lock = threading.Lock()
effect_params = {
    "brightness": 1.0,
    "contrast": 1.0,
    "saturation": 1.0,
    "blur": 0
}
params_lock = threading.Lock()

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
    global mosaic_frame
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

        # --- Mosaic generation ---
        small = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_LINEAR)
        mosaic = cv2.resize(small, (min_dim, min_dim), interpolation=cv2.INTER_NEAREST)
        with frame_lock:
            mosaic_frame = mosaic.copy()
        # --- End mosaic generation ---

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

@app.route("/video_feed_mosaic")
def video_feed_mosaic():
    def gen_mosaic_frames():
        global mosaic_frame
        while True:
            with frame_lock:
                frame = mosaic_frame.copy() if mosaic_frame is not None else None
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                frameWeb = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frameWeb + b'\r\n')
            else:
                time.sleep(0.01)
    return Response(gen_mosaic_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/video_feed_effect")
def video_feed_effect():
    def gen_effect_frames():
        global mosaic_frame, effect_params
        while True:
            with frame_lock:
                frame = mosaic_frame.copy() if mosaic_frame is not None else None
            if frame is not None:
                with params_lock:
                    brightness = effect_params["brightness"]
                    contrast = effect_params["contrast"]
                    saturation = effect_params["saturation"]
                    blur = effect_params["blur"]

                # Convert to float32 for processing
                img = frame.astype('float32') / 255.0

                # Apply brightness and contrast
                img = img * contrast + (brightness - 1.0)
                img = np.clip(img, 0, 1)

                # Convert to HSV for saturation
                img_hsv = cv2.cvtColor((img * 255).astype('uint8'), cv2.COLOR_BGR2HSV).astype('float32')
                img_hsv[..., 1] *= saturation
                img_hsv[..., 1] = np.clip(img_hsv[..., 1], 0, 255)
                img = cv2.cvtColor(img_hsv.astype('uint8'), cv2.COLOR_HSV2BGR).astype('float32') / 255.0

                # Convert back to uint8
                img = (img * 255).astype('uint8')

                # Apply blur
                if blur > 0:
                    img = cv2.GaussianBlur(img, (blur*2+1, blur*2+1), 0)

                ret, buffer = cv2.imencode('.jpg', img)
                if not ret:
                    continue
                frameWeb = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frameWeb + b'\r\n')
            else:
                time.sleep(0.01)
    return Response(gen_effect_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/set_effect_params", methods=["POST"])
def set_effect_params():
    global effect_params
    data = request.json
    with params_lock:
        effect_params["brightness"] = float(data.get("brightness", 1.0))
        effect_params["contrast"] = float(data.get("contrast", 1.0))
        effect_params["saturation"] = float(data.get("saturation", 1.0))
        effect_params["blur"] = int(data.get("blur", 0))
    return jsonify(success=True)

@app.route("/")
def hello():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

def run_flask():
    app.run(debug=True, use_reloader=False, port=5000)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    matrix_loop()