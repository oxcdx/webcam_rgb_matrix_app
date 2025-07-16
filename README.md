# RGB Matrix Image Display App

A Python application for displaying images and test patterns on RGB LED matrix panels using the `rgbmatrix` library. Supports both single-panel and multi-panel configurations with various display modes and effects.

## Features

- **Multi-Panel Support**: Display images across 1 or 4 chained RGB matrix panels
- **Image Cycling**: Automatically cycle through JPG images in the exhibition folder
- **Test Patterns**: Built-in 4-color test pattern for panel mapping and diagnostics
- **Multiple Display Modes**: 
  - Single image test mode
  - Image cycling mode
  - 4-color test pattern mode
- **Flexible Configuration**: Easy toggles for different panel configurations and display modes
- **Multiplexing Support**: Built-in support for different RGB matrix multiplexing modes

## Hardware Requirements

- Raspberry Pi (recommended: Pi 3B+ or Pi 4)
- RGB LED Matrix Panel(s) (32x32 pixels)
- Adafruit RGB Matrix HAT or equivalent
- Proper power supply for LED panels

## Software Dependencies

```bash
# Install required Python packages
pip install opencv-python pillow numpy

# Install RGB Matrix library (follow official instructions)
# https://github.com/hzeller/rpi-rgb-led-matrix
```

## File Structure

- `app.py` - Main webcam/scanner application with multi-panel support
- `jpg_cycle_app.py` - JPG cycling application for 4-panel mode
- `jpg_cycle_app_alt_screen_type.py` - Flexible display app with multiple modes
- `webcam_rgb_matrix.py` - Core webcam functionality
- `exhibition/` - Folder containing JPG images to display
- `uploads/` - Folder for uploaded/processed images
- `static/` - Web interface assets
- `templates/` - HTML templates for web interface

## Configuration

### Main Configuration Flags (in `jpg_cycle_app_alt_screen_type.py`)

```python
TOGGLE_4_SCREEN_MODE = True   # True for 4-panel, False for single panel
TOGGLE_TEST_PATTERN = False   # True for test pattern mode
TEST_JPG_MODE = False         # True to display single test image
MULTIPLEX_MODE = 0            # Multiplexing mode (0-7)
```

### Multiplexing Modes

- `0`: No multiplexing (default)
- `1`: Strip multiplexing
- `2`: Checker multiplexing  
- `3`: Spiral multiplexing
- `4`: ZStrip multiplexing
- `5`: ZnMirrorZStrip multiplexing
- `6`: Coreman multiplexing
- `7`: Kaler2020 multiplexing

## Usage

### 1. Single Panel Display
```bash
# Edit configuration in jpg_cycle_app_alt_screen_type.py
TOGGLE_4_SCREEN_MODE = False
TOGGLE_TEST_PATTERN = False

python jpg_cycle_app_alt_screen_type.py
```

### 2. Multi-Panel Display
```bash
# Edit configuration
TOGGLE_4_SCREEN_MODE = True
TOGGLE_TEST_PATTERN = False

python jpg_cycle_app_alt_screen_type.py
```

### 3. Test Pattern Mode
```bash
# Edit configuration
TOGGLE_TEST_PATTERN = True

python jpg_cycle_app_alt_screen_type.py
```

### 4. Single Image Test
```bash
# Edit configuration
TEST_JPG_MODE = True
# Place test image: exhibition/20250712142130-rose-mosaic-final.jpg

python jpg_cycle_app_alt_screen_type.py
```

## Adding Images

1. Place JPG images in the `exhibition/` folder
2. Supported formats: `.jpg`, `.jpeg`, `.JPG`, `.JPEG`
3. Images are automatically resized and cropped to fit panel dimensions
4. Images cycle automatically (unless in test mode)

## Troubleshooting

### Panel Mapping Issues
1. Try different `MULTIPLEX_MODE` values (0-7)
2. Use test pattern mode to diagnose color and orientation issues
3. Check hardware connections and power supply
4. Verify `options.hardware_mapping` setting

### Display Issues
- **Image appears on half screen**: Check chain_length and image dimensions
- **Colors are wrong**: Try different multiplexing modes
- **Image is rotated**: Adjust the `cv2.rotate()` calls in `create_matrix_image()`
- **Panels show wrong content**: Verify chain_length matches physical setup

### Common Hardware Mapping Options
- `'adafruit-hat'` - For Adafruit RGB Matrix HAT
- `'adafruit-hat-pwm'` - For Adafruit HAT with PWM
- `'regular'` - For direct GPIO connection

## Development

### Key Functions
- `load_and_resize_image()` - Loads and processes images for display
- `create_matrix_image()` - Creates the final matrix image for display
- `matrix_loop()` - Main display loop with cycling logic
- `update_images()` - Updates current images for each panel

### Adding New Features
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with your hardware setup
5. Submit a pull request

## License

This project is open source. Please check individual file headers for specific license information.

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## Hardware Setup Notes

- Ensure proper power supply for LED panels (5V, sufficient amperage)
- Use quality jumper wires for stable connections
- Consider heat dissipation for long-running displays
- Test with single panel before adding multiple panels
- Verify GPIO pin connections match your HAT/hardware setup
