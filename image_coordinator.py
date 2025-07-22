#!/usr/bin/env python3
"""
Image Coordinator Service
Manages image cycling and timing for multiple Pi displays.
Each Pi has 4 screens (chain_length=4), and this service ensures
no image repetition across all displays.
"""

import os
import sys
import time
import glob
import random
import threading
from flask import Flask, jsonify
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXHIBITION_FOLDER = os.path.join(BASE_DIR, "exhibition")

app = Flask(__name__)

# Configuration
CYCLE_TIME = 15.0  # seconds for a full cycle (15 seconds for testing)
INCREMENTAL_UPDATE_TIME = 2.0  # seconds between incremental updates
NUM_DISPLAYS = 3  # number of Pi displays
SCREENS_PER_DISPLAY = [4, 4, 2]  # screens per Pi: Pi#1=4, Pi#2=4, Pi#3=2

# Global state
image_files = []
current_assignments = {}  # {display_id: [img1, img2, img3, img4]}
next_cycle_images = []  # Next 10 images to cycle through
image_index = 0
cycle_start_time = time.time()
# Track the number of cycles for Pi 2 linking logic
cycle_count = 0
last_incremental_update = time.time()
current_screen_to_update = 0  # Which screen position to update next (0-9)
coordinator_lock = threading.Lock()

def load_image_files():
    """Load all JPG files from the exhibition folder"""
    global image_files
    pattern = os.path.join(EXHIBITION_FOLDER, "*.jpg")
    image_files = glob.glob(pattern)
    image_files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.jpeg")))
    image_files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.JPG")))
    image_files.extend(glob.glob(os.path.join(EXHIBITION_FOLDER, "*.JPEG")))
    image_files.sort()  # Sort for consistent order before shuffling
    if len(image_files) > 1:
        random.shuffle(image_files)
    print(f"Loaded {len(image_files)} images")
    return len(image_files) > 0

def assign_images():
    """Assign initial images to each display, ensuring no repetition"""
    global current_assignments, next_cycle_images, image_index, current_screen_to_update
    
    if len(image_files) == 0:
        return
    
    total_screens = sum(SCREENS_PER_DISPLAY)  # 4 + 4 + 2 = 10 screens

    # Prepare linking images (relative to EXHIBITION_FOLDER, e.g., 'linkings/filename.jpg')
    linkings_folder = os.path.join(EXHIBITION_FOLDER, "linkings")
    linkings_images = []
    if os.path.exists(linkings_folder):
        linkings_images = glob.glob(os.path.join(linkings_folder, "*.jpg"))
        linkings_images.extend(glob.glob(os.path.join(linkings_folder, "*.jpeg")))
        linkings_images.extend(glob.glob(os.path.join(linkings_folder, "*.JPG")))
        linkings_images.extend(glob.glob(os.path.join(linkings_folder, "*.JPEG")))
        linkings_images = [os.path.relpath(img, EXHIBITION_FOLDER) for img in linkings_images]

    with coordinator_lock:
        # Create initial assignments for each display
        screen_offset = 0
        for display_id in range(NUM_DISPLAYS):
            screens_for_this_display = SCREENS_PER_DISPLAY[display_id]
            display_images = []
            for screen in range(screens_for_this_display):
                img_idx = (image_index + screen_offset + screen) % len(image_files)
                rel_path = os.path.relpath(image_files[img_idx], EXHIBITION_FOLDER)
                display_images.append(rel_path)
            # For Pi 0 (display_id 0), after 4 images are chosen, replace one with a random linking image
            if display_id == 0 and linkings_images and len(display_images) == 4:
                replace_pos = random.randint(0, 3)
                link_img = random.choice(linkings_images)
                display_images[replace_pos] = link_img
            current_assignments[display_id] = display_images
            screen_offset += screens_for_this_display

        # Prepare next cycle images (next 10 images after current ones)
        next_cycle_images = []
        for i in range(total_screens):
            img_idx = (image_index + total_screens + i) % len(image_files)
            next_cycle_images.append(os.path.basename(image_files[img_idx]))

        # Reset incremental update counter
        current_screen_to_update = 0

        print("Initial image assignments created")

def update_single_image():
    """Update a single image incrementally during the cycle"""
    global current_assignments, current_screen_to_update, next_cycle_images
    
    if len(image_files) == 0 or len(next_cycle_images) == 0:
        return
    
    total_screens = sum(SCREENS_PER_DISPLAY)

    with coordinator_lock:
        # Find which display and screen position this update affects
        screen_position = current_screen_to_update

        # Map global screen position to display and local screen
        current_display = 0
        local_screen = screen_position

        for display_id in range(NUM_DISPLAYS):
            screens_in_this_display = SCREENS_PER_DISPLAY[display_id]
            if local_screen < screens_in_this_display:
                current_display = display_id
                break
            local_screen -= screens_in_this_display

        # Update that specific screen with the next image
        if current_display < len(current_assignments) and local_screen < len(current_assignments[current_display]):
            new_image = next_cycle_images[screen_position]
            current_assignments[current_display][local_screen] = new_image
            print(f"Updated Display {current_display}, Screen {local_screen} with: {new_image[:20]}...")

        # Move to next screen for next update
        current_screen_to_update = (current_screen_to_update + 1) % total_screens

def start_new_cycle():
    """Start a new 2-minute cycle with fresh images"""
    global image_index, next_cycle_images, current_screen_to_update, cycle_start_time, cycle_count
    
    total_screens = sum(SCREENS_PER_DISPLAY)
    
    with coordinator_lock:
        # Move to next set of images
        image_index = (image_index + total_screens * 2) % len(image_files)  # Skip ahead by 2 full sets
        # Increment cycle count
        cycle_count += 1

        # Prepare new next cycle images
        next_cycle_images = []
        for i in range(total_screens):
            img_idx = (image_index + total_screens + i) % len(image_files)
            next_cycle_images.append(os.path.basename(image_files[img_idx]))

        # After preparing next_cycle_images, for Pi 0 and Pi 1, replace one of the first 4 and one of the next 4 with a linking image
        linkings_folder = os.path.join(EXHIBITION_FOLDER, "linkings")
        linkings_images = []
        if os.path.exists(linkings_folder):
            linkings_images = glob.glob(os.path.join(linkings_folder, "*.jpg"))
            linkings_images.extend(glob.glob(os.path.join(linkings_folder, "*.jpeg")))
            linkings_images.extend(glob.glob(os.path.join(linkings_folder, "*.JPG")))
            linkings_images.extend(glob.glob(os.path.join(linkings_folder, "*.JPEG")))
            linkings_images = [os.path.relpath(img, EXHIBITION_FOLDER) for img in linkings_images]
        # Pi 0 (first 4 images)
        if linkings_images and len(next_cycle_images) >= 4:
            replace_pos_0 = random.randint(0, 3)
            link_img_0 = random.choice(linkings_images)
            next_cycle_images[replace_pos_0] = link_img_0
        # Pi 1 (next 4 images)
        if linkings_images and len(next_cycle_images) >= 8:
            replace_pos_1 = random.randint(4, 7)
            link_img_1 = random.choice(linkings_images)
            next_cycle_images[replace_pos_1] = link_img_1

        # Update Pi 2 (display_id 2) with the last two images from next_cycle_images
        if len(next_cycle_images) >= 10:
            pi2_images = next_cycle_images[8:10].copy()
            # Every 4th cycle, replace one with a linking image if available
            if cycle_count % 4 == 0 and linkings_images:
                replace_pos_2 = random.randint(0, 1)
                link_img_2 = random.choice(linkings_images)
                pi2_images[replace_pos_2] = link_img_2
            current_assignments[2] = pi2_images

        # Reset counters
        current_screen_to_update = 0
        cycle_start_time = time.time()

        # Shuffle when we complete a full cycle through all images
        if image_index == 0 and len(image_files) > total_screens:
            random.shuffle(image_files)
            print("Shuffled image order for new cycle")

        print(f"Started new 2-minute cycle at {datetime.now().strftime('%H:%M:%S')}")
        print(f"Next images to cycle: {[img[:15] + '...' for img in next_cycle_images[:5]]}...")

def coordinator_loop():
    """Main coordinator loop that cycles images incrementally"""
    global last_incremental_update, cycle_start_time
    
    print("Starting coordinator loop...")
    
    if not load_image_files():
        print("No images found in exhibition folder!")
        return
    
    # Initial assignment
    assign_images()
    
    while True:
        current_time = time.time()
        
        # Check if we need to start a new 2-minute cycle
        if current_time - cycle_start_time >= CYCLE_TIME:
            start_new_cycle()
        
        # Check if we need to do an incremental update (every 7 seconds)
        elif current_time - last_incremental_update >= INCREMENTAL_UPDATE_TIME:
            update_single_image()
            last_incremental_update = current_time
            
            # Debug: show which images are currently displayed
            cycle_progress = int((current_time - cycle_start_time) / INCREMENTAL_UPDATE_TIME)
            time_left = CYCLE_TIME - (current_time - cycle_start_time)
            print(f"Incremental update #{cycle_progress}, {time_left:.0f}s left in cycle")
        
        time.sleep(0.5)  # Check more frequently for better timing

# API Endpoints

@app.route('/status')
def status():
    """Get coordinator status"""
    current_time = time.time()
    return jsonify({
        'status': 'running',
        'total_images': len(image_files),
        'displays': NUM_DISPLAYS,
        'screens_per_display': SCREENS_PER_DISPLAY,
        'total_screens': sum(SCREENS_PER_DISPLAY),
        'cycle_time': CYCLE_TIME,
        'incremental_update_time': INCREMENTAL_UPDATE_TIME,
        'current_index': image_index,
        'cycle_start': cycle_start_time,
        'time_in_current_cycle': current_time - cycle_start_time,
        'time_until_next_cycle': max(0, CYCLE_TIME - (current_time - cycle_start_time)),
        'current_screen_to_update': current_screen_to_update
    })

@app.route('/images/<int:display_id>')
def get_images(display_id):
    """Get current image assignments for a specific display"""
    if display_id not in current_assignments:
        return jsonify({'error': 'Invalid display ID'}), 400
    
    with coordinator_lock:
        return jsonify({
            'display_id': display_id,
            'images': current_assignments[display_id],
            'cycle_start': cycle_start_time,
            'time_in_cycle': time.time() - cycle_start_time,
            'next_cycle_in': max(0, CYCLE_TIME - (time.time() - cycle_start_time))
        })

@app.route('/images/all')
def get_all_images():
    """Get image assignments for all displays"""
    with coordinator_lock:
        return jsonify({
            'assignments': current_assignments,
            'cycle_start': cycle_start_time,
            'time_in_cycle': time.time() - cycle_start_time,
            'next_cycle_in': max(0, CYCLE_TIME - (time.time() - cycle_start_time)),
            'total_images': len(image_files),
            'total_screens': sum(SCREENS_PER_DISPLAY),
            'current_screen_to_update': current_screen_to_update,
            'next_images': next_cycle_images
        })

@app.route('/reload')
def reload_images():
    """Reload images from exhibition folder"""
    if load_image_files():
        assign_images()
        return jsonify({'status': 'reloaded', 'image_count': len(image_files)})
    else:
        return jsonify({'error': 'No images found'}), 404

def main():
    """Main function"""
    print("Image Coordinator Service")
    print(f"Exhibition folder: {EXHIBITION_FOLDER}")
    print(f"Managing {NUM_DISPLAYS} displays:")
    for i, screens in enumerate(SCREENS_PER_DISPLAY):
        print(f"  Display {i}: {screens} screens")
    print(f"Total screens: {sum(SCREENS_PER_DISPLAY)}")
    print(f"Cycle time: {CYCLE_TIME} seconds ({CYCLE_TIME/60:.1f} minutes)")
    print(f"Incremental update every: {INCREMENTAL_UPDATE_TIME} seconds")
    
    # Ensure exhibition folder exists
    os.makedirs(EXHIBITION_FOLDER, exist_ok=True)
    
    # Start coordinator in background thread
    coordinator_thread = threading.Thread(target=coordinator_loop, daemon=True)
    coordinator_thread.start()
    
    print("Starting Flask server on http://0.0.0.0:5001")
    print("API endpoints:")
    print("  GET /status - Get coordinator status")
    print("  GET /images/<display_id> - Get images for specific display")
    print("  GET /images/all - Get all image assignments")
    print("  GET /reload - Reload images from folder")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=5001, debug=False)

if __name__ == "__main__":
    main()
