This repo contains a Python script to control the Jetson Orin Nano robot with the Waveshare robot base using a game controller. The game controller is assumed to be like GAME:**PAD** 4 S type with 255 step resolution. The gamepad could also be connected wired or wirelessly to a USB port on the Jetson. 

The script applies the deadzone to avoid jitter in the center joystick position. It also applies a "S" curve to smooth out quick joystick actions, which is necessary to mapping during VSLAM operations.    


             
Only the **left** joystick is used to control movement:       
**Up-Down** -> X-Linear velocity positive forward and negative backward.    
**Left-Right**-> Z-Angular velocity clockwise and counterclockwise. 

## Installing and Running
Install pyserial if you haven't already:
```bash
pip install pyserial
```
Download the script and simply run it:
```bash
python tele_op.py
```
## Controller "Unplugged Error"
It is possible to get an error message saying that `"Controller Unplugged"` or something to that effect when you run `tele_op.py`. This probably means that the controller is configured in Xbox or **XInput** mode and not in gamepad or **DInput mode**. To verify the cause of the problem do the following:
```bash
ls -l /dev/input
```
If you don't see the `js0` file listed, then most likely the controller is in **XInput** mode. Apparently some of the game controllers we received from Waveshare are configured in XInput mode by default instead of DInput mode.

To switch the game controller into DInput mode, do the following:
1. Turn on the controller.
2. Plug the wireless dongle into the Jetson and power it up and wait until it is fully running. You should see one LED lit on the controller at this point. 
3. Press and hold down the HOME button (the center button) for ~7 seconds.
4. Watch the LED — it will change pattern/color to confirm the mode switch. When you see two LEDs flashing, release the the HOME button. The two LEDS should now stay on. It is now in DInput mode.  
5. List the `/dev/input` files again:
    ```bash
    ls -l /dev/input
    ```
    The controller should now appear as a standard `/dev/input/js0` joystick readable by the inputs library.   
6. Try running the `tele_op.py` again. It should work at this time.    

Unfortunately, I can't figure out a way to make the mode change permanent on the controller. So you will have to press the HOME button for ~7 seconds every time you plug the wireless dongle, which may not be the end of the world! 
 
