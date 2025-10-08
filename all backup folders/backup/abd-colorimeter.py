from ppadb.client import Client as AdbClient

# Connect to ADB server (make sure adb.exe is installed and running)
client = AdbClient(host="127.0.0.1", port=5037)

devices = client.devices()
if len(devices) == 0:
    print("No devices connected")
else:
    device = devices[0]
    print("Connected to", device.serial)

    # Example: run a shell command on the device
    output = device.shell("ls /sdcard/")
    print(output)
