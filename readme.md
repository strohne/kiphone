# KI Phone

Based on https://www.heise.de/select/make/2026/2/2604114391585400402

# Wiring

- Rotary dial pulse: GPIO26 (pin 37)
- Rotary dial detection: GPIO16 (pin 36)
- Hook switch: GPIO5 (pin 29)

# Install dependencies

Log in to Rasperry PI terminal, then install dependencies:

```
sudo apt-get update
sudo apt install swig
sudo apt install python3-rpi-lgpio
sudo apt install liblgpio-dev
sudo apt install portaudio19-dev python3-pyaudio
```

Create a virtual environment and activate it.
On Pi pip is only allowed in a virtual environment.

```
source venv/bin/activate

pip install numpy
pip install pyaudio

pip install openai sounddevice
pip install aiortc
pip install websocket-client
pip install PySocks
```

# Configuration

Copy config/config.default.py to config/config.py and set your OpenAI API key.
Adjust roles.py and callers.py as needed.

# Autostart

Make the script executable:
```
chmod +x /home/pi/Desktop/KI-Telefon/main.py 
```

Open Nano
```
sudo nano /etc/xdg/autostart/kiphone.desktop
```

Enter into nano editor:

```
[Desktop Entry]
Type=Application
Name=kiphone
Exec=/home/devel/.virtualenvs/kiphone/bin/python /home/devel/Code/kiphone/main.py
```
Note: Adjust the path to your Python executable and the main.py script accordingly.
In the example above, it assumes you have a virtual environment located at /home/devel/.virtualenvs/kiphone 
that has been set up with PyCharm.

Save with Ctrl-O, then exit with Ctrl-X

After reboot, check if it is running:

```
ps aux | grep kiphone
```

Kill process if it is running:

```
sudo killall python
```

# Bluetooth headset problems

Check whether headset is in HSP/HFP mode which supports mic:
```
arecord -l
```

If not listed, use pavucontrol to switch mode to HSP/HFP:
```
sudo apt install pulseaudio pulseaudio-module-bluetooth pavucontrol
pavucontrol
```

Switch mode in Configuration tab.
Then restart audio:

```
pulseaudio -k
pulseaudio --start
```

Test recording.
```
arecord -D pulse -f cd test.wav
```

Press Ctrl+C to stop, then play test.wav.

# Create hotspot

sudo nmcli device wifi hotspot ssid <hotspot name> password <hotspot password> ifname wlan0