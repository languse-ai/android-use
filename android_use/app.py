#!/usr/bin/env python3
"""
Gradio WebUI for Android Use Agent
"""

import asyncio
import json
import os
import time
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import threading
from queue import Queue
import argparse

import gradio as gr
import adbutils

from android_use.config import CONFIG
from android_use.encryption import encrypt_api_key, decrypt_api_key, is_encrypted
from android_use.android.context import AndroidContext, AndroidContextConfig
from android_use.agent.service import AndroidUseAgent
from android_use.agent.views import AgentSettings, AgentHistoryList
from android_use.llm.openai.chat import ChatOpenAI
from android_use.llm.google.chat import ChatGoogle
from android_use.llm.anthropic.chat import ChatAnthropic
from android_use.llm.azure.chat import ChatAzureOpenAI
from android_use.llm.aws.chat_anthropic import ChatAnthropicBedrock
from android_use.llm.aws.chat_bedrock import ChatAWSBedrock


class AndroidUseWebUI:
    """WebUI for Android Use Agent"""
    
    def __init__(self):
        self.workspace_dir = CONFIG.ANDROID_USE_CONFIG_DIR
        self.llm_profiles_path = os.path.join(self.workspace_dir, 'llm_profiles.json')
        self.outputs_dir = os.path.join(self.workspace_dir, 'outputs')
        os.makedirs(self.outputs_dir, exist_ok=True)
        
        # Agent state
        self.agent: Optional[AndroidUseAgent] = None
        self.agent_task: Optional[asyncio.Task] = None
        self.current_device_id: Optional[str] = None
        self.current_llm = None
        self.current_llm_profile_name: Optional[str] = None
        
        # UI state
        self.chat_history = []
        self.current_screenshot = None
        self.current_gif_path = None
        self.is_running = False
        self.is_paused = False
        
        # Thread-safe queue for UI updates
        self.ui_update_queue = Queue()
        
    def load_llm_profiles(self) -> Dict[str, Any]:
        """Load LLM profiles from JSON file"""
        if not os.path.exists(self.llm_profiles_path):
            return {}
        
        try:
            with open(self.llm_profiles_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading LLM profiles: {e}")
            return {}
    
    def save_llm_profiles(self, profiles: Dict[str, Any]):
        """Save LLM profiles to JSON file"""
        try:
            with open(self.llm_profiles_path, 'w', encoding='utf-8') as f:
                json.dump(profiles, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving LLM profiles: {e}")
    
    def get_device_list(self) -> List[str]:
        """Get list of available Android devices"""
        try:
            # Use a local client with a timeout to avoid hanging if ADB is unresponsive
            client = adbutils.AdbClient(socket_timeout=3.0)
            android_devices = client.device_list()
            return [device.serial for device in android_devices]
        except Exception as e:
            print(f"Error getting device list: {e}")
            return []
    
    def get_llm_profile_names(self) -> List[str]:
        """Get list of LLM profile names"""
        profiles = self.load_llm_profiles()
        return list(profiles.keys())
    
    def create_llm_from_profile(self, profile_name: str, profile_config: Dict[str, Any]):
        """Create LLM instance from profile configuration"""
        provider = profile_config.get('provider')
        
        # Decrypt sensitive fields
        decrypted_config = profile_config.copy()
        if 'api_key' in decrypted_config and is_encrypted(decrypted_config['api_key']):
            decrypted_config['api_key'] = decrypt_api_key(decrypted_config['api_key'])
        if 'aws_secret_access_key' in decrypted_config and is_encrypted(decrypted_config['aws_secret_access_key']):
            decrypted_config['aws_secret_access_key'] = decrypt_api_key(decrypted_config['aws_secret_access_key'])
        if 'aws_secret_key' in decrypted_config and is_encrypted(decrypted_config['aws_secret_key']):
            decrypted_config['aws_secret_key'] = decrypt_api_key(decrypted_config['aws_secret_key'])
        if 'aws_session_token' in decrypted_config and is_encrypted(decrypted_config.get('aws_session_token', '')):
            decrypted_config['aws_session_token'] = decrypt_api_key(decrypted_config['aws_session_token'])
        
        try:
            if provider == 'openai':
                return ChatOpenAI(
                    model=decrypted_config['model_name'],
                    api_key=decrypted_config['api_key'],
                    base_url=decrypted_config.get('base_url')
                )
            elif provider == 'google':
                kwargs = {
                    'model': decrypted_config['model_name'],
                    'api_key': decrypted_config['api_key']
                }
                if 'http_options' in decrypted_config:
                    kwargs['http_options'] = decrypted_config['http_options']
                return ChatGoogle(**kwargs)
            elif provider == 'anthropic':
                return ChatAnthropic(
                    model=decrypted_config['model_name'],
                    api_key=decrypted_config['api_key'],
                    base_url=decrypted_config.get('base_url')
                )
            elif provider == 'azure':
                return ChatAzureOpenAI(
                    model=decrypted_config['model_name'],
                    api_key=decrypted_config['api_key'],
                    azure_endpoint=decrypted_config['azure_endpoint'],
                    api_version=decrypted_config.get('api_version', '2025-01-01-preview')
                )
            elif provider == 'aws_bedrock':
                return ChatAWSBedrock(
                    model=decrypted_config['model_name'],
                    aws_access_key_id=decrypted_config['aws_access_key_id'],
                    aws_secret_access_key=decrypted_config['aws_secret_access_key'],
                    aws_session_token=decrypted_config.get('aws_session_token'),
                    aws_region=decrypted_config['aws_region']
                )
            elif provider == 'aws_anthropic':
                return ChatAnthropicBedrock(
                    model=decrypted_config['model_name'],
                    aws_access_key=decrypted_config['aws_access_key'],
                    aws_secret_key=decrypted_config['aws_secret_key'],
                    aws_session_token=decrypted_config.get('aws_session_token'),
                    aws_region=decrypted_config['aws_region']
                )
            else:
                raise ValueError(f"Unsupported provider: {provider}")
        except Exception as e:
            raise Exception(f"Error creating LLM: {e}")
    
    def save_new_profile(self, profile_name: str, provider: str, **kwargs) -> str:
        """Save a new LLM profile"""
        if not profile_name:
            return "❌ Profile name is required"
        
        profiles = self.load_llm_profiles()
        
        if profile_name in profiles:
            return f"❌ Profile '{profile_name}' already exists"
        
        profile = {'provider': provider}
        
        # Add fields based on provider
        profile['use_vision'] = kwargs.get('use_vision', True)

        if provider == 'openai':
            profile['model_name'] = kwargs.get('model_name', '')
            profile['api_key'] = encrypt_api_key(kwargs.get('api_key', ''))
            if kwargs.get('base_url'):
                profile['base_url'] = kwargs['base_url']
        
        elif provider == 'google':
            profile['model_name'] = kwargs.get('model_name', '')
            profile['api_key'] = encrypt_api_key(kwargs.get('api_key', ''))
            if kwargs.get('base_url'):
                profile['http_options'] = {'base_url': kwargs['base_url']}
        
        elif provider == 'anthropic':
            profile['model_name'] = kwargs.get('model_name', '')
            profile['api_key'] = encrypt_api_key(kwargs.get('api_key', ''))
            if kwargs.get('base_url'):
                profile['base_url'] = kwargs['base_url']
        
        elif provider == 'azure':
            profile['model_name'] = kwargs.get('model_name', '')
            profile['api_key'] = encrypt_api_key(kwargs.get('api_key', ''))
            profile['azure_endpoint'] = kwargs.get('azure_endpoint', '')
            profile['api_version'] = kwargs.get('api_version', '2025-01-01-preview')
        
        elif provider == 'aws_bedrock':
            profile['model_name'] = kwargs.get('model_name', '')
            profile['aws_access_key_id'] = kwargs.get('aws_access_key_id', '')
            profile['aws_secret_access_key'] = encrypt_api_key(kwargs.get('aws_secret_access_key', ''))
            if kwargs.get('aws_session_token'):
                profile['aws_session_token'] = encrypt_api_key(kwargs['aws_session_token'])
            profile['aws_region'] = kwargs.get('aws_region', 'us-east-1')
        
        elif provider == 'aws_anthropic':
            profile['model_name'] = kwargs.get('model_name', '')
            profile['aws_access_key'] = kwargs.get('aws_access_key', '')
            profile['aws_secret_key'] = encrypt_api_key(kwargs.get('aws_secret_key', ''))
            if kwargs.get('aws_session_token'):
                profile['aws_session_token'] = encrypt_api_key(kwargs['aws_session_token'])
            profile['aws_region'] = kwargs.get('aws_region', 'us-east-1')
        
        profiles[profile_name] = profile
        self.save_llm_profiles(profiles)
        
        return f"✓ Profile '{profile_name}' created successfully!"
    
    def step_callback(self, current_state, model_output, step: int):
        """Callback for each agent step - updates UI with step information (sync version)"""
        # Format step information for chatbot
        step_info = f"**Step {step + 1}**\n\n"
        
        if model_output.evaluation_previous_goal:
            step_info += f"**Evaluation:** {model_output.evaluation_previous_goal}\n\n"
        
        if model_output.think:
            step_info += f"**Think:** {model_output.think}\n\n"
        
        # Format actions as JSON
        actions_json = []
        for action in model_output.action:
            actions_json.append(action.model_dump(exclude_none=True))
        
        step_info += f"**Actions:**\n```json\n{json.dumps(actions_json, indent=2, ensure_ascii=False)}\n```"
        
        # Add to chat history
        self.chat_history.append({"role": "assistant", "content": step_info})
        
        # Update screenshot with highlight (before action)
        if current_state.highlight_screenshot:
            self.current_screenshot = self.base64_to_image(current_state.highlight_screenshot)
        
        # Queue update
        update_data = {
            'type': 'step',
            'chat_history': self.chat_history.copy(),
            'screenshot': self.current_screenshot
        }
        self.ui_update_queue.put(update_data)
        
        # Wait a bit for action execution
        time.sleep(0.5)
        
        # Update state again to get post-action screenshot
        post_action_state = self.agent.android_context.update_state()
        if post_action_state.screenshot:
            self.current_screenshot = self.base64_to_image(post_action_state.screenshot)
            self.ui_update_queue.put({
                'type': 'screenshot_update',
                'screenshot': self.current_screenshot
            })
    
    def done_callback(self, history: AgentHistoryList):
        """Callback when agent completes (sync version)"""
        # Show completion message
        completion_msg = f"✅ **Task completed!**\n\nTotal steps: {history.number_of_steps()}\nDuration: {history.total_duration_seconds():.2f}s"
        self.chat_history.append({"role": "assistant", "content": completion_msg})
        
        # Queue update with GIF if available and button state reset
        self.ui_update_queue.put({
            'type': 'done',
            'chat_history': self.chat_history.copy(),
            'gif_path': self.current_gif_path,
            'reset_buttons': True  # Signal to reset button states
        })
        
        self.is_running = False
    
    def base64_to_image(self, base64_str: str):
        """Convert base64 string to image path for Gradio"""
        if not base64_str:
            return None
        
        # Create temp file
        temp_path = os.path.join(self.outputs_dir, f"temp_{time.time()}.png")
        
        try:
            # Decode base64
            img_data = base64.b64decode(base64_str)
            with open(temp_path, 'wb') as f:
                f.write(img_data)
            return temp_path
        except Exception as e:
            print(f"Error converting base64 to image: {e}")
            return None
    
    def run_agent_sync(self, task: str):
        """Run agent synchronously in a separate thread"""
        try:
            self.is_running = True
            self.is_paused = False
            self.chat_history = []
            self.current_screenshot = None
            self.current_gif_path = None
            
            # Add task to chat
            self.chat_history.append({"role": "user", "content": task})
            
            # Setup GIF path
            timestamp = time.time()
            self.current_gif_path = os.path.join(self.outputs_dir, f"agent_history-{timestamp}.gif")
            self.agent.agent_settings.generate_gif = self.current_gif_path
            
            # Run agent in new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.agent.run(task, max_steps=100))
            loop.close()
            
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            self.chat_history.append({"role": "assistant", "content": error_msg})
            self.ui_update_queue.put({
                'type': 'error',
                'chat_history': self.chat_history.copy(),
                'reset_buttons': True
            })
        finally:
            self.is_running = False
    
    def initialize_agent(self, device_id: str, profile_name: str) -> Tuple[bool, str]:
        """Initialize agent with selected device and LLM profile"""
        try:
            if not device_id:
                return False, "❌ Please select a device"
            
            if not profile_name:
                return False, "❌ Please select an LLM profile"
            
            # Load profile
            profiles = self.load_llm_profiles()
            if profile_name not in profiles:
                return False, f"❌ Profile '{profile_name}' not found"
            
            profile_config = profiles[profile_name]
            
            # Create LLM
            llm = self.create_llm_from_profile(profile_name, profile_config)
            
            # Initialize Android context
            config = AndroidContextConfig(
                highlight_elements=True,
                device_id=device_id
            )
            android_context = AndroidContext(config)
            
            # Create agent settings
            agent_settings = AgentSettings(
                generate_gif="",
                use_vision=profile_config.get('use_vision', True),
            )
            
            # Create agent with callbacks
            self.agent = AndroidUseAgent(
                agent_settings=agent_settings,
                llm=llm,
                android_context=android_context,
                register_new_step_callback=self.step_callback,
                register_done_callback=self.done_callback
            )
            
            self.current_device_id = device_id
            self.current_llm = llm
            self.current_llm_profile_name = profile_name
            
            return True, f"✓ Agent initialized with device: {device_id} and profile: {profile_name}"
            
        except Exception as e:
            import traceback
            return False, f"❌ Error initializing agent: {str(e)}\n{traceback.format_exc()}"
    
    def build_ui(self):
        """Build Gradio UI"""
        # Removed theme from Blocks constructor to fix warning
        with gr.Blocks(title="Android Use Agent") as demo:
            gr.Markdown("# <center>🤖 Android Use Agent - WebUI</center>")
            gr.Markdown("<center>Automate Android devices using AI agents</center>")
            
            # 1. LLM Profile Creation Section (Moved to top)
            with gr.Accordion("➕ Create New LLM Profile", open=False):
                with gr.Row():
                    profile_name_input = gr.Textbox(label="Profile Name", placeholder="my-gpt4-profile")
                    provider_dropdown = gr.Dropdown(
                        label="Provider",
                        choices=["openai", "google", "anthropic", "azure", "aws_bedrock", "aws_anthropic"],
                        value="openai"
                    )
                    use_vision_checkbox = gr.Checkbox(label="Suppport Vision", value=True)
                
                # Dynamic fields based on provider
                with gr.Group() as openai_fields:
                    gr.Markdown("### OpenAI / OpenAI Compatible")
                    openai_model = gr.Textbox(label="Model Name", placeholder="gpt-4o")
                    openai_api_key = gr.Textbox(label="API Key", type="password")
                    openai_base_url = gr.Textbox(label="Base URL (optional)", placeholder="https://api.openai.com/v1")
                
                with gr.Group(visible=False) as google_fields:
                    gr.Markdown("### Google Gemini")
                    google_model = gr.Textbox(label="Model Name", placeholder="gemini-2.0-flash-exp")
                    google_api_key = gr.Textbox(label="API Key", type="password")
                    google_base_url = gr.Textbox(label="Base URL (optional)")
                
                with gr.Group(visible=False) as anthropic_fields:
                    gr.Markdown("### Anthropic Claude")
                    anthropic_model = gr.Textbox(label="Model Name", placeholder="claude-3-5-sonnet-20241022")
                    anthropic_api_key = gr.Textbox(label="API Key", type="password")
                    anthropic_base_url = gr.Textbox(label="Base URL (optional)")
                
                with gr.Group(visible=False) as azure_fields:
                    gr.Markdown("### Azure OpenAI")
                    azure_model = gr.Textbox(label="Model/Deployment Name")
                    azure_api_key = gr.Textbox(label="API Key", type="password")
                    azure_endpoint = gr.Textbox(label="Azure Endpoint")
                    azure_api_version = gr.Textbox(label="API Version", value="2025-01-01-preview")
                
                with gr.Group(visible=False) as aws_bedrock_fields:
                    gr.Markdown("### AWS Bedrock")
                    aws_bedrock_model = gr.Textbox(label="Model ID")
                    aws_bedrock_access_key = gr.Textbox(label="AWS Access Key ID")
                    aws_bedrock_secret_key = gr.Textbox(label="AWS Secret Access Key", type="password")
                    aws_bedrock_session_token = gr.Textbox(label="AWS Session Token (optional)", type="password")
                    aws_bedrock_region = gr.Textbox(label="AWS Region", value="us-east-1")
                
                with gr.Group(visible=False) as aws_anthropic_fields:
                    gr.Markdown("### AWS Bedrock Anthropic")
                    aws_anthropic_model = gr.Textbox(label="Model ID")
                    aws_anthropic_access_key = gr.Textbox(label="AWS Access Key")
                    aws_anthropic_secret_key = gr.Textbox(label="AWS Secret Key", type="password")
                    aws_anthropic_session_token = gr.Textbox(label="AWS Session Token (optional)", type="password")
                    aws_anthropic_region = gr.Textbox(label="AWS Region", value="us-east-1")
                
                save_profile_btn = gr.Button("💾 Save Profile", variant="primary")
                profile_save_status = gr.Textbox(label="Save Status", interactive=False, show_label=False)

            # 2. Controls (Device and Profile Selection)
            with gr.Row():
                # Get initial lists
                initial_devices = self.get_device_list()
                initial_profiles = self.get_llm_profile_names()
                
                default_device = initial_devices[0] if initial_devices else None
                default_profile = initial_profiles[0] if initial_profiles else None

                device_dropdown = gr.Dropdown(
                    label="📱 Select Device",
                    choices=initial_devices,
                    value=default_device,
                    interactive=True,
                    allow_custom_value=False
                )
                
                llm_profile_dropdown = gr.Dropdown(
                    label="🤖 Select LLM Profile",
                    choices=initial_profiles,
                    value=default_profile,
                    interactive=True,
                    allow_custom_value=False
                )
            
            init_status = gr.Textbox(
                label="Status", 
                interactive=False, 
                value="Please select device and LLM profile" if not (default_device and default_profile) else f"Ready. Device: {default_device}, Profile: {default_profile}",
                show_label=False,
                visible=False
            )

            # 3. Main Content Area (Chatbot + Screenshot)
            with gr.Row():
                # Left column - Chat and Controls
                with gr.Column(scale=2):
                    chatbot = gr.Chatbot(
                        label="Agent Conversation",
                        height=500,
                        show_label=True,
                        render_markdown=True,
                        latex_delimiters=[
                            {"left": "$$", "right": "$$", "display": True},
                            {"left": "$", "right": "$", "display": False}
                        ],
                    )
                    
                    # Task input and controls
                    with gr.Row():
                        task_input = gr.Textbox(
                            label="Task",
                            placeholder="Enter your task here...",
                            scale=4,
                            lines=2
                        )
                    
                    with gr.Row():
                        # Initialize interactive based on defaults
                        initial_interactive = bool(default_device and default_profile)
                        send_btn = gr.Button("▶️ Send", variant="primary", interactive=initial_interactive)
                        stop_btn = gr.Button("⏹️ Stop", variant="stop", interactive=False)
                        pause_resume_btn = gr.Button("⏸️ Pause", interactive=False)
                        clear_btn = gr.Button("🗑️ Clear History")

                # Right column - Screenshot and GIF (overlapping in same position)
                with gr.Column(scale=1):
                    screenshot_display = gr.Image(
                        label="📸 Current Screenshot",
                        type="filepath",
                        height=500,
                        visible=True
                    )
            
            # --- Event Handlers ---

            # Provider fields visibility
            def update_provider_fields(provider):
                return (
                    gr.update(visible=provider == "openai"),
                    gr.update(visible=provider == "google"),
                    gr.update(visible=provider == "anthropic"),
                    gr.update(visible=provider == "azure"),
                    gr.update(visible=provider == "aws_bedrock"),
                    gr.update(visible=provider == "aws_anthropic")
                )
            
            provider_dropdown.change(
                update_provider_fields,
                inputs=[provider_dropdown],
                outputs=[openai_fields, google_fields, anthropic_fields, azure_fields, aws_bedrock_fields, aws_anthropic_fields]
            )
            
            # Save Profile
            def save_profile(profile_name, provider, use_vision, *args):
                kwargs = {}
                if provider == "openai":
                    kwargs = {'model_name': args[0], 'api_key': args[1], 'base_url': args[2]}
                elif provider == "google":
                    kwargs = {'model_name': args[3], 'api_key': args[4], 'base_url': args[5]}
                elif provider == "anthropic":
                    kwargs = {'model_name': args[6], 'api_key': args[7], 'base_url': args[8]}
                elif provider == "azure":
                    kwargs = {'model_name': args[9], 'api_key': args[10], 'azure_endpoint': args[11], 'api_version': args[12]}
                elif provider == "aws_bedrock":
                    kwargs = {'model_name': args[13], 'aws_access_key_id': args[14], 'aws_secret_access_key': args[15], 
                             'aws_session_token': args[16], 'aws_region': args[17]}
                elif provider == "aws_anthropic":
                    kwargs = {'model_name': args[18], 'aws_access_key': args[19], 'aws_secret_key': args[20],
                             'aws_session_token': args[21], 'aws_region': args[22]}
                
                # Add use_vision to kwargs
                kwargs['use_vision'] = use_vision
                
                result = self.save_new_profile(profile_name, provider, **kwargs)
                return result, gr.update(choices=self.get_llm_profile_names())
            
            save_profile_btn.click(
                save_profile,
                inputs=[profile_name_input, provider_dropdown, use_vision_checkbox, 
                       openai_model, openai_api_key, openai_base_url,
                       google_model, google_api_key, google_base_url,
                       anthropic_model, anthropic_api_key, anthropic_base_url,
                       azure_model, azure_api_key, azure_endpoint, azure_api_version,
                       aws_bedrock_model, aws_bedrock_access_key, aws_bedrock_secret_key, 
                       aws_bedrock_session_token, aws_bedrock_region,
                       aws_anthropic_model, aws_anthropic_access_key, aws_anthropic_secret_key,
                       aws_anthropic_session_token, aws_anthropic_region],
                outputs=[profile_save_status, llm_profile_dropdown]
            )
            
            # Initialization Logic
            def on_device_or_profile_change(device, profile):
                if device and profile:
                    success, msg = self.initialize_agent(device, profile)
                    return gr.update(interactive=success), msg
                else:
                    return gr.update(interactive=False), "Please select both device and LLM profile"
            
            device_dropdown.change(
                on_device_or_profile_change,
                inputs=[device_dropdown, llm_profile_dropdown],
                outputs=[send_btn, init_status]
            )
            
            llm_profile_dropdown.change(
                on_device_or_profile_change,
                inputs=[device_dropdown, llm_profile_dropdown],
                outputs=[send_btn, init_status]
            )
            
            # Auto-refresh Dropdowns on Focus
            def update_devices_list(current_value):
                devices = self.get_device_list()
                # Keep current value if it exists in new list
                new_value = current_value if current_value in devices else (devices[0] if devices else None)
                return gr.update(choices=devices, value=new_value)

            def update_profiles_list(current_value):
                profiles = self.get_llm_profile_names()
                new_value = current_value if current_value in profiles else (profiles[0] if profiles else None)
                return gr.update(choices=profiles, value=new_value)

            device_dropdown.focus(
                update_devices_list,
                inputs=[device_dropdown],
                outputs=[device_dropdown]
            )
            
            llm_profile_dropdown.focus(
                update_profiles_list,
                inputs=[llm_profile_dropdown],
                outputs=[llm_profile_dropdown]
            )

            # Task Execution
            def start_task(task):
                if not task.strip():
                    return (
                        self.chat_history,
                        gr.update(value=None, visible=True, label="📸 Current Screenshot"),  # Reset to screenshot mode
                        gr.update(value=""),
                        gr.update(interactive=False),
                        gr.update(interactive=True),
                        gr.update(value="⏸️ Pause", interactive=True)
                    )
                
                thread = threading.Thread(target=self.run_agent_sync, args=(task,), daemon=True)
                thread.start()
                
                return (
                    self.chat_history,
                    gr.update(value=None, visible=True, label="📸 Current Screenshot"),  # Reset to screenshot mode
                    gr.update(value=""),
                    gr.update(interactive=False),
                    gr.update(interactive=True),
                    gr.update(value="⏸️ Pause", interactive=True)
                )
            
            def stop_task():
                if self.agent:
                    self.agent.stop()
                return (
                    gr.update(interactive=True),
                    gr.update(interactive=False),
                    gr.update(value="⏸️ Pause", interactive=False)
                )
            
            def pause_resume_task(current_label):
                if not self.agent:
                    return gr.update()
                
                if "Pause" in current_label:
                    self.agent.pause()
                    self.is_paused = True
                    return gr.update(value="▶️ Resume")
                else:
                    self.agent.resume()
                    self.is_paused = False
                    return gr.update(value="⏸️ Pause")
            
            def clear_history():
                self.chat_history = []
                self.current_screenshot = None
                self.current_gif_path = None
                if self.agent:
                    if hasattr(self.agent, 'message_manager'):
                        self.agent.message_manager.clear_message_history()
                    # Reset agent state for fresh start
                    if hasattr(self.agent, 'reset'):
                        self.agent.reset()
                        
                return [], gr.update(value=None, visible=True)
            
            send_btn.click(
                start_task,
                inputs=[task_input],
                outputs=[chatbot, screenshot_display, task_input, send_btn, stop_btn, pause_resume_btn]
            )
            
            stop_btn.click(
                stop_task,
                outputs=[send_btn, stop_btn, pause_resume_btn]
            )
            
            pause_resume_btn.click(
                pause_resume_task,
                inputs=[pause_resume_btn],
                outputs=[pause_resume_btn]
            )
            
            clear_btn.click(
                clear_history,
                outputs=[chatbot, screenshot_display]
            )
            
            # Periodic UI update with button state handling
            def check_updates():
                updates = []
                while not self.ui_update_queue.empty():
                    try:
                        update = self.ui_update_queue.get_nowait()
                        updates.append(update)
                    except:
                        break
                
                if not updates:
                    return gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
                
                last_update = updates[-1]
                
                if last_update['type'] == 'step':
                    return (
                        gr.update(value=last_update['chat_history']),
                        gr.update(value=last_update.get('screenshot'), visible=True),  # Show screenshot during execution
                        gr.update(),  # send_btn - no change
                        gr.update(),  # stop_btn - no change
                        gr.update()   # pause_resume_btn - no change
                    )
                elif last_update['type'] == 'screenshot_update':
                    return (
                        gr.update(),
                        gr.update(value=last_update['screenshot'], visible=True),  # Keep screenshot visible
                        gr.update(),  # send_btn - no change
                        gr.update(),  # stop_btn - no change
                        gr.update()   # pause_resume_btn - no change
                    )
                elif last_update['type'] == 'done':
                    gif_path = last_update.get('gif_path')
                    # Switch to GIF when task completes
                    screenshot_update = gr.update(value=gif_path, visible=True, label="🎬 Task GIF") if gif_path and os.path.exists(gif_path) else gr.update()
                    return (
                        gr.update(value=last_update['chat_history']),
                        screenshot_update,
                        gr.update(interactive=True),   # send_btn - enable
                        gr.update(interactive=False),  # stop_btn - disable
                        gr.update(value="⏸️ Pause", interactive=False)  # pause_resume_btn - reset and disable
                    )
                elif last_update['type'] == 'error':
                    return (
                        gr.update(value=last_update['chat_history']),
                        gr.update(visible=True, label="📸 Current Screenshot"),  # Keep screenshot mode
                        gr.update(interactive=True),   # send_btn - enable
                        gr.update(interactive=False),  # stop_btn - disable
                        gr.update(value="⏸️ Pause", interactive=False)  # pause_resume_btn - reset and disable
                    )
                
                return gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            
            # Use timer for continuous polling (every 500ms)
            timer = gr.Timer(value=0.5, active=True)
            timer.tick(
                check_updates,
                outputs=[chatbot, screenshot_display, send_btn, stop_btn, pause_resume_btn]
            )

            # Auto-initialize if defaults are present
            def initial_check(device, profile):
                if device and profile:
                    success, msg = self.initialize_agent(device, profile)
                    return gr.update(interactive=success), msg
                return gr.update(), "Please select both device and LLM profile"

            demo.load(
                initial_check,
                inputs=[device_dropdown, llm_profile_dropdown],
                outputs=[send_btn, init_status]
            )
        
        return demo


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Android Use Agent WebUI")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=7860, help="Port to bind the server to")
    args = parser.parse_args()

    print("🚀 Starting Android Use Agent WebUI...")
    print("📍 Make sure you have Android devices connected via ADB")
    print(f"🌐 WebUI will be available at http://{args.host}:{args.port}")
    
    webui = AndroidUseWebUI()
    demo = webui.build_ui()
    # Moved theme to launch() as per Gradio 6.0 warning
    # Add outputs directory and config directory to allowed paths for GIF access
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=False,
        show_error=True,
        theme=gr.themes.Ocean(),
        allowed_paths=[
            webui.outputs_dir,
            str(CONFIG.ANDROID_USE_CONFIG_DIR)
        ]
    )


if __name__ == "__main__":
    main()
