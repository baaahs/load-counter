# Loadcounter Setup

This file documents the clean Raspberry Pi setup steps used to restore this project after a fresh OS install.

## Assumptions

- Hostname: `raspberry.local`
- User: `jul`
- Project path on Pi: `/home/jul/loadcounter`
- Services:
  - `loadcounter.service`
  - `loadcounter-keyboard.service`

## 1. Copy project files to the Pi

From the local repo:

```bash
scp -r \
  load-counter.py \
  keyboard-listener.py \
  test-ultrasonic.sensors.py \
  loadcounter.service \
  loadcounter-keyboard.service \
  fonts \
  deploy.sh \
  logs.sh \
  README.md \
  jul@raspberry.local:/home/jul/loadcounter-bootstrap
```

Then on the Pi:

```bash
rm -rf /home/jul/loadcounter
mv /home/jul/loadcounter-bootstrap /home/jul/loadcounter
cd /home/jul/loadcounter
```

Important:

- Do **not** copy the local `rgbmatrix/` directory to the Pi.
- That directory is a local emulator and will break the real device setup on the Pi.

## 2. Create the Python environment

On the Pi:

```bash
cd /home/jul/loadcounter
python3 -m venv env
./env/bin/pip install --upgrade pip setuptools wheel
```

## 3. Install required system packages

On the Pi:

```bash
sudo apt-get update
sudo apt-get install -y \
  python3-dev \
  libpython3-dev \
  build-essential \
  pkg-config \
  git \
  cython3 \
  cmake \
  ninja-build
```

## 4. Install Python dependencies

On the Pi:

```bash
cd /home/jul/loadcounter
./env/bin/pip install \
  pyserial \
  evdev \
  adafruit-circuitpython-us100 \
  pillow \
  scikit-build-core \
  cython
```

## 5. Install and enable the systemd services

On the Pi:

```bash
cd /home/jul/loadcounter
sudo cp loadcounter.service /etc/systemd/system/loadcounter.service
sudo cp loadcounter-keyboard.service /etc/systemd/system/loadcounter-keyboard.service
sudo systemctl daemon-reload
sudo systemctl enable loadcounter.service loadcounter-keyboard.service
```

## 6. Prepare persistent state directories

On the Pi:

```bash
sudo install -d -o daemon -g daemon /var/lib/loadcounter
sudo install -d -o jul -g jul /var/tmp/loadcounter
```

## 7. Build the real RGB matrix Python binding

The project does not use a PyPI `rgbmatrix` package on the Pi. It needs the upstream `hzeller/rpi-rgb-led-matrix` binding built from source.

Clone it:

```bash
cd /home/jul
rm -rf rpi-rgb-led-matrix
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
```

Then build/install it into the project venv from the repo root:

```bash
cd /home/jul/rpi-rgb-led-matrix
/home/jul/loadcounter/env/bin/pip install .
```

### Fresh-install workaround used here

On this Pi, the upstream build failed in the Pillow shim for `SetImage()` because:

- the installed Pillow wheel did not provide `Imaging.h`
- the app does not use that Pillow-backed matrix path anyway

Workaround used on the Pi:

```bash
cat > /home/jul/rpi-rgb-led-matrix/bindings/python/rgbmatrix/shims/Imaging.h <<'EOF'
#ifndef LOADCOUNTER_SHIM_IMAGING_H
#define LOADCOUNTER_SHIM_IMAGING_H

typedef struct ImagingMemoryInstance {
    char _padding[64];
    int **image32;
} ImagingMemoryInstance;

#endif
EOF
```

Then install from the repo root without build isolation:

```bash
cd /home/jul/rpi-rgb-led-matrix
CMAKE_BUILD_PARALLEL_LEVEL=1 /home/jul/loadcounter/env/bin/pip install --no-build-isolation .
```

## 8. Low-memory Pi note

On a small-memory Pi, the `rgbmatrix` build may fail during the Cython/CMake step because the process gets killed by OOM.

If that happens, add temporary swap and retry with single-threaded builds:

```bash
sudo fallocate -l 1G /swapfile-loadcounter
sudo chmod 600 /swapfile-loadcounter
sudo mkswap /swapfile-loadcounter
sudo swapon /swapfile-loadcounter

cd /home/jul/rpi-rgb-led-matrix
CMAKE_BUILD_PARALLEL_LEVEL=1 /home/jul/loadcounter/env/bin/pip install --no-build-isolation .

sudo swapoff /swapfile-loadcounter
sudo rm -f /swapfile-loadcounter
```

## 9. Start the services

On the Pi:

```bash
sudo systemctl restart loadcounter.service loadcounter-keyboard.service
sudo systemctl status loadcounter.service loadcounter-keyboard.service --no-pager -l
```

## 10. Validate device availability

Sensors:

```bash
ls -l /dev/ttyUSB*
```

Keyboard input devices:

```bash
ls -l /dev/input/event*
sudo journalctl -u loadcounter-keyboard -n 100 --no-pager
```

Loadcounter logs:

```bash
sudo journalctl -u loadcounter -n 100 --no-pager
```

## Known failure modes

### Local emulator copied to the Pi

Symptom:

- `ImportError: rgbmatrix emulator requires Pillow and Tkinter`

Cause:

- local `rgbmatrix/` emulator directory copied into `/home/jul/loadcounter`

Fix:

- remove `/home/jul/loadcounter/rgbmatrix`
- build/install the real `rpi-rgb-led-matrix` Python binding

### `evdev` fails to install

Symptom:

- build error with `Python.h: No such file or directory`

Fix:

- install `python3-dev`, `libpython3-dev`, `build-essential`

### No sensors found

Symptom:

- `ls /dev/ttyUSB*` shows nothing

Fix:

- reconnect both USB serial sensors
- confirm they enumerate as `/dev/ttyUSB0` and `/dev/ttyUSB1`

### No keyboard found

Symptom:

- keyboard listener repeatedly logs `No keyboard device available for listener`

Fix:

- restart Bluetooth and confirm the controller is available:
  ```bash
  sudo systemctl restart bluetooth
  bluetoothctl list
  ```
- enable BlueZ userspace HID on the Pi:
  ```bash
  sudo cp /etc/bluetooth/input.conf /etc/bluetooth/input.conf.bak
  sudo sed -i 's/^#UserspaceHID=true/UserspaceHID=true/' /etc/bluetooth/input.conf
  sudo systemctl restart bluetooth
  ```
- if the keyboard was paired before the setting change, remove the stale bond:
  ```bash
  bluetoothctl
  remove 3C:A6:F6:ED:9E:BF
  ```
- pair the Apple keyboard again:
  ```bash
  bluetoothctl
  power on
  agent on
  default-agent
  scan on
  pair 3C:A6:F6:ED:9E:BF
  yes
  trust 3C:A6:F6:ED:9E:BF
  connect 3C:A6:F6:ED:9E:BF
  ```
- after pairing succeeds, verify the keyboard shows up as an input device:
  ```bash
  ls -l /dev/input/event*
  cat /proc/bus/input/devices
  ```
- on this Pi the keyboard appeared as `/dev/input/event2` with name `Julien’s Magic Keyboard #3`
- restart the keyboard listener so it rescans and attaches:
  ```bash
  sudo systemctl restart loadcounter-keyboard.service
  sudo journalctl -u loadcounter-keyboard -n 80 --no-pager
  ```
- success looks like:
  - `Using keyboard listener device: /dev/input/event2 (Julien’s Magic Keyboard #3)`
  - kernel log lines mentioning `input: Julien’s Magic Keyboard #3`

## Current restore status

These steps were completed successfully on the fresh Pi:

- project copied to `/home/jul/loadcounter`
- venv created
- Python dependencies installed
- services installed and enabled
- state directories created
- real `rgbmatrix` binding built from upstream source

Current hardware-specific blockers to verify if restore is incomplete:

- real `rgbmatrix` binding must be built successfully from `rpi-rgb-led-matrix`
- sensors must appear as `/dev/ttyUSB0` and `/dev/ttyUSB1`
- Bluetooth keyboard must be paired again
