#!/usr/bin/env python3

import sys
import os
import asyncio
import hid
from enum import Enum

# Framework Laptop 16 RGB Macropad
macropad_vid = 0x32ac
macropad_pid = 0x0013

# Equal to QMK's RAW_EPSIZE
report_length = 32

# Custom command namespace
custom_hid_prefix = 0xFF

# Amount of time to wait for each read to complete
read_timeout = 1000

socket_path = "/run/user/1000/macropad.sock"


"""
Define the codes for the custom RAW HID commands (identical to the custom_hid_commands enum in firmware)
"""
# Send/receive a ping
hid_cmd_ping       = 0x00
# Acknowledge a ping
hid_cmd_ack        = 0x01

# Send/receive new layer
hid_cmd_set_layer  = 0x02 # [layer]

# Send a new RGB value for a key
hid_cmd_set_rgb    = 0x03 # [key id, r, g, b]
# Send a new overall brightness level
hid_cmd_set_bright = 0x04 # [brightness shift]
# RGB matrix enable/disable & set mode
hid_cmd_rgb_matrix = 0x05 # [new state, new mode]

# Receive a key downpress event
hid_cmd_key_down   = 0x06 # [key id]
# Receive a key release event
hid_cmd_key_up     = 0x07 # [key id]

# Receive a request for host system status
hid_cmd_status_req = 0x08
# Send host system status response
hid_cmd_status_res = 0x09 # [mem, cpu, gpu, gui, crashes, kernel]
""" End custom_hid_commands """


"""
Define the terms for the IPC commands
"""
# Set new layer
ipc_cmd_set_layer  = "layer" # [layer: int]

# Set a new RGB value for a key
ipc_cmd_set_rgb    = "rgb" # [key: int, r: int, g: int, b: int]
# Set a new overall brightness level
ipc_cmd_set_bright = "bright" # [brightness shift: int]
# Enable/disable RGB matrix
ipc_cmd_rgb_matrix = "rgb_enable" # [state: on/off]

# Set audio output mute indicator state
ipc_cmd_audio_ind_out = "audio_out" # [state: unmute/mute]
# Set audio input (mic) mute indicator state
ipc_cmd_audio_ind_in = "audio_in" # [state: unmute/mute]
""" End IPC commands """


# The index of the key at each physical position
key_indices_2d_map = (
    (5,  2, 22, 17),
    (4,  0, 20, 18),
    (7,  1, 21, 16),
    (6,  3, 23, 19),
    (9, 11, 15, 13),
    (8, 10, 14, 12),
)
# The physical position of each key by index
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


# Global queue for messages to be sent to the macropad
outgoing_hid_queue = asyncio.Queue()


# True if the macropad has ever been heard from since boot
macropad_hid_initialised = False

# Store the current layer
current_layer = 1

# Current RGB matrix state (0 = off)
rgb_enabled = 1

# Current RGB brightness shift
rgb_brightness_shift = 3



async def main():
    """
    Start the daemon: connect to the macropad, validate two-way communication, and schedule asynchronous tasks.
    """
    # Get RAW HID handle
    global macropad_interface
    macropad_interface = get_raw_hid_interface(macropad_vid, macropad_pid)
    
    # Exit if it isn't found
    if macropad_interface is None:
        print("No device found")
        return
    
    # Exit if the macropad doesn't acknowledge a ping
    if not await blocking_ping(macropad_interface):
        print("Macropad did not return ping")
        return
    
    # Schedule asynchronous RAW HID tasks
    asyncio.create_task(hid_reader(macropad_interface))
    asyncio.create_task(hid_writer(macropad_interface))
    
    # Start the UNIX socket server
    await start_unix_socket()
    
    # Synchronise default states
    await synchronise_states()
    
    # Sleep until killed
    await asyncio.Event().wait()

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

async def blocking_ping(interface):
    """
    Send a ping and wait for the response.
    
    :param interface: RAW HID handle for the keyboard.
    """
    
    # Send a ping
    send_command(macropad_interface, hid_cmd_ping, [])
    
    # Wait for a response
    response_data = interface.read(report_length, timeout=read_timeout)
    
    # Validate that the macropad acknowledged the ping
    if len(response_data) > 0 and (await handle_custom_hid(response_data)) == hid_cmd_ack:
        return True
    
    return False

def send_command(interface, command_id, data):
    """
    Send a RAW HID command over the given interface.
    
    :param interface: RAW HID handle for the keyboard.
    
    :param command_id: Identifier of the command.
    
    :param data: Raw data to send (length should be at most report_length-2).
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

async def hid_reader(interface):
    """
    Listen for messages from the macropad, handling them as they come in.
    
    :param interface: RAW HID handle for the keyboard.
    """
    while True:
        data = await asyncio.to_thread(
            interface.read,
            report_length,
            read_timeout
        )
        
        if len(data) > 0:
            await handle_custom_hid(data)

async def hid_writer(interface):
    """
    Send messages to the macropad, taking them off the outgoing_hid_queue as they come in.
    
    :param interface: RAW HID handle for the keyboard.
    """
    while True:
        command_id, data = await outgoing_hid_queue.get()
        
        send_command(
            macropad_interface,
            command_id,
            data
        )



async def queue_command(command_id, data):
    """
    Add a RAW HID command to the command queue
    
    :param command_id: Identifier of the command.
    
    :param data: Raw data to send (length should be at most report_length-2).
    """
    
    # Ensure the length of the data is correct
    assert len(data) <= report_length - 2
    
    await outgoing_hid_queue.put(
        (command_id, data)
    )

async def handle_custom_hid(data):
    """
    Handle a RAW HID message from the macropad.
    
    :param data: RAW HID report, with length report_length.
    """
    
    # We heard from the macropad, update availability
    macropad_hid_initialised = True
    
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
        await queue_command(hid_cmd_ack, [])
        print("Ping received")
        
    elif command_id == hid_cmd_ack:
        # Ping acknowledged, macropad must be available
        print("Ping acknowledged")
        
    elif command_id == hid_cmd_set_layer:
        # The layer has changed
        current_layer = command_data[0]
        print("Layer changed to "+str(current_layer))
        
    elif command_id == hid_cmd_set_bright:
        # The brightness has changed
        print("Brightness changed to "+str(command_data[0]))
        
    else:
        # Not a known command
        print("WARNING: Unknown command with ID "+str(command_id))
    
    return command_id

async def synchronise_states():
    """
    Synchronise some state information with the macropad.
    """
    
    # Set the layer
    await queue_command(hid_cmd_set_layer, [current_layer])
    
    # Set the brightness of the LEDs
    await queue_command(hid_cmd_set_bright, [rgb_brightness_shift])



async def start_unix_socket():
    """
    Create a UNIX socket to listen on for IPC.
    """
    # Remove old socket if it exists
    if os.path.exists(socket_path):
        os.remove(socket_path)
    
    # Start the server, letting handle_socket_client handle messages
    server = await asyncio.start_unix_server(handle_socket_client, path=socket_path)
    
    asyncio.create_task(server.serve_forever())

async def handle_socket_client(reader, writer):
    """
    Handle incoming messages from the UNIX socket.
    
    :param reader: StreamReader object that provides APIs to read data from the IO stream.
    
    :param writer: StreamWriter object that provides APIs to write data to the IO stream.
    """
    
    while True:
        raw_data = await reader.readline()
        
        if not raw_data:
            break
        
        print("Received IPC message:", raw_data)
        
        response = await handle_ipc_command(raw_data.decode().split(" "))
        
        writer.write(response.encode())
        await writer.drain()
    
    # Close the connection
    writer.close()
    await writer.wait_closed()

async def handle_ipc_command(data):
    """
    Handle an IPC incoming message from the UNIX socket.
    
    :param data: Array of decoded strings making up the message.
    """
    
    command_id = data[0]
    command_data = data[1:]
    
    response = "ACK\n"
    
    if command_id == ipc_cmd_set_layer:
        # Set new layer
        current_layer = int(command_data[0])
        await queue_command(hid_cmd_set_layer, [current_layer])
        
        response = f"Set layer to {command_data[0]}\n"
        
    elif command_id == ipc_cmd_set_rgb:
        # Set a new RGB value for a key
        
        # Decode the command data
        key = int(command_data[0])
        r   = int(command_data[1])
        g   = int(command_data[2])
        b   = int(command_data[3])
        
        # Check bounds
        if key < 0 or key > 23:
            return f"ERROR: Invalid key ID: {str(key)}\n"
        if r < 0 or r > 255 or g < 0 or g > 255 or b < 0 or b > 255:
            return f"ERROR: RGB components must be between 0 and 255\n"
        
        # Send command to macropad
        await queue_command(hid_cmd_set_rgb, [key, r, g, b])
        
        response = f"Changed colour of key {str(key)}\n"
        
    elif command_id == ipc_cmd_set_bright:
        # Set a new overall brightness level
        
        new_shift = int(command_data[0])
        
        # Check bounds
        if new_shift < 0 or new_shift > 7:
            return f"ERROR: Invalid brightness shift: {str(new_shift)}\n"
        
        # Update our tracked value
        rgb_brightness_shift = new_shift
        
        # Send command to macropad
        await queue_command(hid_cmd_set_bright, [rgb_brightness_shift])
        
        response = f"Changed brightness shift to {str(new_shift)}\n"
        
    elif command_id == ipc_cmd_rgb_matrix:
        # Enable/disable RGB matrix
        
        # Check bounds
        if command_data[0].strip() == "on":
            rgb_enabled = 1
            response = f"Enabled RGB matrix\n"
        elif command_data[0].strip() == "off":
            rgb_enabled = 0
            response = f"Disabled RGB matrix\n"
        else:
            return f"ERROR: Invalid RGB matrix state: {command_data[0]}\n"
        
        # Send command to macropad
        await queue_command(hid_cmd_rgb_matrix, [rgb_enabled, 1])
        
    elif command_id == ipc_cmd_audio_ind_out:
        # Set audio output mute indicator state
        
        if command_data[0].strip() == "unmute":
            muted = False
            response = f"Set audio output mute indicator off\n"
        elif command_data[0].strip() == "mute":
            muted = True
            response = f"Set audio output mute indicator on\n"
        else:
            return f"ERROR: Invalid mute state: {command_data[0]}\n"
        
        await set_mute_state("output", muted)
        
    elif command_id == ipc_cmd_audio_ind_in:
        # Set audio input (mic) mute indicator state
        
        if command_data[0].strip() == "unmute":
            muted = False
            response = f"Set audio input mute indicator off\n"
        elif command_data[0].strip() == "mute":
            muted = True
            response = f"Set audio input mute indicator on\n"
        else:
            return f"ERROR: Invalid mute state: {command_data[0]}\n"
        
        await set_mute_state("input", muted)
        
    else:
        response = f"ERROR: Invalid IPC command: {command_id}\n"
    
    return response



async def set_mute_state(device, muted):
    """
    Update a mute indicator LED on the macropad.
    
    :param device: Device identifier - "input" or "output"
    
    :param muted: Whether or not the device is muted
    """
    
    if device == "input":
        key_id = 17
    elif device == "output":
        key_id = 22
    else:
        return
    
    if muted:
        red = 255
    else:
        red = 0
    
    await queue_command(hid_cmd_set_rgb, [key_id, red, 0, 0])

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
    asyncio.run(main())

