#
# Test handset lifting
#

import time

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)

from handset import handset
from tones import tones

# Play a tone if the handset is lifted
while True:
    if not handset.is_lifted:
        tones.stop()
    elif handset.is_lifted:
        tones.beep()

    time.sleep(0.1)