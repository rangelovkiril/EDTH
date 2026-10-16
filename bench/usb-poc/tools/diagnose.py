#!/usr/bin/env python3
import glob
import json
import os

from serial.tools import list_ports

print("USB serial cameras:")
for p in list_ports.comports():
    if not p.vid:
        continue
    print(
        json.dumps(
            {
                "port": p.device,
                "description": p.description,
                "serial": p.serial_number,
                "read_write": os.access(p.device, os.R_OK | os.W_OK),
            }
        )
    )
print("Stable serial paths:", glob.glob("/dev/serial/by-id/*"))
print("Video devices:", glob.glob("/dev/video*"))
print("ESP32 serial ports need skycam firmware; a USB cable alone does not make them webcams.")
