# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Android Use is an AI-powered Android phone automation tool that enables natural language-driven control of Android devices. It uses LLM agents to interpret user tasks and execute multi-step automation workflows on Android phones via USB debugging.

**Key Technology Stack:**
- Python 3.11+ (uiautomator2 for Android control, adbutils for device communication)
- Gradio for WebUI, Rich for CLI
- Multiple LLM provider integrations (OpenAI, Anthropic, Google, Deepseek, Ollama, etc.)

## Development Commands

### Installation & Setup

```bash
# Clone and install dependencies
git clone https://github.com/languse-ai/android-use
cd android-use
uv sync

# Run CLI mode
python -m android_use.cli

# Run WebUI mode
python -m android_use.app
```

### Running from Package

```bash
# Install and run CLI
uvx android-use

# Install and run WebUI
uvx android-use webui
```

### Testing

```bash
# Run all tests (requires connected Android device with USB debugging enabled)
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_agents.py
python -m pytest tests/test_android_context.py
python -m pytest tests/test_tools.py
python -m pytest tests/test_llm.py
```

**Note:** Tests require an Android device (Android 7.0+) connected via USB with USB debugging enabled.

### Building & Publishing

```bash
# Build package
python -m build

# The project uses GitHub Actions for automated PyPI publishing on release
# See .github/workflows/publish.yml
```

## Architecture

### Core Components

The codebase is organized around four primary subsystems:

#### 1. Agent System ([android_use/agent/](android_use/agent/))

**AndroidUseAgent** ([service.py:28](android_use/agent/service.py#L28)) - Main orchestrator that coordinates the entire automation workflow:
- Manages conversation state and message history via MessageManager
- Generates system prompts with available actions and Android state
- Invokes LLM to decide next actions
- Executes actions through AndroidTools
- Handles step-by-step execution with callbacks for UI updates
- Supports pause/resume and error handling

**Key Flow:**
1. User provides task → Agent generates system prompt with available actions
2. Agent captures Android state (screenshot + XML DOM)
3. LLM analyzes state and selects action(s)
4. Agent executes action via AndroidTools
5. Repeats until task completion or max steps reached

**Important Classes:**
- `MessageManager` - Manages conversation history with token limit awareness
- `AgentSystemPrompt` - Generates system prompts including action descriptions
- `StateMessagePrompt` - Formats Android state for LLM (screenshot + highlighted DOM)

#### 2. Android Context ([android_use/android/](android_use/android/))

**AndroidContext** ([context.py:29](android_use/android/context.py#L29)) - Handles all device interaction and state parsing:
- Connects to Android device via uiautomator2
- Captures screenshots and XML hierarchy
- Parses XML into DOMElementNode tree structure
- **XML Parsing & Highlighting:** Automatically identifies interactive elements (clickable, focusable, long-clickable) and assigns them index numbers for precise targeting
- Provides device control methods (tap, swipe, input, shell commands)

**DOM Structure:**
- `DOMElementNode` - Represents UI elements with bounds, text, attributes, and interaction capabilities
- Interactive elements get highlighted with colored boxes and index numbers overlaid on screenshots
- Three node types: `NODE_TYPE_INTERACTIVE`, `NODE_TYPE_TEXT`, `NODE_TYPE_NON_INTERACTIVE`

**Critical Feature:** Vision-optional design - even non-vision LLMs can operate using XML-based element descriptions and index-based targeting.

#### 3. Tools System ([android_use/tools/](android_use/tools/))

**AndroidTools** ([service.py:38](android_use/tools/service.py#L38)) - Registry and executor for available actions:

**Registry Architecture** ([registry/service.py](android_use/tools/registry/service.py)):
- Dynamic action registration using decorator pattern (`@registry.action`)
- Actions auto-generate Pydantic models from function signatures
- Supports filtering actions based on context or device capabilities
- Creates dynamic `ActionModel` with all registered actions as optional fields

**Default Actions:**
- `done` - Complete task with extracted content
- `wait` - Wait for specified seconds
- `launch_app` - Launch app by name (uses APP_PACKAGES registry)
- `click_element` - Click element by index
- `input_text` - Input text to focused element
- `swipe` - Swipe in direction or between coordinates
- `drag` - Drag from one element to another
- `long_press_element` - Long press on element
- `press_key` - Press Android key code
- `shell_command` - Execute ADB shell command
- `pull_file` / `push_file` - Transfer files to/from device
- `record_important_content` - Store extracted information
- `generate_or_update_todos` - Create/update task list

**Action Execution:**
- All actions return `ActionResult` with success status and extracted content
- Actions can access `AndroidContext` for device control
- Screenshot highlighting shows executed actions visually

#### 4. LLM Integration ([android_use/llm/](android_use/llm/))

**BaseChatModel Protocol** ([base.py](android_use/llm/base.py)) - Unified interface for all LLM providers

**Supported Providers:**
- OpenAI (`openai/`)
- Anthropic Claude (`anthropic/`)
- Google Gemini (`google/`)
- Azure OpenAI (`azure/`)
- AWS Bedrock (`aws/`)
- Deepseek (`deepseek/`)
- Ollama (`ollama/`)
- OpenAI-compatible endpoints (`openai_compatible/`)

**Message Types:**
- `SystemMessage` - System prompts with action descriptions
- `UserMessage` - User requests with Android state (text + image)
- `AssistantMessage` - LLM responses with selected actions

**Token Tracking** ([tokens/service.py](android_use/tokens/service.py)):
- `TokenCost` service tracks usage across providers
- Cost calculation using provider-specific pricing in `tokens/mappings.py`

### Key Design Patterns

#### Dynamic Action Registry

Actions self-register using decorators. To add new actions:

```python
@registry.action('Description of what this does', param_model=MyParamModel)
async def my_action(params: MyParamModel, android: AndroidContext):
    # Implementation
    return ActionResult(extracted_content="Result")
```

The registry automatically:
1. Creates action schemas for LLM tool calling
2. Validates parameters using Pydantic models
3. Handles both sync and async action functions
4. Injects AndroidContext and LLM dependencies

#### State Management

Agent maintains two parallel state histories:
- `AgentHistoryList` - Complete execution history with all steps
- `MessageHistory` - LLM conversation history (with token management)

Each step captures:
- Android state (screenshot + XML DOM)
- Selected action and parameters
- Execution result
- Token usage and timing

#### Vision-Optional Design

The system works with both vision and non-vision LLMs:
- **With vision:** LLM sees highlighted screenshot with element indices
- **Without vision:** LLM receives XML DOM description with element attributes and indices
- Both modes use same index-based targeting for actions

### Configuration

**Config System** ([config.py](android_use/config.py)):
- XDG-compliant config directory: `~/.config/android_use/`
- Environment variables for customization (ANDROID_USE_LOGGING_LEVEL, etc.)
- LLM profile storage with encrypted API keys ([encryption.py](android_use/encryption.py))

**Entry Points:**
- CLI: `android_use.cli:main` → [cli.py](android_use/cli.py)
- WebUI: Run via `python -m android_use.app` → [app.py](android_use/app.py)

### Working with the Codebase

**Agent Behavior:**
- Max steps controlled by `AgentSettings.max_steps` (default varies by mode)
- Agent uses reflection - LLM sees previous actions and their results
- Support for initial actions (pre-programmed action sequences)

**Device Requirements:**
- Android 7.0+ with USB debugging enabled
- Device connected via USB or network ADB
- uiautomator2 server automatically installed on device on first connection

**Common Patterns:**
- Actions use async/await throughout
- XML parsing happens at each step to get current UI state
- Screenshots are base64-encoded for LLM vision input
- Element highlighting uses PIL ImageDraw with rainbow colors for indices
