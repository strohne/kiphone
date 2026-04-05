#
# Main script
#

import time

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)

#from src.bell import bell
from src.handset import handset
from src.tones import tones
from src.rotary import rotary
from src.conversation import conversation

if __name__ == "__main__":
    print("Phone started.")

    while True:
        # ── Hang-up state: stop any activities ──
        if not handset.is_lifted:
            tones.stop()
            conversation.stop()
            rotary.stop()

        # ── Dialing state: wait for number ──
        elif rotary.is_dialing:
            conversation.stop()
            tones.stop()

            tones.beep()
            rotary.read()
            tones.stop()

        # ── Start or continue conversation ──
        else:
            if not conversation.is_running:
                tones.ring()
            elif conversation.is_ready:
                tones.stop()

            conversation.run(rotary.number)

        time.sleep(0.05)
