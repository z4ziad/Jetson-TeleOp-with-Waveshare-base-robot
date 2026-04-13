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

 
