import os
import sys
import time
import glob
import cv2
import numpy as np
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image
import threading
import random
import requests
import json
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# Configuration

# Use /opt/exhibition as the exhibition folder for sudo compatibility
EXHIBITION_FOLDER = "/opt/exhibition"
os.makedirs(EXHIBITION_FOLDER, exist_ok=True)

TOGGLE_TEST_PATTERN = False  # Set to True for 4-color test pattern
USE_COORDINATOR = True  # Set to True to use coordinator service
COORDINATOR_IP = os.getenv("COORDINATOR_IP", "127.0.0.1")  # IP of the coordinator Pi
COORDINATOR_PORT = 5001
DISPLAY_ID = 2  # Set to 2 for the third Pi (2-screen Pi)

current_images = [None, None]  # Only 2 screens for this Pi
assigned_filenames = [None, None]  # Current assigned filenames
loaded_filenames = [None, None]  # Track last loaded filename for each screen
last_coordinator_check = 0
image_lock = threading.Lock()
fallback_start_time = None
fallback_last_update = 0
fallback_indices = [0, 1]
fallback_files = []
fallback_fail_count = 0

def fetch_coordinator_images():
    """Fetch current image assignments from coordinator"""
    global assigned_filenames, last_coordinator_check
    
    try:
        url = f"http://{COORDINATOR_IP}:{COORDINATOR_PORT}/images/{DISPLAY_ID}"
        response = requests.get(url, timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            with image_lock:
                assigned_filenames = data['images']
                last_coordinator_check = time.time()
            print(f"Received from coordinator: {[f[:20] + '...' if len(f) > 20 else f for f in assigned_filenames]}")
            return True
        else:
            print(f"Coordinator returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to coordinator: {e}")
        return False

def load_image_files():
    """Load all JPG files from the exhibition folder (fallback mode only)"""
    pattern = os.path.join(EXHIBITION_FOLDER, "*.jpg")
    files = glob.glob(pattern)
    files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.jpeg")))
    files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.JPG")))
    files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.JPEG")))
    files.sort()
    if len(files) > 1:
        random.shuffle(files)
    print(f"Fallback: Found {len(files)} local images")
    return files

def load_and_resize_image(filename):
    """Load an image by filename and resize it to 32x32 for the LED matrix"""
    try:
        # Allow subfolders, but sanitize to prevent directory traversal
        safe_path = os.path.normpath(filename).lstrip(os.sep)
        image_path = os.path.join(EXHIBITION_FOLDER, safe_path)
        print(f"Trying to load image: {image_path}")
        img = cv2.imread(image_path)
        if img is None:
            print(f"Failed to load image: {image_path}")
            return None
        # Resize to 32x32 for each screen
        resized = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
        return resized
    except Exception as e:
        print(f"Error processing image {filename}: {e}")
        return None

def update_images():
    """Update the current images based on coordinator assignments"""
    global current_images, fallback_start_time, fallback_last_update, fallback_indices, fallback_files, fallback_fail_count

    if USE_COORDINATOR:
        if fetch_coordinator_images():
            # Reset fallback tracking
            fallback_fail_count = 0
            fallback_start_time = None
            fallback_last_update = 0
            fallback_indices = [0, 1]
            fallback_files = []
            with image_lock:
                for screen in range(2):
                    fname = assigned_filenames[screen] if screen < len(assigned_filenames) else None
                    if fname:
                        if loaded_filenames[screen] != fname:
                            current_images[screen] = load_and_resize_image(fname)
                            loaded_filenames[screen] = fname
                        # else: keep current_images[screen] as is
                    else:
                        current_images[screen] = None
                        loaded_filenames[screen] = None
        else:
            fallback_fail_count += 1
            print(f"Coordinator unavailable, fail count: {fallback_fail_count}")
            if fallback_fail_count >= 4:
                # Only start fallback after 4 consecutive failures
                if fallback_start_time is None:
                    fallback_start_time = time.time()
                    fallback_last_update = 0
                    fallback_indices = [0, 1]
                    fallback_files = load_image_files()
                    with image_lock:
                        for screen in range(2):
                            if fallback_files and screen < len(fallback_files):
                                img_path = fallback_files[fallback_indices[screen] % len(fallback_files)]
                                current_images[screen] = load_and_resize_image(os.path.basename(img_path))
                            else:
                                current_images[screen] = None
                else:
                    # Only start cycling after 2 minutes
                    if time.time() - fallback_start_time > 120:
                        # Update one image every 7 seconds
                        if time.time() - fallback_last_update > 7:
                            fallback_last_update = time.time()
                            # Find which screen to update (round robin)
                            next_screen = int(((fallback_last_update - fallback_start_time) // 7) % 2)
                            if fallback_files and next_screen < len(fallback_indices):
                                fallback_indices[next_screen] = (fallback_indices[next_screen] + 1) % len(fallback_files)
                                img_path = fallback_files[fallback_indices[next_screen]]
                                with image_lock:
                                    current_images[next_screen] = load_and_resize_image(os.path.basename(img_path))
            # If not enough failures, do nothing (keep last images)
    else:
        # Local mode (original behavior)
        fallback_files = load_image_files()
        with image_lock:
            for screen in range(2):
                if fallback_files and screen < len(fallback_files):
                    img_path = fallback_files[screen % len(fallback_files)]
                    if loaded_filenames[screen] != img_path:
                        current_images[screen] = load_and_resize_image(os.path.basename(img_path))
                        loaded_filenames[screen] = img_path
                    # else: keep current_images[screen] as is
                else:
                    current_images[screen] = None
                    loaded_filenames[screen] = None

def create_matrix_image():
    """Create the image for the matrix display"""
    with image_lock:
        # Create black fallback images if any are missing
        screen_images = []
        for i in range(2):  # Only 2 screens
            if current_images[i] is not None:
                img_rotated = cv2.rotate(current_images[i], cv2.ROTATE_90_COUNTERCLOCKWISE)
                screen_images.append(img_rotated)
            else:
                # Create a black 32x32 image as fallback
                black_img = np.zeros((32, 32, 3), dtype=np.uint8)
                screen_images.append(black_img)
        
        # Concatenate horizontally to create 64x32 image (2 panels wide)
        matrix_img = np.concatenate(screen_images, axis=1) 
        matrix_img = cv2.rotate(matrix_img, cv2.ROTATE_180)
        matrix_img_rgb = cv2.cvtColor(matrix_img, cv2.COLOR_BGR2RGB)
        return Image.fromarray(matrix_img_rgb)

def matrix_loop():
    """Main loop for the RGB matrix display"""
    if TOGGLE_TEST_PATTERN:
        options = RGBMatrixOptions()
        options.rows = 32
        options.cols = 32
        options.chain_length = 2  # Only 2 panels
        options.multiplexing = 6
        options.hardware_mapping = 'adafruit-hat'
        options.brightness = 50
        matrix = RGBMatrix(options=options)
        print("Starting RGB matrix display in DEDICATED 2-COLOR TEST PATTERN mode...")
        test_img = np.zeros((32, 64, 3), dtype=np.uint8)  # 2 panels wide
        # Create test pattern for 2 panels
        test_img[0:16, 0:32] = [255, 0, 0]     # Panel 1: red
        test_img[16:32, 0:32] = [0, 255, 0]    # Panel 1: green
        test_img[0:16, 32:64] = [0, 0, 255]    # Panel 2: blue
        test_img[16:32, 32:64] = [255, 255, 0] # Panel 2: yellow
        matrix.SetImage(Image.fromarray(test_img))
        while True:
            time.sleep(1)
    else:
        options = RGBMatrixOptions()
        options.rows = 32
        options.cols = 32
        options.chain_length = 2  # Only 2 panels
        options.hardware_mapping = 'adafruit-hat'
        options.brightness = 80
        # anti-flickering stuff
        # options.pwm_lsb_nanoseconds = 130
        # options.gpio_slowdown = 4
        # options.disable_hardware_pulsing = True
        # options.pwm_bits = 11
        options.pwm_lsb_nanoseconds = 300
        options.gpio_slowdown = 2
        options.pwm_bits = 8
        matrix = RGBMatrix(options=options)
        
        print(f"Starting RGB matrix display (Display ID: {DISPLAY_ID}, 2-Screen Pi)...")
        if USE_COORDINATOR:
            print(f"Using coordinator at {COORDINATOR_IP}:{COORDINATOR_PORT}")
        else:
            print("Using local image cycling")
        print("Press Ctrl+C to exit")
        
        # Initial image load
        update_images()
        
        try:
            while True:
                # Check for new assignments every few seconds
                current_time = time.time()
                if USE_COORDINATOR and current_time - last_coordinator_check > 1.0:
                    update_images()
                
                # Update display
                try:
                    matrix_image = create_matrix_image()
                    matrix.SetImage(matrix_image)
                except Exception as e:
                    print(f"Error setting matrix image: {e}")
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            matrix.Clear()

def main():
    """Main function"""
    print("JPG Cycle App for 2-Panel RGB Matrix (Client Mode)")
    print(f"Exhibition folder: {EXHIBITION_FOLDER}")
    print(f"Display ID: {DISPLAY_ID}")
    
    if USE_COORDINATOR:
        print(f"Coordinator mode: {COORDINATOR_IP}:{COORDINATOR_PORT}")
    else:
        print("Local cycling mode")
    
    # Check if exhibition folder exists
    if not os.path.exists(EXHIBITION_FOLDER):
        print(f"Creating exhibition folder: {EXHIBITION_FOLDER}")
        os.makedirs(EXHIBITION_FOLDER, exist_ok=True)
        if not USE_COORDINATOR:
            print("Please add JPG images to the exhibition folder and restart the app.")
            return
    
    # Start the matrix loop
    matrix_loop()

if __name__ == "__main__":
    main()
