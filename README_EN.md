# Android Use: Automate Android phones using AI agents

[English](./README_EN.md) | [中文](./README.md)

**android-use** is a tool designed for natural language-driven automation on Android devices. It enables automated operations on Android phones using natural language commands.

## ✨ Features

1.  **Precise Positioning & Interaction**: Utilizes XML parsing to highlight interactive elements and supports clicking via index, significantly enhancing the Agent's positioning capabilities.
2.  **Broad Model Support**: Supports domestic models like Deepseek, Kimi-k2, GLM, etc. It works effectively even without vision capabilities by leveraging XML parsing.

## 🚀 Getting Started

### 1. Prerequisites

Before using this tool, ensure USB debugging is enabled on your Android device.

*   **Device Requirements**: Android 7.0+.
*   **Enable Developer Mode**:
    *   Go to **Settings** -> **About Phone**.
    *   Find **Build Number** and tap it continuously about 10 times.
    *   Wait for the "You are now a developer!" toast message.
    *   *Note: Steps may vary slightly by phone manufacturer. Search online if you can't find it.*
*   **Enable USB Debugging**:
    *   Go to **Settings** -> **Developer Options**.
    *   Find and enable **USB Debugging**.

### 2. Install uv

Install the `uv` package manager from the official website.

**MacOS/Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Setup Environment

#### Install android_use

```bash
uv pip install android_use -U
```

#### Running the Application

**Option 1: WebUI (Recommended)**

```bash
android_use_webui
```

<video controls src="https://github.com/user-attachments/assets/65d75067-b9d0-4b5a-a96e-eadf2d9a22e5" title="WebUI Demo"></video>

**Option 2: CLI (Interactive)**

```bash
android_use
```

#### Local Development

If you want to contribute or develop locally:

```bash
git clone https://github.com/YourUsername/android_use.git
cd android_use
uv sync
# Start CLI
python -m android_use.cli
# Start WebUI
python -m android_use.app
```

## ⚠️ Disclaimer
⚠️ This project is for research and study purposes only. It is strictly prohibited to use it for illegal information acquisition, system interference, or any illegal activities. Please review the [Terms of Use](./privacy_policy_en.txt) carefully.

## 📺 Demos

Here are three demos showcasing the capabilities:

### 1. WeChat Video Account Interaction
**Task**: Open WeChat, search for "Doubao Phone" in Video Accounts, get all comments from the most liked video on the current page, share this video with a friend, and send a summary of the comments.

<video controls src="https://github.com/user-attachments/assets/8f51e56c-16e7-405f-840b-ab8db68bebaa" title="WeChat Demo"></video>

### 2. Douyin E-commerce Data Scraping
**Task**: Open Douyin, search for "Anta Basketball Shoes" in the shop, and retrieve information for the top 10 products.

<video controls src="https://github.com/user-attachments/assets/18fdfc82-5cc2-42ca-b1ab-f8e93aef6c60" title="Douyin Demo"></video>

### 3. Xiaohongshu Interaction
**Task**: Open Xiaohongshu, search for "browser-use", select the most liked post on the current page, like it, leave a concise, human-like comment, and summarize the core content of the post.

<video controls src="https://github.com/user-attachments/assets/05def550-386d-4d0c-91e9-074baab15641" title="Xiaohongshu Demo"></video>
