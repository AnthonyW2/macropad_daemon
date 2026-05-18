#!/usr/bin/env python3

import hid
from enum import Enum

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

# Amount of time to wait for each read to complete
read_timeout = 1000

"""
Define the codes for the custom RAW HID commands (identical to the custom_hid_commands enum in firmware)
"""
# Send/receive a ping
hid_cmd_ping       = 0x00
# Acknowledge a ping
hid_cmd_ack        = 0x01

# Send/receive new layer
hid_cmd_set_layer  = 0x02 # [layer]

# Receive a new RGB value for a key
hid_cmd_set_rgb    = 0x03 # [key id, r, g, b]
# Receive a new overall brightness level
hid_cmd_set_bright = 0x04 # [brightness divisor]
# RGB matrix enable/disable & set mode
hid_cmd_rgb_matrix = 0x05 # [new state, new mode]

# Send a key downpress event
hid_cmd_key_down   = 0x06 # [key id]
# Send a key release event
hid_cmd_key_up     = 0x07 # [key id]

# Ask the daemon for host system status
hid_cmd_status_req = 0x08
# Receive host system status response
hid_cmd_status_res = 0x09 # [mem, cpu, gpu, gui, crashes, kernel]
""" End custom_hid_commands """


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

def send_command(interface, command_id, data):
    """
    Send a RAW HID command over the given interface.
    
    :param interface: RAW HID handle for the keyboard.
    
    :param command_id: Identifier of the command.
    
    :param data: Raw data to send (should be of length report_length-2).
    """
    
    # Ensure the length of the data is correct
    assert len(data) <= report_length - 2
    
    # Create the report contents
    # First byte is Report ID
    request_data = [0x00] * (report_length + 1)
    # Use our custom command prefix
    request_data[1] = custom_hid_prefix
    # Insert the command ID
    request_data[2] = command_id
    # Add any extra data that the command sends
    request_data[3:len(data) + 3] = data
    
    try:
        interface.write(bytes(request_data))
    except:
        print("ERROR: Failed to send report with command ID "+str(command_id))

def read_interface(interface, timeout):
    """
    Read a message from the keyboard, if there is one.
    
    :param interface: RAW HID handle for the keyboard.
    
    :param timeout: Amount of time (in milliseconds) to wait for a message.
    """
    
    report_data = interface.read(report_length, timeout=timeout)
    
    if len(report_data) > 0:
        handle_custom_hid(report_data)

def handle_custom_hid(data):
    """
    Handle a RAW HID message from the macropad.
    
    :param data: RAW HID report, with length report_length.
    """
    
    if len(data) != report_length:
        print("WARNING: Message length ("+len(data)+") not equal to expected report length, skipping.")
        return
    
    namespace = data[0]
    if namespace != custom_hid_prefix:
        print("WARNING: Intercepted a report which was not meant for us:", data)
    
    command_id = data[1]
    command_data = data[2:]
    
    if command_id == hid_cmd_ping:
        # Ping received, acknowledge it
        send_command(macropad_interface, hid_cmd_ack, [])
        print("Ping received")
        
    elif command_id == hid_cmd_ack:
        # Ping acknowledged, macropad must be available
        print("Ping acknowledged")
        
    else:
        # Not a known command
        print("WARNING: Unknown command with ID "+str(command_id))

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
    send_command(macropad_interface, hid_cmd_ping, [])
    
    while True:
        read_interface(macropad_interface, read_timeout)
    
    macropad_interface.close()

