# LiftOff - A Drone Footage Archiving Utility

![LiftOff Logo](logo.jpeg)

LiftOff is a Python utility designed to simplify the archiving of drone videos (and metadata) from your local machine  to a specified folder with automatic timestamped organization.

## Features
- Auto-creates daily timestamped directories for archiving
- Handles both individual files and directories
- Generates clean directory structure for drone footage
- Error reporting for failed archiving

## Prerequisites
- Python 3.13.2 (or higher)
- `virtualenv` (for project isolation)
- `pip` (for package installation)

## Installation

1. Create a virtual environment:
```shell script
python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or venv\Scripts\activate  # Windows
```


2. Install required packages:
```shell script
pip install requests kdrive_client
```

## Usage

1. Edit the configuration to the SD Card path(e.g., `place/holder`)
2. Run the upload script:
```shell script
python main.py
```
