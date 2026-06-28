import base64
import broadlink
import os
import time

from dotenv import load_dotenv
load_dotenv()

TIMEOUT = 30

device = devices = broadlink.discover(discover_ip_address=os.environ["BROADLINK_IP"], timeout=5)[0]
device.auth()

print("Entering learning mode...")
device.enter_learning()

print("Press a button on the AC remote within 30 seconds")

for _ in range(30):
    time.sleep(1)

    try:
        packet = device.check_data()
        if packet:
            print("Received!")

            print("Raw bytes:", packet.hex())

            print("Base64:")
            print(base64.b64encode(packet).decode())

            break

    except Exception:
        pass
