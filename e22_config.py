#!/usr/bin/env python3
"""
Configure an EBYTE E22-900T22U (LoRa, USB) module over its virtual serial port.

Requires: pip install pyserial

IMPORTANT: put the module in CONFIGURATION MODE first. Hold the button for more
than 1.5 s and release: the LED turns steady RED. Configuration always uses
9600 baud, 8N1, whatever baud rate the module is set to for normal operation.
When finished, long-press the button again to return to transmission mode
(steady GREEN).

Examples:
  python e22_config.py -p COM5 read
  python e22_config.py -p /dev/ttyACM0 set --channel 20 --air-rate 9.6k --power 22
  python e22_config.py -p COM5 set --address 0x1234 --netid 5 --key 4321 --lbt on
  python e22_config.py -p COM5 reset
"""
import argparse
import sys
import time

import serial  # pyserial

CONFIG_BAUD = 9600

# E22-900T22U lookup tables (from the spec, register 03H / 04H / 05H / 06H)
BAUDS = {1200: 0, 2400: 1, 4800: 2, 9600: 3, 19200: 4, 38400: 5, 57600: 6, 115200: 7}
PARITY = {"8N1": 0, "8O1": 1, "8E1": 2}
# Air rate: 000/001/010 are all 2.4k; default 010
AIR_RATES = {"2.4k": 2, "4.8k": 3, "9.6k": 4, "19.2k": 5, "38.4k": 6, "62.5k": 7}
PACKETS = {240: 0, 128: 1, 64: 2, 32: 3}
POWERS = {22: 0, 17: 1, 13: 2, 10: 3}

BASE_FREQ_MHZ = 850.125  # E22-900T22U: f = 850.125 + CH * 1 MHz
MAX_CHANNEL = 80  # 0-80 (850.125 - 930.125 MHz)

# Factory default from the spec for E22-900T22U
FACTORY_DEFAULT = bytes.fromhex("00 00 00 62 00 12 03 00 00")


def rev(d):
    return {v: k for k, v in d.items()}


def get_bits(value, hi, lo):
    return (value >> lo) & ((1 << (hi - lo + 1)) - 1)


def set_bits(value, hi, lo, new):
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    return (value & ~mask) | ((new << lo) & mask)


class E22:
    def __init__(self, port):
        self.ser = serial.Serial(port, CONFIG_BAUD, bytesize=8, parity="N",
                                 stopbits=1, timeout=1.0)

    def close(self):
        self.ser.close()

    def _txrx(self, frame, expect_len):
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()
        resp = self.ser.read(expect_len)
        if resp[:3] == b"\xFF\xFF\xFF":
            raise RuntimeError("Module replied 'format error' (FF FF FF)")
        if len(resp) != expect_len:
            raise RuntimeError(
                f"No/short response ({len(resp)} of {expect_len} bytes: {resp.hex(' ')}). "
                "Is the module in configuration mode (steady red LED)?")
        return resp

    def read_regs(self, start, length):
        resp = self._txrx(bytes([0xC1, start, length]), 3 + length)
        if resp[:3] != bytes([0xC1, start, length]):
            raise RuntimeError(f"Unexpected response: {resp.hex(' ')}")
        return resp[3:]

    def write_regs(self, start, data, temporary=False):
        cmd = 0xC2 if temporary else 0xC0
        frame = bytes([cmd, start, len(data)]) + bytes(data)
        resp = self._txrx(frame, 3 + len(data))
        if resp != bytes([0xC1]) + frame[1:]:
            raise RuntimeError(f"Write not confirmed: sent {frame.hex(' ')}, got {resp.hex(' ')}")


def describe(regs, pid=None):
    addh, addl, netid, reg0, reg1, reg2, reg3 = regs[:7]
    baud = rev(BAUDS)[get_bits(reg0, 7, 5)]
    parity = {0: "8N1", 1: "8O1", 2: "8E1", 3: "8N1"}[get_bits(reg0, 4, 3)]
    air_code = get_bits(reg0, 2, 0)
    air = {0: "2.4k", 1: "2.4k", 2: "2.4k"}.get(air_code) or rev(AIR_RATES)[air_code]
    packet = rev(PACKETS)[get_bits(reg1, 7, 6)]
    power = rev(POWERS)[get_bits(reg1, 1, 0)]
    onoff = lambda b: "on" if b else "off"
    print(f"  Raw registers 00-06  : {regs[:7].hex(' ')}")
    if pid:
        print(f"  Product info (80-86) : {pid.hex(' ')}")
    print(f"  Address              : 0x{addh:02X}{addl:02X} ({addh << 8 | addl})")
    print(f"  Network ID           : {netid}")
    print(f"  UART baud / format   : {baud} / {parity}")
    print(f"  Air rate             : {air} bps")
    print(f"  Packet size          : {packet} bytes")
    print(f"  TX power             : {power} dBm")
    print(f"  Channel              : {reg2} -> {BASE_FREQ_MHZ + reg2:.3f} MHz")
    print(f"  Ambient RSSI cmds    : {onoff(reg1 & 0x20)}")
    print(f"  Software mode switch : {onoff(reg1 & 0x04)}")
    print(f"  RSSI byte on RX      : {onoff(reg3 & 0x80)}")
    print(f"  Transmission method  : {'fixed-point' if reg3 & 0x40 else 'transparent'}")
    print(f"  Relay                : {onoff(reg3 & 0x20)}")
    print(f"  LBT                  : {onoff(reg3 & 0x10)}")


def cmd_read(dev, args):
    regs = dev.read_regs(0x00, 7)
    try:
        pid = dev.read_regs(0x80, 7)
    except RuntimeError:
        pid = None
    describe(regs, pid)


def cmd_set(dev, args):
    regs = bytearray(dev.read_regs(0x00, 7))  # read-modify-write keeps reserved bits
    if args.address is not None:
        regs[0], regs[1] = (args.address >> 8) & 0xFF, args.address & 0xFF
    if args.netid is not None:
        regs[2] = args.netid
    if args.baud is not None:
        regs[3] = set_bits(regs[3], 7, 5, BAUDS[args.baud])
    if args.parity is not None:
        regs[3] = set_bits(regs[3], 4, 3, PARITY[args.parity])
    if args.air_rate is not None:
        regs[3] = set_bits(regs[3], 2, 0, AIR_RATES[args.air_rate])
    if args.packet is not None:
        regs[4] = set_bits(regs[4], 7, 6, PACKETS[args.packet])
    if args.rssi_noise is not None:
        regs[4] = set_bits(regs[4], 5, 5, args.rssi_noise == "on")
    if args.soft_mode is not None:
        regs[4] = set_bits(regs[4], 2, 2, args.soft_mode == "on")
    if args.power is not None:
        regs[4] = set_bits(regs[4], 1, 0, POWERS[args.power])
    if args.channel is not None:
        regs[5] = args.channel
    if args.rssi_byte is not None:
        regs[6] = set_bits(regs[6], 7, 7, args.rssi_byte == "on")
    if args.fixed is not None:
        regs[6] = set_bits(regs[6], 6, 6, args.fixed == "on")
    if args.relay is not None:
        regs[6] = set_bits(regs[6], 5, 5, args.relay == "on")
    if args.lbt is not None:
        regs[6] = set_bits(regs[6], 4, 4, args.lbt == "on")

    dev.write_regs(0x00, regs, temporary=args.temporary)
    if args.key is not None:  # write-only registers 07H/08H
        dev.write_regs(0x07, bytes([(args.key >> 8) & 0xFF, args.key & 0xFF]),
                       temporary=args.temporary)
        print(f"Key written ({args.key}); it cannot be read back.")
    print("Written" + (" (temporary, lost on power cycle)" if args.temporary else " (saved)") + ":")
    describe(dev.read_regs(0x00, 7))
    if args.baud is not None:
        print(f"\nNote: normal-mode UART baud is now {args.baud}. Configuration mode "
              "still uses 9600. Long-press the button to return to transmission mode.")


def cmd_reset(dev, args):
    dev.write_regs(0x00, FACTORY_DEFAULT)
    print("Factory defaults written:")
    describe(dev.read_regs(0x00, 7))


def int_auto(s):
    return int(s, 0)  # accepts 123 and 0x7B


def main():
    ap = argparse.ArgumentParser(description="Configure EBYTE E22-900T22U over USB serial")
    ap.add_argument("-p", "--port", required=True, help="e.g. COM5 or /dev/ttyACM0")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("read", help="read and show current settings")
    sub.add_parser("reset", help="restore factory defaults (868.125 MHz, ch 18, 2.4k, 22 dBm)")

    s = sub.add_parser("set", help="change settings (only given options are changed)")
    s.add_argument("--address", type=int_auto, help="0-65535 (0xFFFF = broadcast/monitor)")
    s.add_argument("--netid", type=int_auto, help="0-255")
    s.add_argument("--channel", type=int_auto, help=f"0-{MAX_CHANNEL}; freq = 850.125 + CH MHz")
    s.add_argument("--freq", type=float, help="frequency in MHz (850.125-930.125), sets channel")
    s.add_argument("--baud", type=int, choices=sorted(BAUDS), help="UART baud rate (normal mode)")
    s.add_argument("--parity", choices=sorted(PARITY), help="UART format")
    s.add_argument("--air-rate", choices=list(AIR_RATES), help="over-the-air rate")
    s.add_argument("--packet", type=int, choices=sorted(PACKETS), help="packet size in bytes")
    s.add_argument("--power", type=int, choices=sorted(POWERS, reverse=True), help="TX power dBm")
    s.add_argument("--rssi-noise", choices=["on", "off"], help="enable ambient-noise RSSI commands")
    s.add_argument("--rssi-byte", choices=["on", "off"], help="append RSSI byte to received data")
    s.add_argument("--fixed", choices=["on", "off"], help="fixed-point transmission (addr+ch prefix)")
    s.add_argument("--relay", choices=["on", "off"], help="relay function")
    s.add_argument("--lbt", choices=["on", "off"], help="listen-before-talk")
    s.add_argument("--soft-mode", choices=["on", "off"], help="software mode switching")
    s.add_argument("--key", type=int_auto, help="encryption key 0-65535 (write-only)")
    s.add_argument("--temporary", action="store_true", help="use C2 (not saved across power cycle)")

    args = ap.parse_args()

    if args.cmd == "set":
        if args.freq is not None:
            ch = round(args.freq - BASE_FREQ_MHZ)
            if abs((BASE_FREQ_MHZ + ch) - args.freq) > 0.01:
                ap.error("frequency must be 850.125 + N MHz (1 MHz steps)")
            args.channel = ch
        if args.address is not None and not 0 <= args.address <= 0xFFFF:
            ap.error("address out of range")
        if args.netid is not None and not 0 <= args.netid <= 255:
            ap.error("netid out of range")
        if args.channel is not None and not 0 <= args.channel <= MAX_CHANNEL:
            ap.error(f"channel must be 0-{MAX_CHANNEL}")
        if args.key is not None and not 0 <= args.key <= 0xFFFF:
            ap.error("key out of range")

    try:
        dev = E22(args.port)
    except serial.SerialException as e:
        sys.exit(f"Cannot open {args.port}: {e}")
    time.sleep(0.1)
    try:
        {"read": cmd_read, "set": cmd_set, "reset": cmd_reset}[args.cmd](dev, args)
    except RuntimeError as e:
        sys.exit(f"Error: {e}")
    finally:
        dev.close()


if __name__ == "__main__":
    main()
