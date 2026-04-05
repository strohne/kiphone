#
# Create bell singleton
#

import RPi.GPIO as GPIO
import time

from handset import handset

class Bell:
    """
    Handles the telephone bell motor via an H-bridge driver.

    Drives IN1/IN2/ENA GPIO pins to simulate the 25 Hz alternating current
    needed to strike the bell. Rings in discrete strokes and stops as soon
    as the handset is lifted.
    """

    def __init__(
        self,
        in1: int = 17,
        in2: int = 27,
        ena: int = 22,
        freq: float = 25,
        slag_time: float = 1.5,
        pause_between: float = 1.5,
    ):
        """
        :param in1: BCM GPIO pin for H-bridge IN1.
        :param in2: BCM GPIO pin for H-bridge IN2.
        :param ena: BCM GPIO pin for H-bridge enable.
        :param freq: Alternating frequency in Hz (default 25 Hz).
        :param slag_time: Duration of a single ring stroke in seconds.
        :param pause_between: Pause between strokes in seconds.
        """
        self.in1 = in1
        self.in2 = in2
        self.ena = ena
        self.freq = freq
        self.slag_time = slag_time
        self.pause_between = pause_between

        self.setup()

    def setup(self) -> None:
        """Configure all H-bridge GPIO pins as outputs and enable the driver."""

        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        GPIO.setup(self.in1, GPIO.OUT)
        GPIO.setup(self.in2, GPIO.OUT)
        GPIO.setup(self.ena, GPIO.OUT)

        GPIO.output(self.ena, GPIO.HIGH)

    def _bipolar_wave(self, duration_s: float) -> bool:
        """
        Drive a bipolar (alternating) waveform for the given duration.

        :param duration_s: How long to run the wave in seconds.
        :return: True if the handset was lifted during the stroke, else False.
        """
        period = 1.0 / self.freq
        half = period / 2.0
        end = time.time() + duration_s
        while time.time() < end:
            if handset.is_lifted:
                return True
            GPIO.output(self.in1, True)
            GPIO.output(self.in2, False)
            time.sleep(half)
            GPIO.output(self.in1, False)
            GPIO.output(self.in2, True)
            time.sleep(half)
        GPIO.output(self.in1, False)
        GPIO.output(self.in2, False)
        return False

    def ring_until_answer(self, max_rings: int = 5) -> bool:
        """
        Ring up to *max_rings* times and stop as soon as the handset is lifted.

        :param max_rings: Maximum number of ring strokes before giving up.
        :return: True if the handset was lifted, False if nobody answered.
        """
        try:
            for _ in range(max_rings):
                if self._bipolar_wave(self.slag_time):
                    return True
                time.sleep(self.pause_between)
                if handset.is_lifted:
                    return True
            return False
        finally:
            GPIO.output(self.ena, False)
            GPIO.output(self.in1, False)
            GPIO.output(self.in2, False)

# Module-level singleton
bell = Bell()