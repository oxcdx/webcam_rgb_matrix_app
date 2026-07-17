import os
import sys

from requests import options
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, '.env.local'))
# Set PYTHONPATH to include the script directory
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, Response, jsonify, request, send_from_directory
from jinja2 import FileSystemLoader
import ftplib
import ssl
import threading
import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import time
from datetime import datetime
import base64
import io

isSavingToFTP = True

DEFAULT_EFFECT_PARAMS = {
    "brightness": 1.0,
    "contrast": 1.0,
    "saturation": 1.0,
    "blur": 0,
    "highlights": 0.0,
    "hue_shift": 0,
    "colorize": 0,
    "invert": 0,
}

UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates')
STATIC_PATH = os.path.join(BASE_DIR, 'static')

context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_PORT = int(os.environ.get("FTP_PORT", "21"))
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
FTP_TARGET_DIR = os.environ.get("FTP_TARGET_DIR", "eastbury-screenshots")

app = Flask(__name__,
            template_folder=TEMPLATE_PATH,
            static_folder=STATIC_PATH)
app.jinja_loader = FileSystemLoader(TEMPLATE_PATH)

# app = Flask(__name__)

latest_frame = None
mosaic_frame = None
# A Condition (not just a Lock) so the web preview streams can block with zero
# CPU usage until latest_frame/mosaic_frame actually change, instead of
# polling on a timer.
frame_lock = threading.Condition()
# Bumped every time latest_frame/mosaic_frame actually change. Combined with
# frame_lock.notify_all(), this lets preview streams wait for real changes
# instead of continuously re-encoding a static frame (which competes for
# CPU/GIL with the matrix's real-time refresh and causes flicker).
frame_version = 0
# Set whenever something the matrix should react to changes (new capture/
# upload, slider released, button clicked, mode toggled). matrix_loop blocks
# on this with zero CPU instead of re-sending a still image on a timer - there
# should never be any "animation" while a still image is being shown.
display_update_event = threading.Event()
effect_params = dict(DEFAULT_EFFECT_PARAMS)
params_lock = threading.Lock()
last_captured_mosaic_path = None
display_captured = False
display_lock = threading.Lock()
matrix_still_image = None
matrix_still_lock = threading.Lock()
# Bumped every time a new image becomes the "current" one (upload or capture).
# Used to detect and ignore stale /set_matrix_effect_params requests that were
# queued for a previous image but only complete after a newer image replaced it.
capture_generation = 0

# Scanner mode configuration
USE_SCANNER_MODE = True  # Set to True to use scanner instead of webcam
scanner_image = None
scanner_filename = None  # Store the current scanner image filename
scanner_lock = threading.Lock()
scanner_frame_version = 0  # Bumped whenever a new scanner image is uploaded

# Cached still-image render for the scanner mode preview (not the effects editor).
# The scanner image is static once uploaded, so the matrix loop should only
# rebuild/re-send it when it actually changes - not on every loop iteration.
matrix_scanner_image = None
matrix_scanner_version = None
matrix_scanner_lock = threading.Lock()


def reset_effect_params():
    with params_lock:
        effect_params.clear()
        effect_params.update(DEFAULT_EFFECT_PARAMS)
    print(f"[effects] reset_effect_params -> {effect_params}", flush=True)
    return dict(effect_params)


def apply_effects_to_bgr(img, params):
    brightness = float(params.get("brightness", 1.0))
    contrast = float(params.get("contrast", 1.0))
    saturation = float(params.get("saturation", 1.0))
    blur = int(params.get("blur", 0))
    highlights = float(params.get("highlights", 0.0))
    hue_shift = int(params.get("hue_shift", 0))
    colorize = int(params.get("colorize", 0))
    invert = int(params.get("invert", 0))

    img = img.astype('float32') / 255.0
    img = img * contrast + (brightness - 1.0)
    img = np.clip(img, 0, 1)

    if invert:
        img = 1.0 - img

    neutral_source = np.clip(img * 255.0, 0, 255).astype('uint8')
    channel_spread = np.max(neutral_source, axis=2).astype('int16') - np.min(neutral_source, axis=2).astype('int16')
    neutral_mask = channel_spread <= 10
    luminance = neutral_source.astype('float32').mean(axis=2) / 255.0

    if highlights > 0:
        highlight_mask = np.clip((luminance - 0.35) / 0.65, 0, 1)
        highlight_mask = (highlight_mask * highlight_mask) * neutral_mask.astype('float32')
        darken = 1.0 - np.clip(1.8 * highlights, 0, 1.0)
        img *= 1.0 - (1.0 - darken) * highlight_mask[..., None]
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

    if blur > 0:
        img = cv2.GaussianBlur(img, (blur * 2 + 1, blur * 2 + 1), 0)

    return img

def gen_frames():
    global latest_frame
    last_sent_version = -1
    while True:
        with frame_lock:
            while frame_version == last_sent_version:
                frame_lock.wait()
            current_version = frame_version
            frame = latest_frame.copy() if latest_frame is not None else None
        if frame is not None:
            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                frameWeb = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frameWeb)).encode() + b'\r\n\r\n' + frameWeb + b'\r\n')
        last_sent_version = current_version


def build_matrix_still_image(image_path, params):
    img = cv2.imread(image_path)
    if img is None:
        return None

    img = apply_effects_to_bgr(img, params)

    height, width = img.shape[:2]
    min_dim = min(height, width)
    if min_dim <= 0:
        return None

    start_x = max((width - min_dim) // 2, 0)
    start_y = max((height - min_dim) // 2, 0)
    cropped = img[start_y:start_y + min_dim, start_x:start_x + min_dim]
    resized = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_AREA)
    tiled = np.concatenate([resized, resized, resized, resized], axis=1)
    frame_rgb = cv2.cvtColor(tiled, cv2.COLOR_BGR2RGB)
    return Image.fromarray(frame_rgb)


def build_tiled_mosaic_image(img):
    if img is None:
        return None

    height, width = img.shape[:2]
    min_dim = min(height, width)
    if min_dim <= 0:
        return None

    start_x = max((width - min_dim) // 2, 0)
    start_y = max((height - min_dim) // 2, 0)
    cropped = img[start_y:start_y + min_dim, start_x:start_x + min_dim]
    if cropped.shape[0] <= 0 or cropped.shape[1] <= 0:
        return None

    small = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (min_dim, min_dim), interpolation=cv2.INTER_NEAREST)

def auto_crop_scanned_drawing(img):
    """Detect the black square drawing border on an A4 portrait scan and
    return a straightened, cropped, then 90-degree-right-rotated image.

    Expected geometry (A4 portrait, ~21cm wide):
      - square ~11.8-12.5cm x 11.8-12.5cm
      - ~1cm from top, ~4.5cm from left, ~4cm from right
    The actual scan can be off by a few mm and rotated by 1-2 degrees, so we
    search a generous region around the expected location, find the black
    square via contour detection, and use its precise corner points to both
    straighten (rotate) and tightly crop the image (no left-over white
    margin). Falls back to the fixed-offset crop if detection fails.
    """
    h, w = img.shape[:2]
    pixels_per_cm = w / 21.0

    expected_left = 4.5 * pixels_per_cm
    expected_top = 1.0 * pixels_per_cm
    expected_size = 12.2 * pixels_per_cm
    margin = 2.5 * pixels_per_cm  # generous search slack for scanner misalignment

    roi_x0 = max(int(expected_left - margin), 0)
    roi_y0 = max(int(expected_top - margin), 0)
    roi_x1 = min(int(expected_left + expected_size + margin), w)
    roi_y1 = min(int(expected_top + expected_size + margin), h)

    roi = img[roi_y0:roi_y1, roi_x0:roi_x1]
    if roi.shape[0] <= 0 or roi.shape[1] <= 0:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # Otsu picks a threshold adaptively per-scan instead of a fixed guess, so
    # the border is reliably captured across different scanner exposures.
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Close small gaps in the border line (dust, faint ink, JPEG artifacts)
    # so it forms one continuous closed loop for contour detection.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    expected_area = expected_size * expected_size
    best_rect = None
    best_contour = None
    best_score = None
    for c in contours:
        area = cv2.contourArea(c)
        if area < expected_area * 0.3 or area > expected_area * 2.5:
            continue
        rect = cv2.minAreaRect(c)  # ((cx, cy), (rw, rh), angle)
        rw, rh = rect[1]
        if rw <= 0 or rh <= 0:
            continue
        if max(rw, rh) / min(rw, rh) > 1.25:
            continue  # not square-ish enough
        score = abs(area - expected_area)
        if best_score is None or score < best_score:
            best_score = score
            best_rect = rect
            best_contour = c

    if best_rect is None:
        left_offset_px = int(expected_left)
        top_offset_px = int(expected_top)
        crop_size_px = int(expected_size)
        right_edge = min(left_offset_px + crop_size_px, w)
        bottom_edge = min(top_offset_px + crop_size_px, h)
        cropped = img
        if right_edge > left_offset_px and bottom_edge > top_offset_px:
            cropped = img[top_offset_px:bottom_edge, left_offset_px:right_edge]
        return cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)

    (cx_roi, cy_roi), (rw, rh), angle = best_rect
    if rw < rh:
        angle += 90
    if angle > 45:
        angle -= 90
    if abs(angle) > 5:
        angle = 0  # implausible skew - likely a false match, don't rotate

    cx, cy = cx_roi + roi_x0, cy_roi + roi_y0

    rot_mat = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    rotated_full = cv2.warpAffine(img, rot_mat, (w, h), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REPLICATE)

    # Transform the detected contour's own points (not just an approximate
    # average side length) into the straightened image's coordinate space,
    # then take a tight axis-aligned bounding box of them. This crops exactly
    # to the black border with no left-over white margin, and doesn't force
    # a perfectly square result if the detected border wasn't perfectly square.
    contour_full = best_contour.reshape(-1, 2).astype('float32') + np.array([roi_x0, roi_y0], dtype='float32')
    ones = np.ones((contour_full.shape[0], 1), dtype='float32')
    contour_h = np.hstack([contour_full, ones])
    rotated_pts = contour_h @ rot_mat.T

    x0 = int(round(rotated_pts[:, 0].min()))
    y0 = int(round(rotated_pts[:, 1].min()))
    x1 = int(round(rotated_pts[:, 0].max()))
    y1 = int(round(rotated_pts[:, 1].max()))

    x0c, y0c, x1c, y1c = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if x1c <= x0c or y1c <= y0c:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    cropped = rotated_full[y0c:y1c, x0c:x1c]
    return cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)

def refresh_matrix_still_image():
    global matrix_still_image
    with display_lock:
        use_captured = display_captured
        captured_path = last_captured_mosaic_path
        generation = capture_generation

    if not use_captured or not captured_path or not os.path.exists(captured_path):
        with display_lock:
            if capture_generation != generation:
                # A newer capture/upload superseded this one while we were
                # checking - let its own refresh call be the source of truth.
                return
        with matrix_still_lock:
            matrix_still_image = None
        return

    with params_lock:
        params = dict(effect_params)

    still_image = build_matrix_still_image(captured_path, params)

    with display_lock:
        if capture_generation != generation:
            # A newer capture/upload completed while this (now stale) build
            # was running - discard it so it can't clobber the newer image.
            return

    with matrix_still_lock:
        matrix_still_image = still_image


def refresh_matrix_scanner_image():
    """Rebuild the cached scanner-mode preview image from the current scanner_image.

    Also updates latest_frame/mosaic_frame (for the web preview feeds) so those
    stay in sync without the matrix loop needing to recompute them every frame.
    """
    global matrix_scanner_image, matrix_scanner_version, latest_frame, mosaic_frame, frame_version

    with scanner_lock:
        frame = scanner_image.copy() if scanner_image is not None else None
        version = scanner_frame_version

    if frame is None:
        with scanner_lock:
            if scanner_frame_version != version:
                return
        with matrix_scanner_lock:
            matrix_scanner_image = None
            matrix_scanner_version = None
        return

    h, w = frame.shape[:2]
    min_dim = min(h, w)
    if min_dim <= 0:
        return

    start_x = max((w - min_dim) // 2, 0)
    start_y = max((h - min_dim) // 2, 0)
    cropped = frame[start_y:start_y + min_dim, start_x:start_x + min_dim]
    if cropped.shape[0] <= 0 or cropped.shape[1] <= 0:
        return

    small = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_LINEAR)
    mosaic = cv2.resize(small, (min_dim, min_dim), interpolation=cv2.INTER_NEAREST)

    resized = cv2.resize(cropped, (32, 32))
    tiled = np.concatenate([resized, resized, resized, resized], axis=1)
    frame_rgb = cv2.cvtColor(tiled, cv2.COLOR_BGR2RGB)
    still_image = Image.fromarray(frame_rgb)

    with scanner_lock:
        if scanner_frame_version != version:
            # A newer upload landed while we were computing this (now stale)
            # frame - discard it so it can't overwrite the newer content.
            return

    with frame_lock:
        latest_frame = frame.copy()
        mosaic_frame = mosaic.copy()
        frame_version += 1
        frame_lock.notify_all()

    with matrix_scanner_lock:
        matrix_scanner_image = still_image
        matrix_scanner_version = version


def matrix_loop():
    global latest_frame
    global mosaic_frame
    global USE_SCANNER_MODE
    global frame_version
    
    # Setup webcam pipeline
    pipeline = (
        "v4l2src device=/dev/video0 ! "
        "video/x-raw,width=320,height=180 ! "
        "videoconvert ! appsink"
    )
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 32
    options.chain_length = 1
    options.hardware_mapping = 'adafruit-hat'
    options.led_rgb_sequence = "GBR"
    # options.pixel_mapper_config = "U-mapper"
    options.pwm_bits = 11
    options.gpio_slowdown = 1
    options.pwm_lsb_nanoseconds = 55
    options.pwm_dither_bits = 1
    options.brightness = 100
    matrix = RGBMatrix(options=options)
    
    # Only check camera in webcam mode
    if not USE_SCANNER_MODE and not cap.isOpened():
        print("Cannot open camera")
        return

    while True:
        # Decide what to display on the matrix BEFORE doing any capture/mosaic work.
        # While a still/captured image is being shown, we must not run any webcam,
        # scanner, or cv2 processing in this loop - that CPU/GIL contention is what
        # was starving the matrix refresh timing and causing flicker, even when the
        # displayed image itself wasn't changing.
        with display_lock:
            use_captured = display_captured
            captured_path = last_captured_mosaic_path

        if use_captured and captured_path and os.path.exists(captured_path):
            with matrix_still_lock:
                still_image = matrix_still_image

            if still_image is None:
                refresh_matrix_still_image()
                with matrix_still_lock:
                    still_image = matrix_still_image

            if still_image is not None:
                matrix.SetImage(still_image)
            else:
                print("Failed to prepare captured matrix image.")

            ret, frame = cap.read()
            if ret and frame is not None:
                with frame_lock:
                    latest_frame = frame.copy()

                h, w = latest_frame.shape[:2]
                min_dim = min(h, w)
                if min_dim > 0:
                    start_x = max((w - min_dim) // 2, 0)
                    start_y = max((h - min_dim) // 2, 0)
                    cropped = latest_frame[start_y:start_y+min_dim, start_x:start_x+min_dim]
                    if cropped.shape[0] > 0 and cropped.shape[1] > 0:
                        small = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_LINEAR)
                        mosaic = cv2.resize(small, (min_dim, min_dim), interpolation=cv2.INTER_NEAREST)
                        with frame_lock:
                            mosaic_frame = mosaic.copy()
                            frame_version += 1
                            frame_lock.notify_all()

            time.sleep(0.01)
            continue

        # --- Scanner mode preview (static image, not the effects editor) ---
        # The scanner image doesn't change frame-to-frame, so only rebuild and
        # re-send it when the version actually changes - avoid hammering the
        # matrix with SetImage() and cv2 work on every loop iteration.
        if USE_SCANNER_MODE:
            with scanner_lock:
                has_scanner_image = scanner_image is not None

            if not has_scanner_image:
                display_update_event.wait()
                display_update_event.clear()
                continue

            with matrix_scanner_lock:
                still_image = matrix_scanner_image

            if still_image is None:
                refresh_matrix_scanner_image()
                with matrix_scanner_lock:
                    still_image = matrix_scanner_image

            if still_image is not None:
                matrix.SetImage(still_image)
            else:
                print("Failed to prepare scanner matrix image.")

            display_update_event.wait()
            display_update_event.clear()
            continue

        # --- True live webcam mode below: continuous capture + mosaic generation ---
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
            frame_version += 1
            frame_lock.notify_all()
        # --- End mosaic generation ---

        # Display live mosaic as before
        try:
            resized = cv2.resize(cropped, (32, 32))
            img_128x32 = np.concatenate([resized, resized, resized, resized], axis=1)
            frame_rgb = cv2.cvtColor(img_128x32, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            matrix.SetImage(image)
        except Exception as e:
            print(f"Matrix live display error: {e}")
            continue

@app.route("/scanner_snapshot/<folder>/<filename>/<kind>")
def scanner_snapshot(folder, filename, kind):
    """Serve a single, complete (non-streaming) image straight from a saved
    upload file on disk - the same reliable pattern as /processed_mosaic
    (which has always displayed correctly). Used to refresh the main-page
    webcam/webcam-mosaic <img> tags after an upload, instead of relying on
    the persistent MJPEG stream (which has repeated boundary/staleness
    issues for this static, upload-driven use case).
    """
    img_path = os.path.join(UPLOAD_ROOT, folder, filename)
    if not os.path.exists(img_path):
        return "", 404

    img = cv2.imread(img_path)
    if img is None:
        return "", 404

    if kind == "mosaic":
        h, w = img.shape[:2]
        min_dim = min(h, w)
        if min_dim <= 0:
            return "", 404
        start_x = max((w - min_dim) // 2, 0)
        start_y = max((h - min_dim) // 2, 0)
        cropped = img[start_y:start_y + min_dim, start_x:start_x + min_dim]
        small = cv2.resize(cropped, (32, 32), interpolation=cv2.INTER_LINEAR)
        out = cv2.resize(small, (min_dim, min_dim), interpolation=cv2.INTER_NEAREST)
    else:
        out = img

    ret, buffer = cv2.imencode('.jpg', out)
    if not ret:
        return "", 500
    return Response(buffer.tobytes(), mimetype='image/jpeg')

@app.route("/upload_scanner_image", methods=["POST"])
def upload_scanner_image():
    global scanner_image, latest_frame, mosaic_frame, scanner_filename
    # Accept both 'image' and 'file' for compatibility
    file = request.files.get('image') or request.files.get('file')
    user_filename = request.form.get('filename', '').strip()
    skip_auto_crop = request.form.get('skip_auto_crop', '0') == '1'
    if not file or file.filename == '':
        return jsonify(success=False, error="No image file selected")
    if not user_filename:
        return jsonify(success=False, error="No filename provided")

    # Sanitize filename
    safe_filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    folder = f"{timestamp}-{safe_filename}"
    save_dir = os.path.join(UPLOAD_ROOT, folder)
    os.makedirs(save_dir, exist_ok=True)

    try:
        print(f"[scanner] upload request filename={user_filename!r} mode={USE_SCANNER_MODE}", flush=True)
        # Read image data
        image_data = file.read()
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify(success=False, error="Invalid image format")

        # Auto-crop A4 scanned image to specific region unless the caller
        # explicitly asked for a manual upload.
        # h, w = img.shape[:2]
        # pixels_per_cm = w / 21.0
        # left_offset_px = int(4.3 * pixels_per_cm)
        # top_offset_px = int(1.4 * pixels_per_cm)
        # crop_size_px = int(11.8 * pixels_per_cm)
        # right_edge = min(left_offset_px + crop_size_px, w)
        # bottom_edge = min(top_offset_px + crop_size_px, h)
        # if (right_edge > left_offset_px and bottom_edge > top_offset_px and left_offset_px >= 0 and top_offset_px >= 0):
        #     cropped_img = img[top_offset_px:bottom_edge, left_offset_px:right_edge]
        #     if cropped_img.shape[0] > 0 and cropped_img.shape[1] > 0:
        #         img = cropped_img

        if not skip_auto_crop:
            img = auto_crop_scanned_drawing(img)
                
        # Save original (cropped) image
        original_path = os.path.join(save_dir, f"{safe_filename}.jpg")
        cv2.imwrite(original_path, img)

        # Save 180x180px version for manipulation
        min_dim = min(img.shape[:2])
        start_x = max((img.shape[1] - min_dim) // 2, 0)
        start_y = max((img.shape[0] - min_dim) // 2, 0)
        square_img = img[start_y:start_y+min_dim, start_x:start_x+min_dim]
        img_180 = cv2.resize(square_img, (180, 180), interpolation=cv2.INTER_AREA)
        small_path = os.path.join(save_dir, f"{safe_filename}_180x180.jpg")
        cv2.imwrite(small_path, img_180)

        # Update scanner_image; latest_frame/mosaic_frame/frame_version are
        # refreshed below by refresh_matrix_scanner_image() so there's a single
        # source of truth for that computation.
        global scanner_frame_version
        with scanner_lock:
            scanner_image = img_180.copy()
            scanner_filename = safe_filename  # Store the scanner filename
            scanner_frame_version += 1

        reset_effect_params()
        print(f"[scanner] upload processed folder={folder} mosaic={small_path} scanner_filename={scanner_filename}", flush=True)

        # Set the captured mosaic path and flag for editor compatibility
        mosaic_path = small_path  # Use the 180x180 as the main for manipulation
        global last_captured_mosaic_path, display_captured, capture_generation
        with display_lock:
            last_captured_mosaic_path = mosaic_path
            display_captured = True
            capture_generation += 1
            current_generation = capture_generation
        refresh_matrix_still_image()
        refresh_matrix_scanner_image()
        display_update_event.set()

        return jsonify(success=True, message="Scanner image uploaded and processed successfully", folder=folder, filename=safe_filename, mosaic_filename=f"{safe_filename}_180x180.jpg", effect_params=dict(DEFAULT_EFFECT_PARAMS), generation=current_generation)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route("/set_scanner_mode", methods=["POST"])
def set_scanner_mode():
    global USE_SCANNER_MODE
    data = request.json
    USE_SCANNER_MODE = data.get("enabled", False)
    print(f"[scanner] set_scanner_mode enabled={USE_SCANNER_MODE}", flush=True)
    if not USE_SCANNER_MODE:
        reset_effect_params()
        global display_captured
        with display_lock:
            display_captured = False
        with matrix_still_lock:
            global matrix_still_image
            matrix_still_image = None
    display_update_event.set()
    return jsonify(success=True, scanner_mode=USE_SCANNER_MODE, effect_params=dict(effect_params))

@app.route("/get_scanner_mode")
def get_scanner_mode():
    global scanner_filename
    with scanner_lock:
        current_filename = scanner_filename
    return jsonify(scanner_mode=USE_SCANNER_MODE, scanner_filename=current_filename)

@app.route("/video_feed_mosaic")
def video_feed_mosaic():
    def gen_mosaic_frames():
        global mosaic_frame
        last_sent_version = -1
        while True:
            with frame_lock:
                while frame_version == last_sent_version:
                    frame_lock.wait()
                current_version = frame_version
                frame = mosaic_frame.copy() if mosaic_frame is not None else None
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    frameWeb = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' + str(len(frameWeb)).encode() + b'\r\n\r\n' + frameWeb + b'\r\n')
            last_sent_version = current_version
    return Response(gen_mosaic_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/video_feed_effect")
def video_feed_effect():
    def gen_effect_frames():
        global mosaic_frame, effect_params
        last_sent_version = -1
        while True:
            with frame_lock:
                while frame_version == last_sent_version:
                    frame_lock.wait()
                current_version = frame_version
                frame = mosaic_frame.copy() if mosaic_frame is not None else None
            if frame is not None:
                with params_lock:
                    params = dict(effect_params)

                img = apply_effects_to_bgr(frame, params)

                ret, buffer = cv2.imencode('.jpg', img)
                if ret:
                    frameWeb = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' + str(len(frameWeb)).encode() + b'\r\n\r\n' + frameWeb + b'\r\n')
            last_sent_version = current_version
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
        effect_params["highlights"] = float(data.get("highlights", 0.0))
        effect_params["hue_shift"] = int(data.get("hue_shift", 0))
        effect_params["colorize"] = int(data.get("colorize", 0))
        effect_params["invert"] = int(data.get("invert", 0))
    return jsonify(success=True)

@app.route("/capture_image", methods=["POST"])
def capture_image():
    global latest_frame, mosaic_frame, last_captured_mosaic_path, display_captured, scanner_filename, USE_SCANNER_MODE, capture_generation
    data = request.json
    
    if USE_SCANNER_MODE:
        base = scanner_filename
        if not base:
            return jsonify(success=False, error="No scanner image available")
    else:
        base = data.get("base", "").strip()
        if not base:
            return jsonify(success=False, error="Missing base name")
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    folder = f"{timestamp}-{base}"
    save_dir = os.path.join(UPLOAD_ROOT, folder)
    os.makedirs(save_dir, exist_ok=True)

    if USE_SCANNER_MODE:
        with scanner_lock:
            main_img = scanner_image.copy() if scanner_image is not None else None
        if main_img is None:
            with display_lock:
                fallback_path = last_captured_mosaic_path
            if fallback_path and os.path.exists(fallback_path):
                main_img = cv2.imread(fallback_path)
        if main_img is None:
            return jsonify(success=False, error="No scanner image available")

        mosaic_img = build_tiled_mosaic_image(main_img)
        if mosaic_img is None:
            return jsonify(success=False, error="No scanner mosaic available")
    else:
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
        capture_generation += 1
        current_generation = capture_generation
    refresh_matrix_still_image()
    display_update_event.set()
    return jsonify(success=True, folder=folder, generation=current_generation)

@app.route("/uploads/<folder>/<filename>")
def uploaded_file(folder, filename):
    return send_from_directory(os.path.join(UPLOAD_ROOT, folder), filename)

@app.route("/processed_mosaic/<folder>/<filename>")
def processed_mosaic(folder, filename):
    params = {
        "brightness": float(request.args.get("brightness", 1.0)),
        "contrast": float(request.args.get("contrast", 1.0)),
        "saturation": float(request.args.get("saturation", 1.0)),
        "blur": int(request.args.get("blur", 0)),
        "highlights": float(request.args.get("highlights", 0.0)),
        "hue_shift": int(request.args.get("hue_shift", 0)),
        "colorize": int(request.args.get("colorize", 0)),
        "invert": int(request.args.get("invert", 0)),
    }

    img_path = os.path.join(UPLOAD_ROOT, folder, filename)
    if not os.path.exists(img_path):
        return "", 404

    img = cv2.imread(img_path)
    if img is None:
        return "", 404

    img = apply_effects_to_bgr(img, params)

    _, buffer = cv2.imencode('.jpg', img)
    return Response(buffer.tobytes(), mimetype='image/jpeg')
    
@app.route("/matrix_live")
def matrix_live():
    global display_captured
    with display_lock:
        display_captured = False
    with matrix_still_lock:
        global matrix_still_image
        matrix_still_image = None
    display_update_event.set()
    return jsonify(success=True)

@app.route("/matrix_edit")
def matrix_edit():
    global display_captured
    with display_lock:
        display_captured = True
    refresh_matrix_still_image()
    display_update_event.set()
    return jsonify(success=True)

@app.route("/set_matrix_effect_params", methods=["POST"])
def set_matrix_effect_params():
    global effect_params
    data = request.json

    requested_generation = data.get("generation")
    if requested_generation is not None:
        with display_lock:
            current_generation = capture_generation
        if int(requested_generation) != current_generation:
            print(f"[effects] ignoring stale set_matrix_effect_params generation={requested_generation} current={current_generation}", flush=True)
            return jsonify(success=True, ignored=True)

    with params_lock:
        effect_params["brightness"] = float(data.get("brightness", 1.0))
        effect_params["contrast"] = float(data.get("contrast", 1.0))
        effect_params["saturation"] = float(data.get("saturation", 1.0))
        effect_params["hue_shift"] = int(data.get("hue_shift", 0))
        effect_params["highlights"] = float(data.get("highlights", 0.0))
        effect_params["colorize"] = int(data.get("colorize", 0))
        effect_params["invert"] = int(data.get("invert", 0))
    print(f"[effects] set_matrix_effect_params -> {dict(effect_params)}", flush=True)
    refresh_matrix_still_image()
    display_update_event.set()
    return jsonify(success=True)

@app.route("/save_final_image", methods=["POST"])
def save_final_image():
    data = request.json
    folder = data.get("folder")
    filename = data.get("filename")
    target = data.get("target", "web")
    params = data.get("params", {})
    if not folder or not filename:
        return jsonify(success=False, error="Missing folder or filename")

    img_path = os.path.join(UPLOAD_ROOT, folder, filename)
    if not os.path.exists(img_path):
        return jsonify(success=False, error="Image not found")

    img = cv2.imread(img_path)
    if img is None:
        return jsonify(success=False, error="Failed to load image")

    img = apply_effects_to_bgr(img, params)

    # Save as -final.jpg
    base, ext = os.path.splitext(filename)
    final_filename = f"{base}-final.jpg"
    target_folder = folder if target != "led" else os.path.join(folder, "LED")
    final_path = os.path.join(UPLOAD_ROOT, target_folder, final_filename)
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    cv2.imwrite(final_path, img)

    # --- FTP upload ---
    if isSavingToFTP:
        try:
            with ftplib.FTP_TLS(context=context) as ftp:
                ftp.connect(FTP_HOST, FTP_PORT)
                ftp.login(FTP_USER, FTP_PASS)
                ftp.prot_p()
                ftp.cwd(FTP_TARGET_DIR)
                if target == "led":
                    try:
                        ftp.cwd("LED")
                    except Exception:
                        ftp.mkd("LED")
                        ftp.cwd("LED")
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
    app.run(host="0.0.0.0", debug=True, use_reloader=False, port=5000, threaded=True)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    matrix_loop()