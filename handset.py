#
# Create handset singleton
#

import RPi.GPIO as GPIO

class Handset:
    """
    Handles the handset of the telephone.

    Monitors the hook-switch GPIO pin to determine whether the handset
    is lifted (off-hook) or placed down (on-hook), and provides blocking
    helpers to wait for either state.
    """

    def __init__(self, pin: int = 5):
        """
        :param pin: BCM GPIO pin number connected to the hook-switch.
        """
        self.pin = pin
        self._setup_done = False
        self.setup()

    def setup(self, reset = True):
        """Configure the GPIO pin as input with pull-up resistor."""

        if reset:
            self._setup_done = False

        if self._setup_done:
            return

        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self._setup_done = True

    @property
    def is_lifted(self) -> bool:
        """Return True if the handset is currently lifted (off-hook)."""
        return GPIO.input(self.pin) == GPIO.LOW


# Singleton
handset = Handset()
