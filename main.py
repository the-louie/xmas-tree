import time
import spidev
import math
import random
import datetime
import threading
import logging
import signal
import sys
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# We only have SPI bus 0 available to us on the Pi
bus = 0

#Device is the chip select pin. Set to 0 or 1, depending on the connections
device = 1

# Enable SPI
spi = spidev.SpiDev()

# Open a connection to a specific bus and device (chip select pin)
spi.open(bus, device)

# Set SPI speed and mode
spi.max_speed_hz = 500000
spi.mode = 0

# Clear display
msg = [0] * 300
spi.xfer2(msg)


# Configuration constants
NUM_LEDS = 100
FAVORITE_COLOR = [255, 25, 2]  # Orange-red color

# Animation timing constants
DAYTIME_START_HOUR = 6  # 6 AM


# Helper Functions

def send_color_array(color_array):
    """
    Send color data array to LED strip via SPI.

    Args:
        color_array: List of RGB values (flattened, length should be NUM_LEDS * 3)
    """
    spi.xfer2(color_array)


def repeat_color(color, count):
    """
    Repeat a single RGB color for a given number of LEDs.

    Args:
        color: RGB color as [R, G, B]
        count: Number of LEDs to repeat the color for

    Returns:
        Flattened list of RGB values
    """
    return color * count


def create_led_array(color, num_leds):
    """
    Create a full LED array with the same color for all LEDs.

    Args:
        color: RGB color as [R, G, B]
        num_leds: Number of LEDs in the strip

    Returns:
        Flattened list of RGB values for all LEDs
    """
    return repeat_color(color, num_leds)


def calculate_sine_gradient(frequency_r, frequency_g, frequency_b, phase_r, phase_g, phase_b, position):
    """
    Calculate RGB color values using sine wave gradients.

    Args:
        frequency_r: Frequency for red channel
        frequency_g: Frequency for green channel
        frequency_b: Frequency for blue channel
        phase_r: Phase offset for red channel
        phase_g: Phase offset for green channel
        phase_b: Phase offset for blue channel
        position: Current position in the gradient

    Returns:
        RGB color as [R, G, B] with values 0-255
    """
    r = (math.sin(frequency_r * position + phase_r) * 0.5 + 0.5) * 255
    g = (math.sin(frequency_g * position + phase_g) * 0.5 + 0.5) * 255
    b = (math.sin(frequency_b * position + phase_b) * 0.5 + 0.5) * 255
    return [math.floor(r), math.floor(g), math.floor(b)]


def set_led_color(led_array, led_index, color):
    """
    Set a specific LED's color in the flattened array.

    Args:
        led_array: Flattened LED array (will be modified)
        led_index: Index of the LED (0-based)
        color: RGB color as [R, G, B]
    """
    base_index = led_index * 3
    led_array[base_index] = color[0]
    led_array[base_index + 1] = color[1]
    led_array[base_index + 2] = color[2]


def create_wave_pattern(base_color, wave_color, wave_length, position, num_leds):
    """
    Create a wave pattern that moves across the LED strip.

    Args:
        base_color: Background color as [R, G, B]
        wave_color: Wave highlight color as [R, G, B]
        wave_length: Number of LEDs in the wave
        position: Current position of the wave (0 to num_leds)
        num_leds: Total number of LEDs

    Returns:
        Flattened list of RGB values for all LEDs
    """
    led_array = create_led_array(base_color, num_leds)
    for i in range(wave_length):
        led_pos = (position + i) % num_leds
        set_led_color(led_array, led_pos, wave_color)
    return led_array


def create_fading_wave_pattern(base_color, wave_color, fade_length, position, num_leds):
    """
    Create a fading wave pattern that moves across the LED strip.
    The wave has decreasing brightness from front to back.

    Args:
        base_color: Background color as [R, G, B]
        wave_color: Base wave color as [R, G, B] (will be faded)
        fade_length: Number of LEDs in the fading wave
        position: Current position of the wave (0 to num_leds)
        num_leds: Total number of LEDs

    Returns:
        Flattened list of RGB values for all LEDs
    """
    led_array = []

    # Base color before the wave
    led_array.extend(repeat_color(base_color, position))

    # Fading wave with decreasing brightness
    for fade_step in range(fade_length):
        brightness_factor = 1.0 / (((fade_length - fade_step) * 2) + 1)
        faded_color = [
            math.floor(wave_color[0] * brightness_factor),
            math.floor(wave_color[1] * brightness_factor),
            math.floor(wave_color[2] * brightness_factor)
        ]
        led_array.extend(repeat_color(faded_color, 1))

    # Base color after the wave
    remaining_leds = num_leds - position - fade_length
    if remaining_leds > 0:
        led_array.extend(repeat_color(base_color, remaining_leds))

    return led_array

def animate_rotating_colors_frame(state):
    """
    Animate a rotating color pattern across a subset of LEDs (single frame).
    Cycles through red, green, blue, and magenta colors.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'led_offset': 0}

    colors = [
        [255, 0, 0],    # Red
        [0, 255, 0],    # Green
        [0, 0, 255],    # Blue
        [255, 0, 255]   # Magenta
    ]
    num_leds_in_pattern = 40

    color_index = ((state['cycle'] + state['led_offset']) % len(colors))
    current_color = colors[color_index]
    color_array = repeat_color(current_color, 3)
    send_color_array(color_array)

    state['led_offset'] += 1
    if state['led_offset'] >= num_leds_in_pattern:
        state['led_offset'] = 0
        state['cycle'] += 1

    return state

def animate_solid_color_cycle_frame(state):
    """
    Animate by filling all LEDs with a single color, cycling through red, green, and blue (single frame).

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'frame': 0}

    colors = [
        [255, 0, 0],   # Red
        [0, 255, 0],   # Green
        [0, 0, 255]    # Blue
    ]
    num_leds = 40
    FRAMES_PER_COLOR = 10  # 0.1 seconds * 10 frames per second = 1 second per color

    current_color = colors[state['cycle'] % len(colors)]
    color_array = repeat_color(current_color, num_leds)
    send_color_array(color_array)

    state['frame'] += 1
    if state['frame'] >= FRAMES_PER_COLOR:
        state['frame'] = 0
        state['cycle'] += 1

    return state

def animate_white_wave_frame(state):
    """
    Animate a white wave that moves across the LED strip with a fading tail (single frame).
    Creates a wave effect with decreasing brightness behind the leading edge.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'wave_position': 0}

    WHITE_WAVE_FADE_LENGTH = 10
    BLACK = [0, 0, 0]
    WHITE = [255, 255, 255]

    led_array = create_fading_wave_pattern(BLACK, WHITE, WHITE_WAVE_FADE_LENGTH,
                                          state['wave_position'], NUM_LEDS)
    send_color_array(led_array)

    state['wave_position'] += 1
    if state['wave_position'] >= NUM_LEDS:
        state['wave_position'] = 0
        state['cycle'] += 1

    return state

def animate_orange_wave_frame(state):
    """
    Animate an orange wave that moves across the LED strip (single frame).
    Uses the favorite orange color as background with a bright orange wave.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'wave_position': 0}

    WAVE_COLOR = [255, 50, 3]  # Bright orange highlight
    WAVE_LENGTH = 15

    led_array = create_wave_pattern(FAVORITE_COLOR, WAVE_COLOR, WAVE_LENGTH,
                                  state['wave_position'], NUM_LEDS)
    send_color_array(led_array)

    state['wave_position'] += 1
    if state['wave_position'] >= NUM_LEDS:
        state['wave_position'] = 0
        state['cycle'] += 1

    return state


def animate_gradient_wave_frame(state):
    """
    Animate a smooth gradient wave that cycles through colors using sine wave functions (single frame).
    Creates a flowing color effect across all LEDs.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'step': 0}

    GRADIENT_STEPS = 418
    GRADIENT_SPEED = 0.1
    FREQUENCY = 0.3
    PHASE_R = 0
    PHASE_G = 2
    PHASE_B = 3

    position = state['step'] * GRADIENT_SPEED
    color = calculate_sine_gradient(FREQUENCY, FREQUENCY, FREQUENCY,
                                   PHASE_R, PHASE_G, PHASE_B, position)
    color_array = repeat_color(color, NUM_LEDS)
    send_color_array(color_array)

    state['step'] += 1
    if state['step'] >= GRADIENT_STEPS:
        state['step'] = 0
        state['cycle'] += 1

    return state

def animate_gradient_wave_no_blue_frame(state):
    """
    Animate a smooth gradient wave without blue channel (red and green only) (single frame).
    Creates a warm color effect across all LEDs.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'step': 0}

    GRADIENT_STEPS = 418
    GRADIENT_SPEED = 0.1
    FREQUENCY = 0.3
    PHASE_R = 0
    PHASE_G = 2
    PHASE_B = 3

    position = state['step'] * GRADIENT_SPEED
    color = calculate_sine_gradient(FREQUENCY, FREQUENCY, FREQUENCY,
                                   PHASE_R, PHASE_G, PHASE_B, position)
    color[2] = 0  # Remove blue channel
    color_array = repeat_color(color, NUM_LEDS)
    send_color_array(color_array)

    state['step'] += 1
    if state['step'] >= GRADIENT_STEPS:
        state['step'] = 0
        state['cycle'] += 1

    return state

def animate_sparkle_frame(state):
    """
    Animate random sparkles on a background of favorite color (single frame).
    Two random LEDs light up with a yellow-white color each frame.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'frame': 0}

    SPARKLE_COLOR = [200, 200, 80]  # Yellow-white sparkle
    NUM_SPARKLES = 2
    MAX_LED_INDEX = NUM_LEDS - NUM_SPARKLES  # Ensure we don't overflow array

    led_array = create_led_array(FAVORITE_COLOR, NUM_LEDS)

    # Set random LEDs to sparkle color
    for _ in range(NUM_SPARKLES):
        led_index = random.randint(0, MAX_LED_INDEX)
        set_led_color(led_array, led_index, SPARKLE_COLOR)

    send_color_array(led_array)
    state['frame'] += 1
    return state

def animate_slow_sparkle_frame(state):
    """
    Animate slow, occasional sparkles on a background of favorite color (single frame).
    Sparkles appear infrequently with longer pauses between frames.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None or not isinstance(state, dict) or 'phase' not in state:
        state = {'frame': 0, 'phase': 'sparkle'}  # phase: 'sparkle' or 'pause'

    SPARKLE_COLOR = [180, 180, 180]  # White sparkle
    SPARKLE_FREQUENCY = 100  # Sparkle every N frames
    MAX_LED_INDEX = NUM_LEDS - 1
    PAUSE_FRAMES = 40  # 2.0 seconds / 0.05 seconds per frame

    if state['phase'] == 'sparkle':
        led_array = create_led_array(FAVORITE_COLOR, NUM_LEDS)

        # Occasionally add a sparkle
        if state['frame'] % SPARKLE_FREQUENCY == 0:
            led_index = random.randint(0, MAX_LED_INDEX)
            set_led_color(led_array, led_index, SPARKLE_COLOR)

        send_color_array(led_array)
        state['frame'] += 1

        # Switch to pause phase after sparkle
        if state['frame'] % SPARKLE_FREQUENCY == 0:
            state['phase'] = 'pause'
            state['pause_frame'] = 0
    else:
        # Pause phase - show base color
        led_array = create_led_array(FAVORITE_COLOR, NUM_LEDS)
        send_color_array(led_array)
        state['pause_frame'] = state.get('pause_frame', 0) + 1

        if state['pause_frame'] >= PAUSE_FRAMES:
            state['phase'] = 'sparkle'
            del state['pause_frame']

    return state

def animate_random_colors_frame(state):
    """
    Animate random colors for each LED independently (single frame).
    Each LED gets a random RGB value each frame.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'frame': 0}

    num_color_values = NUM_LEDS * 3  # RGB values for all LEDs
    color_array = [random.randint(0, 255) for _ in range(num_color_values)]
    send_color_array(color_array)
    state['frame'] += 1
    return state

def animate_color_chase_frame(state):
    """
    Animate a color chase pattern with red, green, and cyan colors separated by black (single frame).
    Creates a moving pattern effect across the LED strip.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'frame': 0}

    # Pattern: Red, 2x Black, Green, 2x Black, Cyan, 2x Black (repeating)
    color_pattern = [
        255, 0, 0,      # Red
        0, 0, 0,        # Black
        0, 0, 0,        # Black
        0, 255, 0,      # Green
        0, 0, 0,        # Black
        0, 0, 0,        # Black
        0, 255, 255,    # Cyan
        0, 0, 0,        # Black
        0, 0, 0         # Black
    ]
    FRAMES_PER_STEP = 50  # 0.5 seconds * 100 frames per second

    num_values = NUM_LEDS * 3
    color_array = [color_pattern[(i + (state['cycle'] * 3)) % len(color_pattern)]
                   for i in range(num_values)]
    send_color_array(color_array)

    state['frame'] += 1
    if state['frame'] >= FRAMES_PER_STEP:
        state['frame'] = 0
        state['cycle'] += 1

    return state

def crazy_police_frame(state):
    """
    Flash the top half and bottom half of the LED strand separately in red and blue (single frame).
    One half rapidly flashes for 1 second, then the other half for 1 second, repeating.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'phase': 'top_on', 'flash': 0}  # phase: 'top_on', 'top_off', 'bottom_on', 'bottom_off'

    RED = [255, 0, 0]
    BLUE = [0, 0, 255]
    BLACK = [0, 0, 0]
    FLASH_DURATION_FRAMES = 5  # Half the original duration for twice the speed

    HALF_LED_COUNT = NUM_LEDS // 2
    TOP_HALF_START = 0
    TOP_HALF_END = HALF_LED_COUNT
    BOTTOM_HALF_START = HALF_LED_COUNT
    BOTTOM_HALF_END = NUM_LEDS

    if state['phase'] == 'top_on':
        led_array = create_led_array(BLACK, NUM_LEDS)
        for led_index in range(TOP_HALF_START, TOP_HALF_END):
            set_led_color(led_array, led_index, RED)
        send_color_array(led_array)
        state['phase'] = 'top_off'
    elif state['phase'] == 'top_off':
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        state['flash'] += 1
        if state['flash'] >= FLASH_DURATION_FRAMES:
            state['flash'] = 0
            state['phase'] = 'bottom_on'
        else:
            state['phase'] = 'top_on'
    elif state['phase'] == 'bottom_on':
        led_array = create_led_array(BLACK, NUM_LEDS)
        for led_index in range(BOTTOM_HALF_START, BOTTOM_HALF_END):
            set_led_color(led_array, led_index, BLUE)
        send_color_array(led_array)
        state['phase'] = 'bottom_off'
    elif state['phase'] == 'bottom_off':
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        state['flash'] += 1
        if state['flash'] >= FLASH_DURATION_FRAMES:
            state['flash'] = 0
            state['cycle'] += 1
            state['phase'] = 'top_on'
        else:
            state['phase'] = 'bottom_on'

    return state


def crazy_strobe_frame(state):
    """
    Divide the LED strand into 10 segments and violently flash 3 segments at a time (single frame).
    in a strobe-like fashion for 500ms, then switch to different segments.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'phase': 'on', 'flash': 0, 'segments_to_light': None}

    NUM_SEGMENTS = 10
    SEGMENT_SIZE = NUM_LEDS // NUM_SEGMENTS
    SEGMENTS_TO_FLASH = 3
    FLASH_DURATION_FRAMES = 10  # 0.5 seconds / 0.05 seconds per flash
    WHITE = [255, 255, 255]
    BLACK = [0, 0, 0]

    # Initialize segments on new cycle
    if state['segments_to_light'] is None or (state['flash'] == 0 and state['phase'] == 'on'):
        state['segments_to_light'] = random.sample(range(NUM_SEGMENTS), SEGMENTS_TO_FLASH)

    if state['phase'] == 'on':
        led_array = create_led_array(BLACK, NUM_LEDS)
        for segment_index in state['segments_to_light']:
            segment_start = segment_index * SEGMENT_SIZE
            segment_end = min(segment_start + SEGMENT_SIZE, NUM_LEDS)
            for led_index in range(segment_start, segment_end):
                set_led_color(led_array, led_index, WHITE)
        send_color_array(led_array)
        state['phase'] = 'off'
    else:
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        state['flash'] += 1
        if state['flash'] >= FLASH_DURATION_FRAMES:
            state['flash'] = 0
            state['cycle'] += 1
        state['phase'] = 'on'

    return state


def crazy_race_frame(state):
    """
    Two colors race from opposite ends of the strand, meeting in the middle (single frame).
    Creates a high-speed collision effect with rapid color changes, strobe effects, and random direction changes.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'cycle': 0,
            'phase': 'race',
            'position': 0,
            'collision_frame': 0,
            'direction': 1,  # 1 for forward, -1 for backward
            'time_since_direction_change': 0,
            'red_direction': 1,  # Direction for red (1 = forward from start, -1 = backward from end)
            'blue_direction': -1  # Direction for blue (1 = forward from start, -1 = backward from end)
        }

    RED = [255, 0, 0]
    BLUE = [0, 0, 255]
    BLACK = [0, 0, 0]
    WHITE = [255, 255, 255]
    COLLISION_FRAMES = 8  # 0.08 seconds * 100 frames per second
    MID_POINT = NUM_LEDS // 2
    SPEED = 3  # Move 3 positions per frame for increased speed
    DIRECTION_CHANGE_INTERVAL = 300  # 3 seconds at 100 FPS

    # Check if it's time to randomly change direction
    state['time_since_direction_change'] += 1
    if state['time_since_direction_change'] >= DIRECTION_CHANGE_INTERVAL:
        # Randomly change direction for both colors
        if random.random() < 0.5:
            state['red_direction'] *= -1
        if random.random() < 0.5:
            state['blue_direction'] *= -1
        state['time_since_direction_change'] = 0

    if state['phase'] == 'race':
        led_array = create_led_array(BLACK, NUM_LEDS)

        # Calculate positions based on direction
        if state['red_direction'] == 1:
            red_pos = state['position']
        else:
            red_pos = NUM_LEDS - 1 - state['position']

        if state['blue_direction'] == 1:
            blue_pos = state['position']
        else:
            blue_pos = NUM_LEDS - 1 - state['position']

        # Draw racing colors
        if 0 <= red_pos < NUM_LEDS:
            set_led_color(led_array, red_pos, RED)
        if 0 <= blue_pos < NUM_LEDS:
            set_led_color(led_array, blue_pos, BLUE)

        # Add random strobe effect - flash random LEDs white
        if random.random() < 0.15:  # 15% chance per frame
            strobe_count = random.randint(3, 8)  # Flash 3-8 random LEDs
            for _ in range(strobe_count):
                strobe_pos = random.randint(0, NUM_LEDS - 1)
                if strobe_pos != red_pos and strobe_pos != blue_pos:  # Don't override racing colors
                    set_led_color(led_array, strobe_pos, WHITE)

        send_color_array(led_array)

        state['position'] += SPEED
        if state['position'] > NUM_LEDS:
            state['phase'] = 'collision'
            state['position'] = 0
    elif state['phase'] == 'collision':
        led_array = create_led_array(BLACK, NUM_LEDS)
        for i in range(-2, 3):
            if 0 <= MID_POINT + i < NUM_LEDS:
                set_led_color(led_array, MID_POINT + i, [255, 0, 255])  # Magenta collision
        send_color_array(led_array)
        state['collision_frame'] += 1
        if state['collision_frame'] >= COLLISION_FRAMES:
            state['phase'] = 'off'
            state['collision_frame'] = 0
    else:  # phase == 'off'
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        state['collision_frame'] += 1
        if state['collision_frame'] >= COLLISION_FRAMES:
            state['cycle'] += 1
            state['phase'] = 'race'
            state['collision_frame'] = 0
            # Reset to starting positions with random directions
            state['position'] = 0
            state['red_direction'] = random.choice([1, -1])
            state['blue_direction'] = random.choice([1, -1])

    return state


def crazy_pulse_frame(state):
    """
    Fast expanding pulses from center outward, with top and bottom pulses at different intervals.
    Top pulse every 375ms, bottom pulse every 325ms. Each pulse changes color and includes strobe effects.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'top_frame': 0,
            'bottom_frame': 0,
            'top_color_index': 0,
            'bottom_color_index': 1,
            'top_radius': 0,
            'bottom_radius': 0
        }

    COLORS = [
        [255, 0, 0],      # Red
        [0, 255, 0],      # Green
        [0, 0, 255],      # Blue
        [255, 255, 0],    # Yellow
        [255, 0, 255],    # Magenta
        [0, 255, 255],    # Cyan
        [255, 127, 0],    # Orange
        [148, 0, 211]     # Violet
    ]
    BLACK = [0, 0, 0]
    WHITE = [255, 255, 255]
    CENTER = NUM_LEDS // 2
    MAX_RADIUS = NUM_LEDS // 2
    TOP_INTERVAL = 38  # 375ms at 100 FPS (0.01s per frame)
    BOTTOM_INTERVAL = 33  # 325ms at 100 FPS
    PULSE_SPEED = 4  # Fast expansion - 4 LEDs per frame

    led_array = create_led_array(BLACK, NUM_LEDS)

    # Top pulse (every 375ms)
    if state['top_frame'] >= TOP_INTERVAL:
        # Start new pulse
        state['top_frame'] = 0
        state['top_radius'] = 0
        # Change to a different color (ensure it's different from bottom)
        new_color_index = state['top_color_index']
        while new_color_index == state['bottom_color_index']:
            new_color_index = random.randint(0, len(COLORS) - 1)
        state['top_color_index'] = new_color_index

    # Draw top pulse if active
    if state['top_radius'] <= MAX_RADIUS:
        top_color = COLORS[state['top_color_index']]
        for offset in range(-state['top_radius'], state['top_radius'] + 1):
            led_pos = CENTER + offset
            if 0 <= led_pos < NUM_LEDS:
                distance = abs(offset)
                brightness = max(0, 255 - (distance * 3))  # Faster fade for speed
                faded_color = [
                    min(255, int(top_color[0] * brightness / 255)),
                    min(255, int(top_color[1] * brightness / 255)),
                    min(255, int(top_color[2] * brightness / 255))
                ]
                set_led_color(led_array, led_pos, faded_color)
        state['top_radius'] += PULSE_SPEED

    state['top_frame'] += 1

    # Bottom pulse (every 325ms)
    if state['bottom_frame'] >= BOTTOM_INTERVAL:
        # Start new pulse
        state['bottom_frame'] = 0
        state['bottom_radius'] = 0
        # Change to a different color (ensure it's different from top)
        new_color_index = state['bottom_color_index']
        while new_color_index == state['top_color_index']:
            new_color_index = random.randint(0, len(COLORS) - 1)
        state['bottom_color_index'] = new_color_index

    # Draw bottom pulse if active
    if state['bottom_radius'] <= MAX_RADIUS:
        bottom_color = COLORS[state['bottom_color_index']]
        for offset in range(-state['bottom_radius'], state['bottom_radius'] + 1):
            led_pos = CENTER + offset
            if 0 <= led_pos < NUM_LEDS:
                distance = abs(offset)
                brightness = max(0, 255 - (distance * 3))  # Faster fade for speed
                faded_color = [
                    min(255, int(bottom_color[0] * brightness / 255)),
                    min(255, int(bottom_color[1] * brightness / 255)),
                    min(255, int(bottom_color[2] * brightness / 255))
                ]
                set_led_color(led_array, led_pos, faded_color)
        state['bottom_radius'] += PULSE_SPEED

    state['bottom_frame'] += 1

    # Add random strobe effect - flash random LEDs white
    if random.random() < 0.13:  # 13% chance per frame
        strobe_count = random.randint(2, 5)  # Flash 2-5 random LEDs
        for _ in range(strobe_count):
            strobe_pos = random.randint(0, NUM_LEDS - 1)
            # Check if this position isn't already lit by a pulse
            is_pulse_pos = False
            # Check top pulse
            if state['top_radius'] > 0 and state['top_radius'] <= MAX_RADIUS:
                for offset in range(-state['top_radius'], state['top_radius'] + 1):
                    led_pos = CENTER + offset
                    if 0 <= led_pos < NUM_LEDS and led_pos == strobe_pos:
                        is_pulse_pos = True
                        break
            # Check bottom pulse
            if not is_pulse_pos and state['bottom_radius'] > 0 and state['bottom_radius'] <= MAX_RADIUS:
                for offset in range(-state['bottom_radius'], state['bottom_radius'] + 1):
                    led_pos = CENTER + offset
                    if 0 <= led_pos < NUM_LEDS and led_pos == strobe_pos:
                        is_pulse_pos = True
                        break
            if not is_pulse_pos:
                set_led_color(led_array, strobe_pos, WHITE)

    send_color_array(led_array)

    return state


def crazy_rainbow_chase_frame(state):
    """
    Rapid rainbow colors chasing each other across the strand (single frame).
    Multiple color bands move at different speeds creating a chaotic rainbow effect.
    Enhanced with strobe effects, increased speed, and random direction changes.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'cycle': 0,
            'step': 0,
            'direction': 1,  # 1 for forward, -1 for backward
            'time_since_direction_change': 0
        }

    RAINBOW_COLORS = [
        [255, 0, 0],      # Red
        [255, 127, 0],    # Orange
        [255, 255, 0],    # Yellow
        [0, 255, 0],      # Green
        [0, 0, 255],      # Blue
        [75, 0, 130],      # Indigo
        [148, 0, 211]     # Violet
    ]
    BLACK = [0, 0, 0]
    WHITE = [255, 255, 255]
    BAND_WIDTH = 8  # LEDs per color band
    NUM_BANDS = 3  # Number of overlapping bands
    SPEED = 3  # Move 3 positions per frame for increased speed
    MAX_STEPS = NUM_LEDS + BAND_WIDTH * NUM_BANDS
    DIRECTION_CHANGE_INTERVAL = 300  # 3 seconds at 100 FPS

    # Check if it's time to randomly change direction
    state['time_since_direction_change'] += 1
    if state['time_since_direction_change'] >= DIRECTION_CHANGE_INTERVAL:
        if random.random() < 0.5:  # 50% chance to reverse direction
            state['direction'] *= -1
        state['time_since_direction_change'] = 0

    led_array = create_led_array(BLACK, NUM_LEDS)

    # Draw multiple overlapping bands
    for band in range(NUM_BANDS):
        # Calculate band start position based on direction
        if state['direction'] == 1:
            band_start = state['step'] - (band * BAND_WIDTH * 2)
        else:
            band_start = (MAX_STEPS - state['step']) - (band * BAND_WIDTH * 2)

        color_index = (band + state['cycle']) % len(RAINBOW_COLORS)
        color = RAINBOW_COLORS[color_index]

        for i in range(BAND_WIDTH):
            led_pos = band_start + i
            if 0 <= led_pos < NUM_LEDS:
                set_led_color(led_array, led_pos, color)

    # Add random strobe effect - flash random LEDs white
    if random.random() < 0.14:  # 14% chance per frame
        strobe_count = random.randint(3, 7)  # Flash 3-7 random LEDs
        for _ in range(strobe_count):
            strobe_pos = random.randint(0, NUM_LEDS - 1)
            # Check if this position isn't already lit by a rainbow band
            is_band_pos = False
            for band in range(NUM_BANDS):
                if state['direction'] == 1:
                    band_start = state['step'] - (band * BAND_WIDTH * 2)
                else:
                    band_start = (MAX_STEPS - state['step']) - (band * BAND_WIDTH * 2)
                for i in range(BAND_WIDTH):
                    led_pos = band_start + i
                    if led_pos == strobe_pos and 0 <= led_pos < NUM_LEDS:
                        is_band_pos = True
                        break
                if is_band_pos:
                    break
            if not is_band_pos:
                set_led_color(led_array, strobe_pos, WHITE)

    send_color_array(led_array)

    state['step'] += SPEED
    if state['step'] >= MAX_STEPS:
        state['step'] = 0
        state['cycle'] += 1
        # Randomly reset direction on cycle completion
        state['direction'] = random.choice([1, -1])

    return state


def crazy_chaos_frame(state):
    """
    Random segments flash violently in different colors creating pure chaos (single frame).
    Each segment gets a random color and flashes rapidly.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {'cycle': 0, 'phase': 'on', 'flash': 0, 'segment_colors': None}

    COLORS = [
        [255, 0, 0],      # Red
        [0, 255, 0],      # Green
        [0, 0, 255],      # Blue
        [255, 255, 0],    # Yellow
        [255, 0, 255],    # Magenta
        [0, 255, 255],    # Cyan
        [255, 255, 255]   # White
    ]
    BLACK = [0, 0, 0]
    NUM_SEGMENTS = 20
    SEGMENT_SIZE = NUM_LEDS // NUM_SEGMENTS
    FLASH_DURATION_FRAMES = 3  # 0.15 seconds / 0.05 seconds per frame

    # Initialize segment colors on new cycle
    if state['segment_colors'] is None or (state['flash'] == 0 and state['phase'] == 'on'):
        state['segment_colors'] = [random.choice(COLORS) for _ in range(NUM_SEGMENTS)]

    if state['phase'] == 'on':
        led_array = create_led_array(BLACK, NUM_LEDS)
        segments_to_flash = random.sample(range(NUM_SEGMENTS), NUM_SEGMENTS // 2)
        for segment_index in segments_to_flash:
            segment_start = segment_index * SEGMENT_SIZE
            segment_end = min(segment_start + SEGMENT_SIZE, NUM_LEDS)
            color = state['segment_colors'][segment_index]
            for led_index in range(segment_start, segment_end):
                set_led_color(led_array, led_index, color)
        send_color_array(led_array)
        state['phase'] = 'off'
    else:
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        state['flash'] += 1
        if state['flash'] >= FLASH_DURATION_FRAMES:
            state['flash'] = 0
            state['cycle'] += 1
        state['phase'] = 'on'

    return state


def crazy_meteor_frame(state):
    """
    Multiple meteors of different colors shoot across the strand simultaneously (single frame).
    Each meteor has a bright head and fading tail creating a streaking effect.
    Enhanced with strobe effects, increased speed, and random direction changes.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'cycle': 0,
            'step': 0,
            'meteors': None,
            'pause_frame': 0,
            'time_since_direction_change': 0
        }

    METEOR_COLORS = [
        [255, 100, 50],   # Orange
        [100, 255, 255],  # Cyan
        [255, 50, 255],   # Pink
        [50, 255, 100],   # Green
        [255, 255, 100],  # Yellow
        [100, 100, 255]   # Light Blue
    ]
    BLACK = [0, 0, 0]
    WHITE = [255, 255, 255]
    NUM_METEORS = 4
    METEOR_LENGTH = 12  # LEDs in meteor tail
    SPEED = 3  # Move 3 positions per frame for increased speed
    MAX_STEPS = (NUM_LEDS + METEOR_LENGTH) // SPEED  # Adjusted for faster speed
    PAUSE_FRAMES = 2  # 0.1 seconds / 0.05 seconds per frame
    DIRECTION_CHANGE_INTERVAL = 300  # 3 seconds at 100 FPS

    # Initialize meteors on new cycle
    if state['meteors'] is None or (state['step'] == 0 and state['pause_frame'] == 0):
        state['meteors'] = []
        for _ in range(NUM_METEORS):
            start_pos = random.randint(-METEOR_LENGTH, NUM_LEDS)
            color = random.choice(METEOR_COLORS)
            direction = random.choice([1, -1])  # 1 = left to right, -1 = right to left
            state['meteors'].append({
                'pos': start_pos,
                'color': color,
                'direction': direction
            })

    # Check if it's time to randomly change direction
    if state['pause_frame'] == 0:  # Only change direction during active animation
        state['time_since_direction_change'] += 1
        if state['time_since_direction_change'] >= DIRECTION_CHANGE_INTERVAL:
            # Randomly change direction for each meteor
            for meteor in state['meteors']:
                if random.random() < 0.5:  # 50% chance to reverse direction
                    meteor['direction'] *= -1
            state['time_since_direction_change'] = 0

    if state['pause_frame'] > 0:
        led_array = create_led_array(BLACK, NUM_LEDS)
        send_color_array(led_array)
        state['pause_frame'] += 1
        if state['pause_frame'] >= PAUSE_FRAMES:
            state['pause_frame'] = 0
            state['step'] = 0
            state['cycle'] += 1
            state['meteors'] = None  # Reset for next cycle
            state['time_since_direction_change'] = 0
    else:
        led_array = create_led_array(BLACK, NUM_LEDS)
        for meteor in state['meteors']:
            # Update meteor position with increased speed
            meteor['pos'] += meteor['direction'] * SPEED
            # Draw meteor with fading tail
            for i in range(METEOR_LENGTH):
                led_pos = meteor['pos'] - (i * meteor['direction'] * SPEED)
                if 0 <= led_pos < NUM_LEDS:
                    brightness = 1.0 - (i / METEOR_LENGTH)
                    faded_color = [
                        int(meteor['color'][0] * brightness),
                        int(meteor['color'][1] * brightness),
                        int(meteor['color'][2] * brightness)
                    ]
                    set_led_color(led_array, led_pos, faded_color)

        # Add random strobe effect - flash random LEDs white
        if random.random() < 0.12:  # 12% chance per frame
            strobe_count = random.randint(2, 6)  # Flash 2-6 random LEDs
            for _ in range(strobe_count):
                strobe_pos = random.randint(0, NUM_LEDS - 1)
                # Check if this position isn't already lit by a meteor
                is_meteor_pos = False
                for meteor in state['meteors']:
                    for i in range(METEOR_LENGTH):
                        led_pos = meteor['pos'] - (i * meteor['direction'] * SPEED)
                        if led_pos == strobe_pos and 0 <= led_pos < NUM_LEDS:
                            is_meteor_pos = True
                            break
                    if is_meteor_pos:
                        break
                if not is_meteor_pos:
                    set_led_color(led_array, strobe_pos, WHITE)

        send_color_array(led_array)
        state['step'] += 1
        if state['step'] >= MAX_STEPS:
            state['pause_frame'] = 1

    return state


def test_color_comparison():
    """
    Test function to compare two similar orange colors by alternating between them.
    Useful for fine-tuning color values. Runs indefinitely until interrupted.
    """
    color1 = [255, 25, 2]
    color2 = [255, 30, 2]

    while True:
        color_array = create_led_array(color1, NUM_LEDS)
        print(color1)
        send_color_array(color_array)
        time.sleep(1)

        color_array = create_led_array(color2, NUM_LEDS)
        print(color2)
        send_color_array(color_array)
        time.sleep(1)



# Main animation loop
# Different animation sequences run based on time of day
def is_daytime():
    """
    Check if current time is during daytime hours (after 6 AM).

    Returns:
        True if current time is after 6 AM, False otherwise
    """
    now = datetime.datetime.now()
    return now.hour >= DAYTIME_START_HOUR


def run_daytime_frame(state):
    """
    Run gentler animations suitable for daytime viewing (single frame).
    Cycles through orange wave and slow sparkle animations.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'sequence_index': 0,
            'animation_state': None,
            'frame_count': 0
        }

    # Orange wave: 60 cycles * 100 positions = 6000 frames
    # Slow sparkle: 1800 frames (but with pauses, so longer)
    animations = [
        (animate_orange_wave_frame, 6000, 'Orange Wave'),  # 60 cycles
        (animate_slow_sparkle_frame, 18000, 'Slow Sparkle')   # 1800 frames with pauses
    ]

    # Ensure sequence_index exists and is valid
    if 'sequence_index' not in state or not isinstance(state['sequence_index'], int) or state['sequence_index'] < 0 or state['sequence_index'] >= len(animations):
        state['sequence_index'] = 0
        state['animation_state'] = None
        state['frame_count'] = 0

    # Check for navigation request
    nav_request = get_navigation_request()
    if nav_request == 'next':
        state['sequence_index'] = (state['sequence_index'] + 1) % len(animations)
        state['animation_state'] = None
        state['frame_count'] = 0
    elif nav_request == 'previous':
        new_index = state['sequence_index'] - 1
        state['sequence_index'] = new_index if new_index >= 0 else len(animations) - 1
        state['animation_state'] = None
        state['frame_count'] = 0

    anim_func, max_frames, func_name = animations[state['sequence_index']]
    set_current_function_name(func_name)

    # Run current animation frame
    state['animation_state'] = anim_func(state['animation_state'])
    state['frame_count'] += 1

    # Check if animation is complete (only advance if not paused)
    if state['frame_count'] >= max_frames:
        if not get_pause_state():
            state['sequence_index'] = (state['sequence_index'] + 1) % len(animations)
            state['animation_state'] = None
            state['frame_count'] = 0
        # When paused, animation continues running but sequence doesn't advance

    return state


def run_nighttime_frame(state):
    """
    Run more active animations suitable for nighttime viewing (single frame).
    Cycles through multiple animations.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'sequence_index': 0,
            'animation_state': None,
            'frame_count': 0
        }

    # Calculate approximate frame counts
    animations = [
        (animate_white_wave_frame, 6000, 'White Wave'),              # 60 cycles * 100 positions
        (animate_sparkle_frame, 1800, 'Sparkle'),                  # 1800 frames
        (animate_random_colors_frame, 400, 'Random Colors'),              # 400 frames
        (animate_gradient_wave_no_blue_frame, 3344, 'Gradient Wave'),    # 8 cycles * 418 steps
        (animate_sparkle_frame, 1000, 'Sparkle')                   # 1000 frames
    ]

    # Ensure sequence_index exists and is valid
    if 'sequence_index' not in state or not isinstance(state['sequence_index'], int) or state['sequence_index'] < 0 or state['sequence_index'] >= len(animations):
        state['sequence_index'] = 0
        state['animation_state'] = None
        state['frame_count'] = 0

    # Check for navigation request
    nav_request = get_navigation_request()
    if nav_request == 'next':
        state['sequence_index'] = (state['sequence_index'] + 1) % len(animations)
        state['animation_state'] = None
        state['frame_count'] = 0
    elif nav_request == 'previous':
        new_index = state['sequence_index'] - 1
        state['sequence_index'] = new_index if new_index >= 0 else len(animations) - 1
        state['animation_state'] = None
        state['frame_count'] = 0

    anim_func, max_frames, func_name = animations[state['sequence_index']]
    set_current_function_name(func_name)

    # Run current animation frame
    state['animation_state'] = anim_func(state['animation_state'])
    state['frame_count'] += 1

    # Check if animation is complete (only advance if not paused)
    if state['frame_count'] >= max_frames:
        if not get_pause_state():
            state['sequence_index'] = (state['sequence_index'] + 1) % len(animations)
            state['animation_state'] = None
            state['frame_count'] = 0
        # When paused, animation continues running but sequence doesn't advance

    return state


def animate_crazy_frame(state):
    """
    Cycle through all crazy animation patterns in sequence (single frame).
    Creates an intense, chaotic light show.

    Args:
        state: Animation state dictionary or None to initialize

    Returns:
        Updated state dictionary
    """
    if state is None:
        state = {
            'sequence_index': 0,
            'animation_state': None,
            'frame_count': 0,
            'cycle': 0
        }

    animations = [
        (crazy_police_frame, 3000, 'Police Lights'),      # 30 seconds minimum
        (crazy_strobe_frame, 3000, 'Strobe'),     # 30 seconds minimum
        (crazy_race_frame, 3000, 'Color Race'),       # 30 seconds minimum
        (crazy_pulse_frame, 3000, 'Pulse'),      # 30 seconds minimum
        (crazy_rainbow_chase_frame, 3000, 'Rainbow Chase'),  # 30 seconds minimum
        (crazy_chaos_frame, 3000, 'Chaos'),      # 30 seconds minimum
        (crazy_meteor_frame, 3000, 'Meteors')      # 30 seconds minimum
    ]

    # Ensure sequence_index exists and is valid
    if 'sequence_index' not in state or not isinstance(state['sequence_index'], int) or state['sequence_index'] < 0 or state['sequence_index'] >= len(animations):
        state['sequence_index'] = 0
        state['animation_state'] = None
        state['frame_count'] = 0

    # Check for navigation request
    nav_request = get_navigation_request()
    if nav_request == 'next':
        state['sequence_index'] = (state['sequence_index'] + 1) % len(animations)
        state['animation_state'] = None
        state['frame_count'] = 0
    elif nav_request == 'previous':
        new_index = state['sequence_index'] - 1
        state['sequence_index'] = new_index if new_index >= 0 else len(animations) - 1
        state['animation_state'] = None
        state['frame_count'] = 0

    anim_func, max_frames, func_name = animations[state['sequence_index']]
    set_current_function_name(func_name)

    # Run current animation frame
    state['animation_state'] = anim_func(state['animation_state'])
    state['frame_count'] += 1

    # Check if animation is complete (approximate based on frame count)
    # Only advance if not paused
    if state['frame_count'] >= max_frames:
        if not get_pause_state():
            state['sequence_index'] = (state['sequence_index'] + 1) % len(animations)
            state['animation_state'] = None
            state['frame_count'] = 0
            if state['sequence_index'] == 0:
                state['cycle'] += 1
        # When paused, animation continues running but sequence doesn't advance

    return state

# Thread-safe mode management
_mode_lock = threading.Lock()
_current_mode = 'timemode'  # available modes: timemode, force_night, force_day, force_crazy
_previous_mode = None  # Track mode changes for state reset

def get_current_mode():
    """Get the current animation mode in a thread-safe manner."""
    with _mode_lock:
        return _current_mode

def set_current_mode(mode):
    """Set the current animation mode in a thread-safe manner.

    Args:
        mode: Mode string to set. If invalid, defaults to 'timemode'.

    Returns:
        True if mode was set, False if defaulted to 'timemode'
    """
    global _current_mode, _previous_mode
    valid_modes = ['timemode', 'force_night', 'force_day', 'force_crazy']
    with _mode_lock:
        _previous_mode = _current_mode
        if mode in valid_modes:
            _current_mode = mode
            # Reset animation state if mode changed
            if _previous_mode != _current_mode:
                reset_animation_state()
            return True
        else:
            # Default to timemode if invalid mode provided
            _current_mode = 'timemode'
            if _previous_mode != _current_mode:
                reset_animation_state()
            logger.warning(f"Invalid mode '{mode}' provided, defaulting to 'timemode'")
            return False

# Animation state management
_animation_state_lock = threading.Lock()
_animation_state = None

def get_animation_state():
    """Get the current animation state in a thread-safe manner."""
    with _animation_state_lock:
        return _animation_state

def set_animation_state(state):
    """Set the current animation state in a thread-safe manner."""
    with _animation_state_lock:
        global _animation_state
        _animation_state = state

def reset_animation_state():
    """Reset animation state when mode changes."""
    with _animation_state_lock:
        global _animation_state
        _animation_state = None
        set_current_function_name("Initializing...")
        logger.info("Animation state reset due to mode change")

# Function name tracking
_function_name_lock = threading.Lock()
_current_function_name = "Initializing..."

def get_current_function_name():
    """Get the current animation function name in a thread-safe manner."""
    with _function_name_lock:
        return _current_function_name

def set_current_function_name(name):
    """Set the current animation function name in a thread-safe manner."""
    with _function_name_lock:
        global _current_function_name
        if _current_function_name != name:
            _current_function_name = name

# Function name mapping for all animations
FUNCTION_NAMES = {
    # Daytime animations
    'animate_orange_wave_frame': 'Orange Wave',
    'animate_slow_sparkle_frame': 'Slow Sparkle',

    # Nighttime animations
    'animate_white_wave_frame': 'White Wave',
    'animate_sparkle_frame': 'Sparkle',
    'animate_random_colors_frame': 'Random Colors',
    'animate_gradient_wave_no_blue_frame': 'Gradient Wave',

    # Crazy animations
    'crazy_police_frame': 'Police Lights',
    'crazy_strobe_frame': 'Strobe',
    'crazy_race_frame': 'Color Race',
    'crazy_pulse_frame': 'Pulse',
    'crazy_rainbow_chase_frame': 'Rainbow Chase',
    'crazy_chaos_frame': 'Chaos',
    'crazy_meteor_frame': 'Meteors',

    # Other animations (if used)
    'animate_rotating_colors_frame': 'Rotating Colors',
    'animate_solid_color_cycle_frame': 'Solid Color Cycle',
    'animate_color_chase_frame': 'Color Chase',
    'animate_gradient_wave_frame': 'Gradient Wave Full',
}

# Navigation control
_navigation_lock = threading.Lock()
_navigation_request = None  # 'next', 'previous', or None

def get_navigation_request():
    """Get and clear navigation request in a thread-safe manner."""
    with _navigation_lock:
        global _navigation_request
        request = _navigation_request
        _navigation_request = None
        return request

def set_navigation_request(direction):
    """Set navigation request in a thread-safe manner.

    Args:
        direction: 'next' or 'previous'
    """
    with _navigation_lock:
        global _navigation_request
        _navigation_request = direction

# Pause control
_pause_lock = threading.Lock()
_is_paused = False

def get_pause_state():
    """Get the current pause state in a thread-safe manner."""
    with _pause_lock:
        return _is_paused

def set_pause_state(paused):
    """Set the pause state in a thread-safe manner and broadcast to all clients.

    Args:
        paused: Boolean indicating whether to pause (True) or unpause (False)
    """
    global _is_paused
    state_changed = False
    with _pause_lock:
        if _is_paused != paused:
            _is_paused = paused
            logger.info(f"Animation sequence {'paused' if paused else 'unpaused'}")
            state_changed = True

    # Broadcast outside the lock to avoid deadlock (broadcast_pause_state calls get_pause_state which needs the lock)
    if state_changed:
        broadcast_pause_state()

def broadcast_pause_state():
    """Broadcast current pause state to all connected WebSocket clients."""
    try:
        paused = get_pause_state()
        socketio.emit('pause_state_update', {'paused': paused})
    except Exception as e:
        logger.error(f"Error broadcasting pause state: {e}")


# Flask web server
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/icon.png')
def icon():
    """Serve the app icon for mobile shortcuts."""
    import os
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'assets'), 'icon.png')

@app.route('/manifest.json')
def manifest():
    """Serve the web app manifest for Android."""
    return jsonify({
        "name": "Christmas Tree LED Control",
        "short_name": "Xmas Tree",
        "description": "Control your Christmas tree LED animations",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#667eea",
        "theme_color": "#667eea",
        "icons": [
            {
                "src": "/icon.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })

@app.route('/')
def index():
    """Serve the main web interface."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Christmas Tree LED Control</title>

        <!-- Favicon and App Icons -->
        <link rel="icon" type="image/png" href="/icon.png">
        <link rel="apple-touch-icon" href="/icon.png">
        <link rel="apple-touch-icon" sizes="180x180" href="/icon.png">
        <link rel="apple-touch-icon" sizes="512x512" href="/icon.png">

        <!-- Web App Manifest for Android -->
        <link rel="manifest" href="/manifest.json">

        <!-- Meta tags for mobile -->
        <meta name="theme-color" content="#667eea">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="Xmas Tree">
        <meta name="mobile-web-app-capable" content="yes">

        <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }

            .container {
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                max-width: 600px;
                width: 100%;
            }

            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 10px;
                font-size: 28px;
                font-weight: 600;
            }

            .status {
                text-align: center;
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
            }

            .status .current-mode {
                font-weight: 600;
                color: #667eea;
            }

            .buttons {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 20px;
            }

            .function-display {
                text-align: center;
                margin-top: 30px;
                padding: 15px;
                background: rgba(102, 126, 234, 0.1);
                border-radius: 10px;
                min-height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .function-name {
                font-size: 18px;
                font-weight: 600;
                color: #333;
            }

            .navigation-controls {
                display: flex;
                justify-content: center;
                gap: 15px;
                margin-top: 20px;
            }

            .nav-button {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                min-width: 120px;
            }

            .nav-button:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
            }

            .nav-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .nav-button:active:not(:disabled) {
                transform: translateY(0);
            }

            .nav-button.paused {
                background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%);
            }

            .nav-button.paused:hover:not(:disabled) {
                background: linear-gradient(135deg, #e04459 0%, #e081e8 100%);
            }

            .mode-button {
                padding: 25px 20px;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                text-transform: capitalize;
                color: white;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                position: relative;
                overflow: hidden;
            }

            .mode-button::before {
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                width: 0;
                height: 0;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.3);
                transform: translate(-50%, -50%);
                transition: width 0.6s, height 0.6s;
            }

            .mode-button:hover::before {
                width: 300px;
                height: 300px;
            }

            .mode-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
            }

            .mode-button:active {
                transform: translateY(0);
            }

            .mode-button.active {
                box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.8), 0 4px 15px rgba(0, 0, 0, 0.3);
                transform: scale(1.05);
            }

            .mode-button.timemode {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }

            .mode-button.force_night {
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            }

            .mode-button.force_day {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            }

            .mode-button.force_crazy {
                background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
            }

            .mode-button.timemode:hover {
                background: linear-gradient(135deg, #5568d3 0%, #653a8f 100%);
            }

            .mode-button.force_night:hover {
                background: linear-gradient(135deg, #1a2f5f 0%, #254785 100%);
            }

            .mode-button.force_day:hover {
                background: linear-gradient(135deg, #e081e8 0%, #f24459 100%);
            }

            .mode-button.force_crazy:hover {
                background: linear-gradient(135deg, #f85d87 0%, #fdd02d 100%);
            }

            @media (max-width: 600px) {
                .buttons {
                    grid-template-columns: 1fr;
                }

                .container {
                    padding: 30px 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎄 LED Control</h1>
            <div class="status">
                Current Mode: <span class="current-mode" id="current-mode">Loading...</span>
            </div>
            <div class="buttons">
                <button class="mode-button timemode" onclick="setMode('timemode')">Time Mode</button>
                <button class="mode-button force_night" onclick="setMode('force_night')">Force Night</button>
                <button class="mode-button force_day" onclick="setMode('force_day')">Force Day</button>
                <button class="mode-button force_crazy" onclick="setMode('force_crazy')">Force Crazy</button>
            </div>
            <div class="function-display">
                <div class="function-name" id="function-name">Loading...</div>
            </div>
            <div class="navigation-controls">
                <button class="nav-button" id="rewind-btn" onclick="skipPrevious()">⏮ Previous</button>
                <button class="nav-button" id="pause-btn" onclick="togglePause()">⏸ Pause</button>
                <button class="nav-button" id="forward-btn" onclick="skipNext()">Next ⏭</button>
            </div>
        </div>

        <script>
            // WebSocket connection
            const socket = io();
            let isConnected = false;

            socket.on('connect', function() {
                console.log('WebSocket connected');
                isConnected = true;
            });

            socket.on('disconnect', function() {
                console.log('WebSocket disconnected');
                isConnected = false;
                document.getElementById('function-name').textContent = 'Disconnected';
            });

            socket.on('function_name_update', function(data) {
                document.getElementById('function-name').textContent = data.function_name || 'Unknown';
            });

            socket.on('navigation_response', function(data) {
                if (data.success) {
                    console.log('Navigation:', data.message);
                }
            });

            let isPaused = false;

            socket.on('pause_state_update', function(data) {
                isPaused = data.paused || false;
                updatePauseButton();
            });

            function updatePauseButton() {
                const pauseBtn = document.getElementById('pause-btn');
                if (pauseBtn) {
                    if (isPaused) {
                        pauseBtn.textContent = '▶ Resume';
                        pauseBtn.classList.add('paused');
                    } else {
                        pauseBtn.textContent = '⏸ Pause';
                        pauseBtn.classList.remove('paused');
                    }
                }
            }

            function togglePause() {
                if (isConnected) {
                    if (isPaused) {
                        socket.emit('unpause');
                    } else {
                        socket.emit('pause');
                    }
                }
            }

            function updateCurrentMode() {
                fetch('/api/mode')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('current-mode').textContent = data.mode.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                        updateActiveButton(data.mode);
                    })
                    .catch(error => {
                        console.error('Error fetching mode:', error);
                    });
            }

            function updateActiveButton(mode) {
                document.querySelectorAll('.mode-button').forEach(button => {
                    button.classList.remove('active');
                    if (button.classList.contains(mode)) {
                        button.classList.add('active');
                    }
                });
            }

            function setMode(mode) {
                fetch('/api/mode', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ mode: mode })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateCurrentMode();
                    } else {
                        alert('Error: ' + (data.error || 'Failed to set mode'));
                    }
                })
                .catch(error => {
                    console.error('Error setting mode:', error);
                    alert('Error setting mode');
                });
            }

            function skipNext() {
                if (isConnected) {
                    socket.emit('skip_next');
                }
            }

            function skipPrevious() {
                if (isConnected) {
                    socket.emit('skip_previous');
                }
            }

            // Update mode on page load
            updateCurrentMode();

            // Auto-refresh current mode every 2 seconds
            setInterval(updateCurrentMode, 2000);
        </script>
    </body>
    </html>
    """
    return html

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket client connection."""
    logger.info("WebSocket client connected")
    emit('function_name_update', {'function_name': get_current_function_name()})
    emit('pause_state_update', {'paused': get_pause_state()})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket client disconnection."""
    logger.info("WebSocket client disconnected")

@socketio.on('skip_next')
def handle_skip_next():
    """Handle skip to next animation request."""
    set_navigation_request('next')
    emit('navigation_response', {'success': True, 'message': 'Skipping to next animation'})

@socketio.on('skip_previous')
def handle_skip_previous():
    """Handle skip to previous animation request."""
    set_navigation_request('previous')
    emit('navigation_response', {'success': True, 'message': 'Skipping to previous animation'})

@socketio.on('pause')
def handle_pause():
    """Handle pause request."""
    set_pause_state(True)
    # broadcast_pause_state() is called by set_pause_state(), no need to emit here

@socketio.on('unpause')
def handle_unpause():
    """Handle unpause request."""
    set_pause_state(False)
    # broadcast_pause_state() is called by set_pause_state(), no need to emit here

def broadcast_function_name():
    """Broadcast current function name to all connected WebSocket clients."""
    try:
        function_name = get_current_function_name()
        socketio.emit('function_name_update', {'function_name': function_name})
    except Exception as e:
        logger.error(f"Error broadcasting function name: {e}")

@app.route('/api/mode', methods=['GET'])
def get_mode():
    """Get the current animation mode."""
    return jsonify({'mode': get_current_mode()})

@app.route('/api/mode', methods=['POST'])
def set_mode():
    """Set the animation mode."""
    # Validate Content-Type
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400

    # Handle JSON parsing errors
    try:
        data = request.get_json()
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Validate data exists
    if data is None:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    # Get mode with default handling
    mode = data.get('mode')
    if mode is None:
        logger.warning("No mode provided in request, defaulting to 'timemode'")
        set_current_mode('timemode')  # This will set to timemode
        return jsonify({'success': True, 'mode': get_current_mode(), 'message': 'Defaulted to timemode'})

    # Set mode (will default to timemode if invalid)
    was_valid = set_current_mode(mode)
    current_mode = get_current_mode()

    if was_valid:
        logger.info(f"Mode changed to: {current_mode}")
        return jsonify({'success': True, 'mode': current_mode})
    else:
        # Mode was invalid, but set_current_mode already defaulted to timemode
        return jsonify({
            'success': True,
            'mode': current_mode,
            'message': f"Invalid mode provided, defaulted to '{current_mode}'"
        })

def start_web_server():
    """Start the Flask web server with WebSocket support in a separate thread."""
    try:
        logger.info("Starting web server with WebSocket support on port 80...")
        socketio.run(app, host='0.0.0.0', port=80, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            logger.error(f"Port 80 is already in use. Error: {e}")
        elif e.errno == 13:  # Permission denied
            logger.error(f"Permission denied to bind to port 80. Run with sudo. Error: {e}")
        else:
            logger.error(f"Failed to start web server: {e}")
    except Exception as e:
        logger.error(f"Unexpected error starting web server: {e}")

# Global reference to web thread for graceful shutdown
web_thread = None

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    # Flask server will stop when main thread exits (daemon thread)
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Start web server in background thread
try:
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    # Give the server a moment to start
    time.sleep(0.5)
    logger.info("Web server thread started")
except Exception as e:
    logger.error(f"Failed to start web server thread: {e}")

# Global animation loop - single iteration per cycle
FRAME_DELAY = 0.01  # 10ms per frame = ~100 FPS
BROADCAST_INTERVAL = 10  # Broadcast every 10 frames (0.1 seconds)
_broadcast_counter = 0
_last_broadcasted_function_name = None

while True:
    mode = get_current_mode()
    state = get_animation_state()

    # Reset state if mode changed
    if state is not None and state.get('last_mode') != mode:
        state = None
        reset_animation_state()
        set_current_function_name("Initializing...")

    # Select animation function based on mode
    if mode == 'timemode':
        if is_daytime():
            state = run_daytime_frame(state)
        else:
            state = run_nighttime_frame(state)
    elif mode == 'force_night':
        state = run_nighttime_frame(state)
    elif mode == 'force_day':
        state = run_daytime_frame(state)
    elif mode == 'force_crazy':
        state = animate_crazy_frame(state)

    # Store mode in state for change detection
    if state is not None:
        state['last_mode'] = mode

    set_animation_state(state)

    # Broadcast function name updates (throttled)
    _broadcast_counter += 1
    current_function_name = get_current_function_name()
    if _broadcast_counter >= BROADCAST_INTERVAL or current_function_name != _last_broadcasted_function_name:
        broadcast_function_name()
        _last_broadcasted_function_name = current_function_name
        _broadcast_counter = 0

    time.sleep(FRAME_DELAY)
