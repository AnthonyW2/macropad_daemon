#!/usr/bin/env python3

import hid

# Framework Laptop 16 RGB Macropad
macropad_vid = 0x32ac
macropad_pid = 0x0013

# Default QMK usage page identifiers
usage_page    = 0xFF60
usage_id      = 0x61

# Equal to QMK's RAW_EPSIZE
report_length = 32

# Custom command namespace
custom_hid_prefix = 0xFF


def get_raw_hid_interface(vid, pid, usage_page = 0xFF60, usage_id = 0x61):
    """
    Open a connection with the RAW HID interface of a QMK keyboard.
    
    :param vid: USB vendor ID of the keyboard.
    
    :param vid: USB product ID of the keyboard.
    
    :param usage_page: The usage page of the Raw HID interface
    
    :param usage_id: The usage ID of the Raw HID interface
    
    :returns: RAW HID handle for the keyboard.
    """
    
    device_interfaces = hid.enumerate(vid, pid)
    raw_hid_interfaces = [i for i in device_interfaces if i['usage_page'] == usage_page and i['usage'] == usage_id]
    
    if len(raw_hid_interfaces) == 0:
        return None
    
    interface = hid.Device(path=raw_hid_interfaces[0]['path'])
    
    print(f"Manufacturer: {interface.manufacturer}")
    print(f"Product: {interface.product}")
    
    return interface

def send_raw_report(interface, data):
    """
    Send a RAW HID report over the given interface.
    
    :param interface: RAW HID handle for the keyboard.
    
    :param data: Raw data to send.
    """
    request_data = [0x00] * (report_length + 1) # First byte is Report ID
    request_data[1:len(data) + 1] = data
    request_report = bytes(request_data)
    
    print("Request:")
    print(request_report)
    
    try:
        interface.write(request_report)
        
        response_report = interface.read(report_length, timeout=1000)
        
        print("Response:")
        print(response_report)
    except:
        print("Failed to send report")



if __name__ == '__main__':
    macropad_interface = get_raw_hid_interface(macropad_vid, macropad_pid)
    
    if macropad_interface is None:
        print("No device found")
        sys.exit(1)
    
    # Send a ping
    send_raw_report(macropad_interface, [
        custom_hid_prefix,
        0x00
    ])
    
    macropad_interface.close()

