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

# Store the index of the key at each physical position
key_indices_2d_map = (
    (5,  2, 22, 17),
    (4,  0, 20, 18),
    (7,  1, 21, 16),
    (6,  3, 23, 19),
    (9, 11, 15, 13),
    (8, 10, 14, 12),
)
# Store the physical position of each key by index
key_coordinates = (
    ( 1, 1 ),
    ( 1, 2 ),
    ( 1, 0 ),
    ( 1, 3 ),
    ( 0, 1 ),
    ( 0, 0 ),
    ( 0, 3 ),
    ( 0, 2 ),
    ( 0, 5 ),
    ( 0, 4 ),
    ( 1, 5 ),
    ( 1, 4 ),
    ( 3, 5 ),
    ( 3, 4 ),
    ( 2, 5 ),
    ( 2, 4 ),
    ( 3, 2 ),
    ( 3, 0 ),
    ( 3, 1 ),
    ( 3, 3 ),
    ( 2, 1 ),
    ( 2, 2 ),
    ( 2, 0 ),
    ( 2, 3 ),
)



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

def coords_to_key(x, y):
    """
    Convert Macropad key coordinates to LED index
    
    :param x: Column of the key (left is 0).
    :param y: Row of the key (top is 0).
    """
    
    assert x >= 0 and x < 4 and y >=0 and y < 6
    
    return key_indices_2d_map[y][x]

def key_to_coords(key):
    """
    Convert Macropad key index to physical coordinates
    
    :param key: Index of the key
    """
    
    assert key >= 0 and key < 24
    
    return key_coordinates[key]



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

