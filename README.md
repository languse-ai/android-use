# Android Use: 基于LLM的安卓手机自动化操作

[English](./README_EN.md) | [中文](./README.md)

**android-use** 是一个开源版的豆包手机项目，旨在通过自然语言驱动实现 Android 手机的自动化操作。它可以将任意 Android 手机变身为智能 AI 手机，极大提升操作效率与体验。

## ✨ 项目特点

1.  **精准定位与交互**：通过 XML 解析技术自动高亮可交互元素，并支持通过索引（Index）进行点击，显著提升了 Agent 的定位能力和操作准确性。
2.  **广泛的模型支持**：完美支持 Deepseek、Kimi-k2、GLM 等国产大模型。即使模型不具备视觉（Vision）能力，依然可以通过 XML 解析实现高效工作。

## 🚀 快速开始

### 1. 准备工作

在使用本工具之前，请确保您的 Android 设备已开启 USB 调试模式。

*   **设备要求**：Android 7.0+。
*   **开启开发者模式**：
    *   打开 **设置** -> **关于手机**。
    *   找到 **版本号**，连续快速点击 10 次左右。
    *   直到屏幕弹出“开发者模式已启用”提示。
    *   *注：不同品牌手机路径可能略有差异，如未找到请自行搜索对应机型的开启教程。*
*   **开启 USB 调试**：
    *   进入 **设置** -> **开发者选项**。
    *   找到并勾选 **USB 调试**。

### 2. 安装 uv 包管理器

推荐使用 `uv` 进行环境管理和安装。

**MacOS/Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. 安装与运行

#### 启动方式

**方式一：WebUI 界面 (推荐)**

```bash
uvx android-use webui
```

<video controls src="https://github.com/user-attachments/assets/65d75067-b9d0-4b5a-a96e-eadf2d9a22e5" title="WebUI Demo"></video>

**方式二：命令行 CLI (交互式)**

```bash
uvx android-use
```

#### 本地开发运行

如果您希望参与开发或进行本地调试：

```bash
git clone https://github.com/languse-ai/android-use
cd android-use
uv sync
# 启动 CLI
python -m android_use.cli
# 启动 WebUI
python -m android_use.app
```

## ⚠️ 免责声明
⚠️ 本项目仅供研究和学习使用。严禁用于非法获取信息、干扰系统或任何违法活动。请仔细审阅 [使用条款](./privacy_policy.txt)。

## 📺 演示案例 (Demos)

以下是三个典型的自动化场景演示：

### 1. 微信视频号互动与分享
**任务描述**：打开微信，进入视频号搜索“豆包手机”，获取当前页面点赞数最多的视频的所有评论，将该视频分享给好友，并发送一段总结性的评论内容。

<video controls src="https://github.com/user-attachments/assets/8f51e56c-16e7-405f-840b-ab8db68bebaa" title="WeChat Demo"></video>

### 2. 抖音电商数据抓取
**任务描述**：打开抖音，进入商城搜索“安踏篮球鞋”，获取并整理排名前 10 的商品信息。

<video controls src="https://github.com/user-attachments/assets/18fdfc82-5cc2-42ca-b1ab-f8e93aef6c60" title="WeChat Demo"></video>

### 3. 小红书自动互动
**任务描述**：打开小红书，搜索“browser-use”，选择当前页面点赞数最多的帖子，进行点赞并发表一条像真人一样的简洁评论，最后总结该帖子的核心内容。

<video controls src="https://github.com/user-attachments/assets/05def550-386d-4d0c-91e9-074baab15641" title="Xiaohongshu Demo"></video>
