#
# Create rotary singleton
#

import time
from typing import Callable, Optional
import RPi.GPIO as GPIO


class RotaryWheel:
    """
    Handles the rotary-dial pulse decoder.

    Counts falling-edge GPIO pulses produced by the rotary wheel and converts
    them to a dialled digit (0–9).  An optional *on_first_pulse* callback is
    called once when the first pulse is detected (e.g. to stop a dial tone).
    """

    def __init__(
        self,
        pin_pulse: int = 26,
        pin_detect: int = 16,
        pulse_separation: int = 50,
        pulse_timeout: float = 1.5,
    ):
        """
        :param pin_pulse: BCM GPIO pin connected to the rotary-dial pulse output.
        :param pin_detect: BCM GPIO pin connected to the switch that is closed when dialing is started.
        :param pulse_separation: Minimum gap in milliseconds between two valid pulses.
        :param pulse_timeout: Gap in seconds after a pulse that ends the sequence.
        """
        self.pin_pulse = pin_pulse
        self.pin_detect = pin_detect
        self.pulse_separation = pulse_separation
        self.pulse_timeout = pulse_timeout

        self.stop()
        self.setup()

    def setup(self) -> None:
        """Configure GPIO pins and register the pulse callback once."""
        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        GPIO.setup(self.pin_detect, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Full teardown of the pulse pin before registering edge detection.
        # remove_event_detect alone is not enough on all kernel versions –
        # cleanup() unexports the sysfs file so the next add_event_detect
        # gets a clean file descriptor.
        try:
            GPIO.remove_event_detect(self.pin_pulse)
        except Exception:
            pass
        try:
            GPIO.cleanup([self.pin_pulse])
        except Exception:
            pass

        # wait for the kernel to release the sysfs edge file
        time.sleep(0.1)

        # Re-configure after cleanup (cleanup resets the pin direction)
        GPIO.setup(self.pin_pulse, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(
            self.pin_pulse,
            GPIO.FALLING,
            callback=self._pulse_callback,
            bouncetime=self.pulse_separation,  # ms, required on newer kernels
        )

    def _pulse_callback(self, channel: int) -> None:
        """Increment the pulse counter on each valid falling edge."""
        now = time.time()
        gap = now - self._last_pulse_time
        self._last_pulse_time = now

        if gap > self.pulse_timeout:
            self._pulse_count = 0
        else:
            self._pulse_count += 1

        self.is_dialing = True
        print(f"Pulse {self._pulse_count} detected")

    @property
    def is_active(self) -> bool:
        """Return True if dialing is in progress."""
        return (GPIO.input(self.pin_detect) == GPIO.LOW) or self.is_dialing

    def stop(self):
        self.number: int = 0
        self.is_dialing : bool = False

        self._pulse_count: int = 0
        self._last_pulse_time: float = 0.0

    def read(self) -> Optional[int]:
        """
        Block until a complete digit has been dialled and return it.

        Resets the pulse counter, then blocks until *timeout* seconds of
        silence follow the last pulse. The GPIO callback keeps firing in
        the background.

        :param timeout: Seconds of silence after the last pulse before returning.
        :return: Dialled digit 0–9, or None if no pulses were detected.
        """
        print("Dialing started.")

        while True:
            gap = time.time() - self._last_pulse_time
            if (self._pulse_count > 0) and (gap > self.pulse_timeout):
                break
            time.sleep(0.005)


        if (self._pulse_count < 1) or (self._pulse_count > 10):
            self.number = None
            print("No valid digit detected.")
        else:
            self.number = 0 if self._pulse_count > 9 else self._pulse_count
            print(f"Dialled digit: {self.number}.")

        self.is_dialing = False
        return self.number


# Module-level singleton
rotary = RotaryWheel()
