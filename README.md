# E22-900T22U configuration script

`e22_config.py` reads and sets the parameters of an EBYTE **E22-900T22U** LoRa USB module (850.125–930.125 MHz) through its virtual serial port.

It follows the command set in the E22-xxxT22U user manual (v1.1): `C1` read, `C0` write (saved), `C2` write (temporary).

## Where to get modules

eByte LoRa USB Module price is around $10 in several online shopping platforms.  

https://s.click.aliexpress.com/e/_c3TWWnE5  
https://link.amazon/B0c1O40l5  
https://amzn.to/4lfsfea  

## Usage for data transfer

In transmission normal mode (just plugging the module without hold any button) the module create a virtual serial port to receive and send raw data. The module works with a USB OTG adaptor in Android devices with https://github.com/mik3y/usb-serial-for-android and in Linux/Windows/Mac with any serial port terminal.
Data are sent in raw, without error corrections or lost packets check. To implement those functions you can use Reticulum Network Stack https://github.com/markqvist/reticulum

## Requirements

- Python 3.8+
- pyserial: `pip install pyserial`

## Before you run it: enter configuration mode

The module only accepts configuration commands in **configuration mode**.

1. Plug the module and hold the button for **more than 1.5 s** and release. The LED turns **steady red**.
2. Run the script.
3. Long-press the button again to go back to transmission mode (steady green).

In configuration mode the serial link is always **9600 baud, 8N1**, whatever baud rate the module is set to for normal operation. The script handles this itself.

Find the port name: `COMx` on Windows (Device Manager), `/dev/ttyACM0` or `/dev/ttyUSB0` on Linux (you may need `sudo usermod -aG dialout $USER`), `/dev/tty.usbmodem*` on macOS.

## Usage

```
python e22_config.py -p <PORT> read
python e22_config.py -p <PORT> set [options]
python e22_config.py -p <PORT> reset
```

Examples:

```
python e22_config.py -p COM5 read
python e22_config.py -p /dev/ttyACM0 set --freq 868.125 --air-rate 9.6k --power 22
python e22_config.py -p COM5 set --address 0x1234 --netid 5 --channel 20 --lbt on --key 4321
python e22_config.py -p COM5 set --channel 30 --temporary
```

### Commands

| Command | What it does |
|---|---|
| `read` | Shows the current settings and the product ID |
| `set` | Changes only the options you pass; all other settings are kept |
| `reset` | Writes the factory defaults (see below) |

### `set` options

| Option | Values | Notes |
|---|---|---|
| `--address` | 0–65535 (or `0x....`) | `0xFFFF` = broadcast / monitor address |
| `--netid` | 0–255 | Must match on both ends |
| `--channel` | 0–80 | Frequency = 850.125 + CH MHz |
| `--freq` | 850.125–930.125 | In MHz, 1 MHz steps; converted to a channel |
| `--baud` | 1200 … 115200 | UART baud in normal mode (default 9600) |
| `--parity` | `8N1`, `8O1`, `8E1` | UART format |
| `--air-rate` | `2.4k` `4.8k` `9.6k` `19.2k` `38.4k` `62.5k` | Must match on both ends. Higher rate means less range |
| `--packet` | 240, 128, 64, 32 | Packet size in bytes |
| `--power` | 22, 17, 13, 10 | TX power in dBm |
| `--rssi-noise` | `on` / `off` | Enables the ambient-noise RSSI read commands |
| `--rssi-byte` | `on` / `off` | Appends an RSSI byte to received data |
| `--fixed` | `on` / `off` | Fixed-point mode: first 3 bytes of each serial message are address high, address low, channel |
| `--relay` | `on` / `off` | Relay function (see the manual's relay section) |
| `--lbt` | `on` / `off` | Listen-before-talk |
| `--soft-mode` | `on` / `off` | Switch modes by serial command instead of the button |
| `--key` | 0–65535 | Encryption key. Write-only: it cannot be read back |
| `--temporary` | flag | Uses the `C2` command: changes are lost at power-off |

### Factory defaults (`reset`)

868.125 MHz (channel 18), address 0, network ID 0, 9600 8N1, 2.4k air rate, 240-byte packets, 22 dBm, all other features off.

## Troubleshooting

| Message | Likely cause |
|---|---|
| `No/short response` | The module is not in configuration mode (LED must be steady red), or the wrong port is selected |
| `Cannot open <port>` | Port in use by another program, wrong name, or missing permissions |
| `format error (FF FF FF)` | The module rejected the command frame |
| `Write not confirmed` | The module's reply did not match the command; retry, and run `read` to check the state |

## Reference

EBYTE E22-230/400/900T22U Product Specification (Chengdu Ebyte Electronic Technology Co., Ltd.), v1.1.

## Contact

Send feedback, questions and suggestions to fossideasdev@gmail.com
