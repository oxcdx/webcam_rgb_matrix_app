import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
# Set PYTHONPATH to include the script directory
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, Response, jsonify, request, send_from_directory
import ftplib
import ssl
import threading
import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time
from datetime import datetime

UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates')
STATIC_PATH = os.path.join(BASE_DIR, 'static')

context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

FTP_HOST = "ftp.oc-d.co.uk"
FTP_USER = "tracingtogetherauto@oc-d.co.uk"
FTP_PASS = "72lrqnvrw387"
FTP_TARGET_DIR = "screenshots"

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
last_captured_mosaic_path = None
display_captured = False
display_lock = threading.Lock()

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

        # Decide what to display on the matrix
        with display_lock:
            use_captured = display_captured
            captured_path = last_captured_mosaic_path

        if use_captured and captured_path and os.path.exists(captured_path):
            img = cv2.imread(captured_path)
            if img is not None:
                # Apply effects using current effect_params
                with params_lock:
                    brightness = effect_params.get("brightness", 1.0)
                    contrast = effect_params.get("contrast", 1.0)
                    saturation = effect_params.get("saturation", 1.0)
                    hue_shift = int(effect_params.get("hue_shift", 0))
                    colorize = int(effect_params.get("colorize", 0))
                img = img.astype('float32') / 255.0
                img = img * contrast + (brightness - 1.0)
                img = np.clip(img, 0, 1)
                img_hsv = cv2.cvtColor((img * 255).astype('uint8'), cv2.COLOR_BGR2HSV).astype('float32')
                img_hsv[..., 1] *= saturation
                img_hsv[..., 1] = np.clip(img_hsv[..., 1], 0, 255)
                if colorize:
                    img_hsv[..., 0] = hue_shift
                else:
                    if hue_shift != 0:
                        img_hsv[..., 0] = (img_hsv[..., 0] + hue_shift) % 180
                img = cv2.cvtColor(img_hsv.astype('uint8'), cv2.COLOR_HSV2BGR).astype('float32') / 255.0
                img = (img * 255).astype('uint8')
                img_resized = cv2.resize(img, (32, 32))
                frame_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                try:
                    matrix.SetImage(image)
                except Exception as e:
                    print(f"SetImage error: {e}")
            else:
                print("Failed to load captured mosaic image.")
        else:
            # Display live mosaic as before
            try:
                resized = cv2.resize(cropped, (32, 32))
                frame_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                matrix.SetImage(image)
            except Exception as e:
                print(f"Matrix live display error: {e}")
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

@app.route("/capture_image", methods=["POST"])
def capture_image():
    global latest_frame, mosaic_frame, last_captured_mosaic_path, display_captured
    data = request.json
    base = data.get("base", "").strip()
    if not base:
        return jsonify(success=False, error="Missing base name")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    folder = f"{timestamp}-{base}"
    save_dir = os.path.join(UPLOAD_ROOT, folder)
    os.makedirs(save_dir, exist_ok=True)
    with frame_lock:
        main_img = latest_frame.copy() if latest_frame is not None else None
        mosaic_img = mosaic_frame.copy() if mosaic_frame is not None else None
    if main_img is None or mosaic_img is None:
        return jsonify(success=False, error="No image available")
    main_path = os.path.join(save_dir, f"{timestamp}-{base}.jpg")
    mosaic_path = os.path.join(save_dir, f"{timestamp}-{base}-mosaic.jpg")
    cv2.imwrite(main_path, main_img)
    cv2.imwrite(mosaic_path, mosaic_img)
    # Set the captured mosaic path and flag
    with display_lock:
        last_captured_mosaic_path = mosaic_path
        display_captured = True
    return jsonify(success=True, folder=folder)

@app.route("/uploads/<folder>/<filename>")
def uploaded_file(folder, filename):
    return send_from_directory(os.path.join(UPLOAD_ROOT, folder), filename)

@app.route("/processed_mosaic/<folder>/<filename>")
def processed_mosaic(folder, filename):
    brightness = float(request.args.get("brightness", 1.0))
    contrast = float(request.args.get("contrast", 1.0))
    saturation = float(request.args.get("saturation", 1.0))
    hue_shift = int(request.args.get("hue_shift", 0))
    colorize = int(request.args.get("colorize", 0))

    img_path = os.path.join(UPLOAD_ROOT, folder, filename)
    if not os.path.exists(img_path):
        return "", 404

    img = cv2.imread(img_path)
    if img is None:
        return "", 404

    img = img.astype('float32') / 255.0
    img = img * contrast + (brightness - 1.0)
    img = np.clip(img, 0, 1)
    img_hsv = cv2.cvtColor((img * 255).astype('uint8'), cv2.COLOR_BGR2HSV).astype('float32')
    img_hsv[..., 1] *= saturation
    img_hsv[..., 1] = np.clip(img_hsv[..., 1], 0, 255)
    if colorize:
        # Set all hue to the selected value, keep value and saturation
        img_hsv[..., 0] = hue_shift
    else:
        if hue_shift != 0:
            img_hsv[..., 0] = (img_hsv[..., 0] + hue_shift) % 180
    img = cv2.cvtColor(img_hsv.astype('uint8'), cv2.COLOR_HSV2BGR).astype('float32') / 255.0
    img = (img * 255).astype('uint8')

    _, buffer = cv2.imencode('.jpg', img)
    return Response(buffer.tobytes(), mimetype='image/jpeg')
    
@app.route("/matrix_live")
def matrix_live():
    global display_captured
    with display_lock:
        display_captured = False
    return jsonify(success=True)

@app.route("/matrix_edit")
def matrix_edit():
    global display_captured
    with display_lock:
        display_captured = True
    return jsonify(success=True)

@app.route("/set_matrix_effect_params", methods=["POST"])
def set_matrix_effect_params():
    global effect_params
    data = request.json
    with params_lock:
        effect_params["brightness"] = float(data.get("brightness", 1.0))
        effect_params["contrast"] = float(data.get("contrast", 1.0))
        effect_params["saturation"] = float(data.get("saturation", 1.0))
        effect_params["hue_shift"] = int(data.get("hue_shift", 0))
        effect_params["colorize"] = int(data.get("colorize", 0))
    return jsonify(success=True)

@app.route("/save_final_image", methods=["POST"])
def save_final_image():
    data = request.json
    folder = data.get("folder")
    filename = data.get("filename")
    params = data.get("params", {})
    if not folder or not filename:
        return jsonify(success=False, error="Missing folder or filename")

    img_path = os.path.join(UPLOAD_ROOT, folder, filename)
    if not os.path.exists(img_path):
        return jsonify(success=False, error="Image not found")

    # Get effect parameters
    brightness = float(params.get("brightness", 1.0))
    contrast = float(params.get("contrast", 1.0))
    saturation = float(params.get("saturation", 1.0))
    hue_shift = int(params.get("hue_shift", 0))
    colorize = int(params.get("colorize", 0))

    img = cv2.imread(img_path)
    if img is None:
        return jsonify(success=False, error="Failed to load image")

    # Apply effects (same as in processed_mosaic)
    img = img.astype('float32') / 255.0
    img = img * contrast + (brightness - 1.0)
    img = np.clip(img, 0, 1)
    img_hsv = cv2.cvtColor((img * 255).astype('uint8'), cv2.COLOR_BGR2HSV).astype('float32')
    img_hsv[..., 1] *= saturation
    img_hsv[..., 1] = np.clip(img_hsv[..., 1], 0, 255)
    if colorize:
        img_hsv[..., 0] = hue_shift
    else:
        if hue_shift != 0:
            img_hsv[..., 0] = (img_hsv[..., 0] + hue_shift) % 180
    img = cv2.cvtColor(img_hsv.astype('uint8'), cv2.COLOR_HSV2BGR).astype('float32') / 255.0
    img = (img * 255).astype('uint8')

    # Save as -final.jpg
    base, ext = os.path.splitext(filename)
    final_filename = f"{base}-final.jpg"
    final_path = os.path.join(UPLOAD_ROOT, folder, final_filename)
    cv2.imwrite(final_path, img)

    # --- FTP upload ---
    try:
        with ftplib.FTP_TLS(context=context) as ftp:
            ftp.connect("77.72.2.82", 21)
            ftp.login("tracingtogetherauto@oc-d.co.uk", "72lrqnvrw387")
            ftp.prot_p()
            ftp.cwd("screenshots")
            with open(final_path, "rb") as f:
                ftp.storbinary(f"STOR {final_filename}", f)
    except Exception as e:
        return jsonify(success=False, error=f"FTP upload failed: {e}")

    return jsonify(success=True, path=final_path)

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