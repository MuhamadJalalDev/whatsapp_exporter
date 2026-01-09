# WhatsApp Media Exporter (Date Range)

A desktop application to export WhatsApp media files within a specified date range. Supports both direct USB connection (ADB) and local folder modes.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

## ✨ Features

- **Dual Mode Operation**:
  - **USB/ADB Mode**: Connect your Android phone via USB and export directly
  - **Local Folder Mode**: Use previously copied WhatsApp media folders
- **Date Range Filtering**: Select specific start and end dates (inclusive)
- **Selective Subfolder Export**: Choose which WhatsApp media types to export:
  - WhatsApp Images
  - WhatsApp Video
  - WhatsApp Documents
  - WhatsApp Audio
  - WhatsApp Voice Notes
  - Animated Gifs
- **Smart Organization**: Files maintain their folder structure in the destination
- **Duplicate Handling**: Automatically renames duplicate files (adds `__dup1`, `__dup2`, etc.)
- **Real-time Progress**: Live counters for scanned, exported, and error files
- **Two Export Modes**:
  - **Copy** (recommended): Leaves original files intact
  - **Move** (Local mode only): Moves files from source to destination

## 📋 Prerequisites

### For USB/ADB Mode:
1. **Android Phone** with WhatsApp installed
2. **USB Debugging Enabled** on your phone:
   - Go to Settings → About Phone → Tap "Build Number" 7 times
   - Go to Settings → Developer Options → Enable "USB Debugging"
3. **ADB Drivers** installed on your computer
4. **Authorize USB Debugging** when prompted on your phone

### For Local Folder Mode:
1. A folder containing WhatsApp media (typically from `WhatsApp/Media/`)

### Software Requirements:
- Python 3.8 or higher
- Required Python packages (install via `requirements.txt`)

## 🚀 Installation

1. **Clone or download** this repository
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
3.python whatsapp_media_exporter.py


# Step-by-Step Guide:

1. **Choose Source Type**:
   - **Option 1: USB Device (ADB)**: For direct phone connection
   - **Option 2: Local Folder**: For previously copied media

2. **Configure Source**:
   - **ADB Mode**: Connect phone via USB, then click "Refresh Devices"
   - **Local Mode**: Browse to your WhatsApp media folder

3. **Set Destination**: Choose where to save exported files

4. **Set Date Range**:
   - Format: YYYY-MM-DD (e.g., 2025-09-17 to 2025-12-17)
   - Both dates are inclusive

5. **Select Subfolders**: Check which media types to export

6. **Choose Export Mode**:
   - Copy (recommended for both modes)
   - Move (only available in Local Folder mode)

7. **Click "Start Export"** and monitor progress in the log

## 📁 Folder Structure

### Typical WhatsApp Media Structure:
WhatsApp/
├── Media/
│ ├── WhatsApp Images/
│ ├── WhatsApp Video/
│ ├── WhatsApp Documents/
│ ├── WhatsApp Audio/
│ ├── WhatsApp Voice Notes/
│ └── Animated Gifs/


### Output Structure:
Files maintain their relative paths from the WhatsApp Media root.

## 🛠️ Technical Details

### ADB Implementation:
- Uses Android Debug Bridge (ADB) for direct file access
- Supports multiple device connection
- Handles file timestamp extraction via `stat` command
- Falls back to alternative WhatsApp media paths

### File Operations:
- **Copy Mode**: Uses `shutil.copy2()` to preserve metadata
- **Move Mode**: Uses `shutil.move()` (local only)
- **Timestamp Filtering**: Compares file modification time with selected range
- **Duplicate Resolution**: Appends `__dupN` suffix to conflicting filenames

### Performance Features:
- Multi-threaded UI to prevent freezing
- Progress tracking with estimated file counts
- Cancel support during long operations
- Error resilience with detailed logging

## ⚠️ Limitations & Notes

- **ADB Mode**: Does not support "Move" operation (safety precaution)
- **File Dates**: Uses file modification time, which may differ from WhatsApp's internal dates
- **Large Collections**: First run scans all files to estimate progress
- **Permissions**: May need elevated privileges for certain system paths
- **Network Drives**: Performance may vary with network locations

## 🔧 Troubleshooting

### Common ADB Issues:

1. **"No devices detected"**:
   - Check USB cable connection
   - Enable USB Debugging in Developer Options
   - Grant permission on phone when prompted
   - Run `adb devices` in terminal to verify

2. **"ADB not found"**:
   - Ensure ADB is in your system PATH
   - Or modify `adb_path_guess()` function in code

3. **"Cannot access WhatsApp folder"**:
   - Try both media paths (app may use different locations)
   - Check phone storage permissions for WhatsApp

### Application Issues:

1. **Date parsing errors**: Ensure YYYY-MM-DD format
2. **Slow performance**: Initial scan may take time with large collections
3. **Permission errors**: Run as administrator or check folder permissions

## 📝 Logging

The application provides detailed logs showing:
- Timestamp of each operation
- File export progress
- Error messages with context
- Summary statistics upon completion

## 🎨 Customization

### UI Customization:
- Place icons in `assets/` folder:
  - `app.ico`: Windows window icon
  - `app.png`: Taskbar/dock icon
  - `logo.png`: Header logo

### Code Customization:
- Modify `DEFAULT_SUBFOLDERS` for different WhatsApp versions
- Adjust `DATE_FMT` for alternative date formats
- Extend `adb_path_guess()` for custom ADB locations

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👤 Author

**Muhammad Jalal Fatih**

## 🙏 Acknowledgments

- Android Open Source Project for ADB
- WhatsApp for media organization structure
- Python/Tkinter community for GUI framework

## 🐛 Reporting Issues

If you encounter any bugs or have feature requests, please:
1. Check the Troubleshooting section
2. Search existing issues
3. Create a new issue with:
   - Application mode (ADB/Local)
   - Error messages from log
   - Steps to reproduce
   - System information

---

**Note**: This tool is for personal backup purposes. Always ensure you have permission to copy/move files and comply with WhatsApp's Terms of Service.
