# Smart CNC Automated Pen Plotter
This project presents a fully automated system that converts a user-selected image into CNC-compatible G-code for a pen plotter machine. The system integrates AI background removal, image processing, vector conversion, and toolpath generation into a single workflow.
---

# Project Overview
The goal of this project is to simplify the process of converting images into CNC pen plotter drawings.

Traditional workflows require multiple tools and manual processing steps. This system automates the entire pipeline from image selection to final G-code generation using a graphical interface and Python-based backend processing.
---

## Features 
- Fully automated image-to-Gcode pipeline
- Dual drawing modes
   1.Outline Mode
   2.Shading / Hatch Mode
- AI background removal
- Automatic raster to vector
- CNC machine scaling
- Automatic G-code generation
- Compatible with LaserGRBL and other G-code senders
---

## System Workflow

User Image + Mode Selection
              ↓
      AI Background Removal
              ↓
       White Background
              ↓
        Mode Decision
        /            \
   Outline         Shading
        \            /
   Raster to Vector (SVG)
              ↓
        SVG Cleanup
              ↓
      G-Code Generation
              ↓
        G-Code Sender
              ↓
     CNC Pen Plot Drawing
 ---
 
 ## Hardware Used
 - CNC Pen Plotter Frame
 - Stepper Motors (X–Y Axis)
 - Servo Motor (Pen Up / Down Control)
 - Arduino Uno
 - CNC Shield
 - Stepper Motor Drivers
 - Power Supply Unit
