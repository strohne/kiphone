#
# Test handset lifting
#


import time

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)

from src.rotary import rotary

active = False
while True:

    if active != rotary.is_active:
        active = rotary.is_active
        print(f"Rotary switched to {active}")

    if rotary.is_dialing:
        rotary.read()

    time.sleep(0.1)