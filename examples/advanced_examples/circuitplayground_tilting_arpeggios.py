"""Tilting Arpeggios

This program plays notes from arpeggios in a circle of fourths. Y-axis tilt chooses the note.
Buttons A and B advance forward and backward through the circle. The switch selects
the type of arpeggio, either dominant seventh or blues.

You can ignore the FrequencyProvider class if you’re just interested in the CPX interface.

See a code walkthrough here: https://www.youtube.com/watch?v=cDhqyT3ZN0g
"""

# pylint: disable=R0903
import array
import time
import adafruit_lis3dh
import board
import busio
import digitalio
import neopixel
import audioio
try:
    import audiocore
except ImportError:
    audiocore = audioio


class CustomizedExpress:
    'An enhanced set of audio features, perhaps to augment those in the current Adafruit library'
    def __init__(self):
        self._pixels = neopixel.NeoPixel(board.NEOPIXEL, 10)
        self._a = digitalio.DigitalInOut(board.BUTTON_A)
        self._a.switch_to_input(pull=digitalio.Pull.DOWN)
        self._b = digitalio.DigitalInOut(board.BUTTON_B)
        self._b.switch_to_input(pull=digitalio.Pull.DOWN)
        self._switch = digitalio.DigitalInOut(board.SLIDE_SWITCH)
        self._switch.switch_to_input(pull=digitalio.Pull.UP)
        self._i2c = busio.I2C(board.ACCELEROMETER_SCL, board.ACCELEROMETER_SDA)
        self._int1 = digitalio.DigitalInOut(board.ACCELEROMETER_INTERRUPT)
        self._lis3dh = adafruit_lis3dh.LIS3DH_I2C(self._i2c, address=0x19, int1=self._int1)
        self._lis3dh.range = adafruit_lis3dh.RANGE_8_G
        self._highest_supported_frequency = 20_000
        self._speaker_enable = digitalio.DigitalInOut(board.SPEAKER_ENABLE)
        self._speaker_enable.switch_to_output(value=False)
        self._speaker_enable.value = False
        self._volume = 1.0
        self._audio_out = audioio.AudioOut(board.SPEAKER)
        self._generators = (
            (CustomizedExpress._square_waveform, 2),
        )
        self._waveform_index = 0
        self._create_waveform()

    @property
    def pixels(self):
        return self._pixels

    @property
    def button_a(self):
        return self._a.value

    @property
    def button_b(self):
        return self._b.value

    @property
    def switch(self):
        return self._switch.value

    @property
    def acceleration(self):
        return self._lis3dh.acceleration

    def _create_waveform(self):
        generator, length = self._generators[self._waveform_index]
        self._audiocore_raw_sample = audiocore.RawSample(array.array("H", generator(length, self._volume)))

    @staticmethod
    def _square_waveform(length, amplitude=1.0):
        assert length == 2
        loudest_audible_amplitude = 0.5
        max_amplitude = 2 ** 16 - 1
        return 0, int(loudest_audible_amplitude * amplitude * max_amplitude)

    def set_volume(self, volume):
        self._volume = volume
        self._create_waveform()

    def start_tone(self, frequency):
        if frequency <= self._highest_supported_frequency and self._volume > 0:
            self._audiocore_raw_sample.sample_rate = int(self._generators[self._waveform_index][1] * frequency)
            self._speaker_enable.value = False
            self._audio_out.play(self._audiocore_raw_sample, loop=True)
            self._speaker_enable.value = True


HS_OCT = 12                 # Half-steps per octave
HS_4TH = 5                  # Half-steps in a fourth
ARPEGGIOS = (
    (0, 4, 7, 10),          # Dominant seventh
    (0, 3, 5, 6, 7, 10))    # Blues
C1_FREQ = 32.70319566257483
STARTING_NOTE = C1_FREQ * 2
NUM_OCTAVES = 4
MIN_NOTE_PLAY_SECONDS = 0.2
BUTTON_REPEAT_AFTER_SECONDS = 0.25


class TiltingArpeggios:
    def __init__(self):
        cpx.pixels.brightness = 0.2
        self.circle_pos = 0
        self.key_offset = 0
        TiltingArpeggios.update_pixel(self.circle_pos)
        self.last_freq = None
        self.next_freq_change_allowed_at = time.monotonic()
        self.next_press_allowed_at = time.monotonic()
        self.buttons_on = (cpx.button_a, cpx.button_b)
        num_octaves_to_pre_compute = NUM_OCTAVES + 2
        self.arpeg_note_indexes = TiltingArpeggios.create_arpeggios(num_octaves_to_pre_compute)

    def run(self):
        while True:
            self.process_button_presses()
            if time.monotonic() >= self.next_freq_change_allowed_at:
                self.next_freq_change_allowed_at = time.monotonic() + MIN_NOTE_PLAY_SECONDS
                self.change_tone_if_needed()

    def pressed(self, index):
        """Return whether the specified button (0=A, 1=B) was pressed, limiting the repeat rate"""
        pressed = cpx.button_b if index else cpx.button_a
        if pressed:
            now = time.monotonic()
            if now >= self.next_press_allowed_at:
                self.next_press_allowed_at = now + BUTTON_REPEAT_AFTER_SECONDS
                return True
        return False

    @staticmethod
    def update_pixel(circle_pos):
        """Manage the display on the NeoPixels of the current circle position"""
        cpx.pixels.fill((0, 0, 0))
        # Light the pixels clockwise from “1 o’clock” with the USB connector on the bottom
        pixel_index = (4 - circle_pos) % 10
        # Use a different color after all ten LEDs used
        color = (0, 255, 0) if circle_pos <= 9 else (255, 255, 0)
        cpx.pixels[pixel_index] = color

    @staticmethod
    def tilt():
        """Normalize the Y-Axis Tilt"""
        standard_gravity = 9.81  # Acceleration (m/s²) due to gravity at the earth’s surface
        constrained_accel = min(max(0.0, -cpx.acceleration[1]), standard_gravity)
        return constrained_accel / standard_gravity

    def process_button_presses(self):
        """For each of the buttons A and B, if pushed, advance forward or backward"""
        for button_index, direction in enumerate((1, -1)):
            if self.pressed(button_index):
                self.advance(direction)
                TiltingArpeggios.update_pixel(self.circle_pos)

    def change_tone_if_needed(self):
        """Find the frequency for the current arpeggio and tilt, and restart the tone if changed"""
        arpeggio_index = 0 if cpx.switch else 1
        freq = self.freq(TiltingArpeggios.tilt(), arpeggio_index)
        if freq != self.last_freq:
            self.last_freq = freq
            cpx.start_tone(freq)

    @staticmethod
    def calc_freq(i):
        return STARTING_NOTE * 2 ** (i / HS_OCT)

    @staticmethod
    def create_arpeggios(num_octaves):
        """Create a list of arpeggios, where each one is a list of chromatic scale note indexes"""
        return [TiltingArpeggios.create_arpeggio(arpeggio, num_octaves) for arpeggio in ARPEGGIOS]

    @staticmethod
    def create_arpeggio(arpeggio, num_octaves):
        return [octave * HS_OCT + note for octave in range(num_octaves) for note in arpeggio]

    def advance(self, amount):
        """Advance forward or backward through the circle of fourths"""
        self.circle_pos = (self.circle_pos + amount) % HS_OCT
        self.key_offset = self.circle_pos * HS_4TH % HS_OCT

    def freq(self, normalized_position, selected_arpeg):
        """Return the frequency for the note at the specified position in the specified arpeggio"""
        selected_arpeg_note_indexes = self.arpeg_note_indexes[selected_arpeg]
        num_notes_in_selected_arpeg = len(ARPEGGIOS[selected_arpeg])
        num_arpeg_notes_in_range = num_notes_in_selected_arpeg * NUM_OCTAVES + 1
        arpeg_index = int(normalized_position * num_arpeg_notes_in_range)
        note_index = self.key_offset + selected_arpeg_note_indexes[arpeg_index]
        return TiltingArpeggios.calc_freq(note_index)

cpx = CustomizedExpress()
cpx.set_volume(1.0)
TiltingArpeggios().run()
