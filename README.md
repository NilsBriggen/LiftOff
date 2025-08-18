# LiftOff - KDrive File Upload Utility

![LiftOff Logo](logo.jpeg)

LiftOff is a Python utility designed to simplify the upload of files to KDrive (a cloud storage service) from your local machine with automatic timestamped organization.

## Features
- Auto-creates daily timestamped directories for uploads
- Handles both individual files and directories
- Requires minimal configuration (token-based authentication)
- Generates clean directory structure for drone footage
- Error reporting for failed uploads

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


## Configuration

Create a `token.pw` file in your project directory with these credentials (format matters!):
```plain text
Token: <your_token_here>
Drive_id: <your_drive_id_here>
```

**Important**: 
- `Drive_id` must be a valid integer (no quotes)
- This file is **not** committed to version control

## Usage

1. Place your files in the upload directory (e.g., `place/holder`)
2. Run the upload script:
```shell script
python main.py
```


**Example workflow**:
```shell script
mkdir place/holder
touch place/holder/test.txt
python main.py
```


This will upload `test.txt` to KDrive in the directory:
`/Drone Footage/20250818` (current date formatted as YYYYMMDD)

## How It Works
1. Reads token credentials from `token.pw`
2. Creates a timestamped directory (today's date)
3. Uploads files/directories to KDrive
4. Reports success/failure for each file

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Token and Drive_id are required` | Check `token.pw` format and permissions |
| `Drive_id is not a number` | Verify `Drive_id` is integer (no quotes) |
| Upload fails for directories | Ensure directory contains valid files |
| Missing `kdrive_client` | Run `pip install kdrive_client` |

## Notes
- **Security**: Never commit `token.pw` to version control (use `.gitignore`)
- **Path**: Base upload path is `/Drone Footage/` (customizable in code)
- **Error Handling**: Script prints detailed error messages for failed uploads

> **Important**: This tool assumes your KDrive client is configured with the correct permissions. Contact your KDrive administrator if you encounter authorization issues.

---

*This project uses Python 3.13.2 with virtualenv for isolation. No additional dependencies beyond [requests](https://pypi.org/project/requests/) and [kdrive_client](https://pypi.org/project/kdrive_client/) are required.*
