#!/usr/bin/env python3
"""
Android Use CLI - Interactive command-line interface for Android automation agent
"""

import asyncio
import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

import adbutils
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import print as rprint

from android_use.config import CONFIG
from android_use.encryption import encrypt_api_key, decrypt_api_key, is_encrypted
from android_use.android.context import AndroidContext, AndroidContextConfig
from android_use.agent.service import AndroidUseAgent
from android_use.agent.views import AgentSettings
from android_use.llm.openai.chat import ChatOpenAI
from android_use.llm.google.chat import ChatGoogle
from android_use.llm.anthropic.chat import ChatAnthropic
from android_use.llm.azure.chat import ChatAzureOpenAI
from android_use.llm.aws.chat_anthropic import ChatAnthropicBedrock
from android_use.llm.aws.chat_bedrock import ChatAWSBedrock

console = Console()

# ASCII Logo for ANDROID USE
LOGO = """
[bold cyan]
 █████╗ ███╗   ██╗██████╗ ██████╗  ██████╗ ██╗██████╗     ██╗   ██╗███████╗███████╗
██╔══██╗████╗  ██║██╔══██╗██╔══██╗██╔═══██╗██║██╔══██╗    ██║   ██║██╔════╝██╔════╝
███████║██╔██╗ ██║██║  ██║██████╔╝██║   ██║██║██║  ██║    ██║   ██║███████╗█████╗
██╔══██║██║╚██╗██║██║  ██║██╔══██╗██║   ██║██║██║  ██║    ██║   ██║╚════██║██╔══╝
██║  ██║██║ ╚████║██████╔╝██║  ██║╚██████╔╝██║██████╔╝    ╚██████╔╝███████║███████╗
╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝╚═════╝      ╚═════╝ ╚══════╝╚══════╝
[/bold cyan]
[bold white]Make Android Use Easier for AI Agents[/bold white]
"""


class AndroidUseCLI:
    """Interactive CLI for Android Use agent"""
    
    def __init__(self):
        self.workspace_dir = CONFIG.ANDROID_USE_CONFIG_DIR
        self.llm_profiles_path = os.path.join(self.workspace_dir, 'llm_profiles.json')
        self.outputs_dir = os.path.join(self.workspace_dir, 'outputs')
        os.makedirs(self.outputs_dir, exist_ok=True)
        
        self.agent: Optional[AndroidUseAgent] = None
        self.agent_task: Optional[asyncio.Task] = None
        self.keyboard_listener_active = False
        
    def show_logo(self):
        """Display the ASCII logo"""
        console.print(LOGO)
        console.print()
    
    def select_device(self) -> Optional[str]:
        """Select an Android device from available devices"""
        console.print("[bold yellow]📱 Selecting Android Device...[/bold yellow]\n")
        
        try:
            # Use a local client with a timeout to avoid hanging if ADB is unresponsive
            client = adbutils.AdbClient(socket_timeout=3.0)
            android_devices = client.device_list()
        except Exception as e:
            console.print(f"[bold red]❌ Error getting device list: {e}[/bold red]")
            return None
        
        if not android_devices:
            console.print("[bold red]❌ No Android devices found![/bold red]")
            console.print("Please connect a device and enable USB debugging.")
            return None
        
        # If only one device, auto-select it
        if len(android_devices) == 1:
            selected_device = android_devices[0]
            console.print(f"[bold green]✓ Auto-selected device: {selected_device.serial}[/bold green]\n")
            return selected_device.serial
        
        # Create device selection table for multiple devices
        table = Table(title="Available Android Devices")
        table.add_column("#", style="cyan", no_wrap=True)
        table.add_column("Serial", style="magenta")
        table.add_column("State", style="green")
        
        for idx, device in enumerate(android_devices, 1):
            table.add_row(str(idx), device.serial, "online" if device.serial else "unknown")
        
        console.print(table)
        console.print()
        
        # Add quit option
        choices = [str(i) for i in range(1, len(android_devices) + 1)] + ['q']
        choice = Prompt.ask(
            "Select device number (or 'q' to quit)",
            choices=choices,
            default="1"
        )
        
        if choice.lower() == 'q':
            return None
        
        selected_device = android_devices[int(choice) - 1]
        console.print(f"[bold green]✓ Selected device: {selected_device.serial}[/bold green]\n")
        return selected_device.serial
    
    def load_llm_profiles(self) -> Dict[str, Any]:
        """Load LLM profiles from JSON file"""
        if not os.path.exists(self.llm_profiles_path):
            return {}
        
        try:
            with open(self.llm_profiles_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[bold red]❌ Error loading LLM profiles: {e}[/bold red]")
            return {}
    
    def save_llm_profiles(self, profiles: Dict[str, Any]):
        """Save LLM profiles to JSON file"""
        try:
            with open(self.llm_profiles_path, 'w', encoding='utf-8') as f:
                json.dump(profiles, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[bold red]❌ Error saving LLM profiles: {e}[/bold red]")
    
    def create_new_llm_profile(self) -> Optional[Dict[str, Any]]:
        """Create a new LLM profile interactively"""
        console.print("[bold yellow]🤖 Creating New LLM Profile...[/bold yellow]\n")
        
        # Provider selection
        providers = {
            '1': 'openai',
            '2': 'google',
            '3': 'anthropic',
            '4': 'azure',
            '5': 'aws_bedrock',
            '6': 'aws_anthropic',
            'q': 'quit'
        }
        
        console.print("[bold cyan]Available Providers:[/bold cyan]")
        console.print("1. OpenAI or OpenAI Compatible")
        console.print("2. Google (Gemini models)")
        console.print("3. Anthropic (Claude models)")
        console.print("4. Azure OpenAI")
        console.print("5. AWS Bedrock")
        console.print("6. AWS Bedrock Anthropic")
        console.print("q. Quit\n")
        
        provider_choice = Prompt.ask(
            "Select provider",
            choices=list(providers.keys()),
            default="1"
        )
        
        if provider_choice == 'q':
            return None
        
        provider = providers[provider_choice]
        profile = {'provider': provider}
        
        # Profile name
        profile_name = Prompt.ask("Enter profile name", default=f"{provider}_{time.time()}")
        
        # Common fields based on provider
        profile['use_vision'] = Confirm.ask("Suppport Vision?", default=True)

        if provider == 'openai':
            profile['model_name'] = Prompt.ask("Model name")
            profile['api_key'] = Prompt.ask("API Key", password=True)
            base_url = Prompt.ask("Base URL (optional, press Enter to skip)", default="")
            if base_url:
                profile['base_url'] = base_url
        
        elif provider == 'google':
            profile['model_name'] = Prompt.ask("Model name")
            profile['api_key'] = Prompt.ask("API Key", password=True)
            base_url = Prompt.ask("Base URL (optional, press Enter to skip)", default="")
            if base_url:
                # For Google, base_url goes into http_options
                profile['http_options'] = {'base_url': base_url}
        
        elif provider == 'anthropic':
            profile['model_name'] = Prompt.ask("Model name")
            profile['api_key'] = Prompt.ask("API Key", password=True)
            base_url = Prompt.ask("Base URL (optional, press Enter to skip)", default="")
            if base_url:
                profile['base_url'] = base_url
        
        elif provider == 'azure':
            profile['model_name'] = Prompt.ask("Model/Deployment name")
            profile['api_key'] = Prompt.ask("API Key", password=True)
            profile['azure_endpoint'] = Prompt.ask("Azure Endpoint")
            profile['api_version'] = "2025-01-01-preview"
        
        elif provider == 'aws_bedrock':
            profile['model_name'] = Prompt.ask("Model ID")
            profile['aws_access_key_id'] = Prompt.ask("AWS Access Key ID")
            profile['aws_secret_access_key'] = Prompt.ask("AWS Secret Access Key", password=True)
            session_token = Prompt.ask("AWS Session Token (optional, press Enter to skip)", default="")
            if session_token:
                profile['aws_session_token'] = session_token
            profile['aws_region'] = Prompt.ask("AWS Region", default="us-east-1")
        
        elif provider == 'aws_anthropic':
            profile['model_name'] = Prompt.ask("Model ID")
            profile['aws_access_key'] = Prompt.ask("AWS Access Key ID")
            profile['aws_secret_key'] = Prompt.ask("AWS Secret Access Key", password=True)
            session_token = Prompt.ask("AWS Session Token (optional, press Enter to skip)", default="")
            if session_token:
                profile['aws_session_token'] = session_token
            profile['aws_region'] = Prompt.ask("AWS Region", default="us-east-1")
        
        # Encrypt sensitive fields
        if 'api_key' in profile:
            profile['api_key'] = encrypt_api_key(profile['api_key'])
        if 'aws_secret_access_key' in profile:
            profile['aws_secret_access_key'] = encrypt_api_key(profile['aws_secret_access_key'])
        if 'aws_secret_key' in profile:
            profile['aws_secret_key'] = encrypt_api_key(profile['aws_secret_key'])
        if 'aws_session_token' in profile:
            profile['aws_session_token'] = encrypt_api_key(profile['aws_session_token'])
        
        console.print(f"[bold green]✓ Profile '{profile_name}' created successfully![/bold green]\n")
        return {profile_name: profile}
    
    def select_llm_profile(self) -> Optional[Dict[str, Any]]:
        """Select or create an LLM profile"""
        console.print("[bold yellow]🤖 Selecting LLM Profile...[/bold yellow]\n")
        
        profiles = self.load_llm_profiles()
        
        if not profiles:
            console.print("[yellow]No existing LLM profiles found.[/yellow]")
            if Confirm.ask("Create a new profile?", default=True):
                new_profile = self.create_new_llm_profile()
                if new_profile:
                    profiles.update(new_profile)
                    self.save_llm_profiles(profiles)
                    return new_profile
            return None
        
        # Display existing profiles
        table = Table(title="Available LLM Profiles")
        table.add_column("#", style="cyan", no_wrap=True)
        table.add_column("Profile Name", style="magenta")
        table.add_column("Provider", style="green")
        table.add_column("Model", style="yellow")
        
        profile_list = list(profiles.items())
        for idx, (name, config) in enumerate(profile_list, 1):
            table.add_row(
                str(idx),
                name,
                config.get('provider', 'unknown'),
                config.get('model_name', 'N/A')
            )
        
        console.print(table)
        console.print()
        
        # Selection options
        choices = [str(i) for i in range(1, len(profile_list) + 1)] + ['n', 'q']
        console.print("[cyan]Options: [1-{}] Select profile | n: New profile | q: Quit[/cyan]".format(len(profile_list)))
        
        choice = Prompt.ask("Your choice", choices=choices, default="1")
        
        if choice == 'q':
            return None
        elif choice == 'n':
            new_profile = self.create_new_llm_profile()
            if new_profile:
                profiles.update(new_profile)
                self.save_llm_profiles(profiles)
                return new_profile
            return None
        else:
            profile_name = profile_list[int(choice) - 1][0]
            selected_profile = {profile_name: profiles[profile_name]}
            console.print(f"[bold green]✓ Selected profile: {profile_name}[/bold green]\n")
            return selected_profile
    
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
                console.print(f"[bold red]❌ Unsupported provider: {provider}[/bold red]")
                return None
        except Exception as e:
            console.print(f"[bold red]❌ Error creating LLM: {e}[/bold red]")
            return None
    
    def get_task_from_user(self) -> Optional[str]:
        """Get task description from user"""
        console.print("[bold yellow]📝 Enter Task Description[/bold yellow]\n")
        console.print("[dim]Describe what you want the agent to do on the Android device.[/dim]")
        console.print("[dim]Type 'q' to quit.[/dim]\n")
        
        task = Prompt.ask("Task")
        
        if task.lower() == 'q':
            return None
        
        if not task.strip():
            console.print("[bold red]❌ Task cannot be empty![/bold red]")
            return self.get_task_from_user()
        
        return task
    
    def show_controls_help(self):
        """Display keyboard controls help"""
        console.print("\n[bold yellow]⌨️  During Execution - Keyboard Controls:[/bold yellow]")
        console.print("  [cyan]p + enter[/cyan] - Pause agent")
        console.print("  [cyan]r + enter[/cyan] - Resume agent")
        console.print("  [cyan]s + enter[/cyan] - Stop current task")
        console.print()
    
    async def monitor_agent_and_keyboard(self, agent_task: asyncio.Task):
        """Monitor agent execution and handle keyboard input"""
        self.keyboard_listener_active = True
        
        def get_keyboard_input():
            """Get keyboard input in a thread-safe way"""
            try:
                return input()
            except EOFError:
                return None
        
        async def keyboard_handler():
            """Handle keyboard input asynchronously"""
            loop = asyncio.get_event_loop()
            while self.keyboard_listener_active and not agent_task.done():
                try:
                    # Run input in executor to avoid blocking
                    key = await loop.run_in_executor(None, get_keyboard_input)
                    if key is None:
                        break
                    
                    if not self.agent:
                        continue
                    
                    if key.lower() == 'p':
                        console.print("[yellow]⏸️  Pausing agent...[/yellow]")
                        self.agent.pause()
                    elif key.lower() == 'r':
                        console.print("[green]▶️  Resuming agent...[/green]")
                        self.agent.resume()
                    elif key.lower() == 's':
                        console.print("[red]⏹️  Stopping agent...[/red]")
                        self.agent.stop()
                        break
                except Exception as e:
                    console.print(f"[red]Error in keyboard handler: {e}[/red]")
                    break
        
        # Start keyboard handler
        keyboard_task = asyncio.create_task(keyboard_handler())
        
        # Wait for either agent or keyboard handler to finish
        done, pending = await asyncio.wait(
            [agent_task, keyboard_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel the other task
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self.keyboard_listener_active = False
    
    async def execute_task(self, task: str):
        """Execute a single task with the agent"""
        gif_path = None
        try:
            # Setup agent output directory
            timestamp = time.time()
            gif_path = os.path.join(self.outputs_dir, f"agent_history-{timestamp}.gif")
            
            # Update agent settings for this task
            self.agent.agent_settings.generate_gif = gif_path
            
            console.print(f"[bold green]🚀 Starting task execution...[/bold green]\n")
            self.show_controls_help()
            
            # Create agent task
            agent_task = asyncio.create_task(self.agent.run(task))
            
            # Monitor agent and keyboard input
            await self.monitor_agent_and_keyboard(agent_task)
            
            # Get result if task completed
            if agent_task.done():
                # Check if task was cancelled (e.g., by pressing 's' to stop)
                if agent_task.cancelled():
                    console.print("[yellow]⏹️  Task stopped by user[/yellow]")
                    
                    # Print GIF path even when stopped
                    if gif_path and os.path.exists(gif_path):
                        console.print(f"[bold cyan]📹 GIF saved to: {gif_path}[/bold cyan]\n")
                    
                    return False
                
                try:
                    result = agent_task.result()
                    console.print(f"\n[bold green]✓ Task completed![/bold green]")
                    console.print(f"[cyan]Total duration: {result.total_duration_seconds():.2f}s[/cyan]")
                    
                    # Always print GIF path
                    if gif_path and os.path.exists(gif_path):
                        console.print(f"[bold cyan]📹 GIF saved to: {gif_path}[/bold cyan]\n")
                    
                    return True
                except asyncio.CancelledError:
                    # Handle the case where task was cancelled during result retrieval
                    console.print("[yellow]⏹️  Task stopped by user[/yellow]")
                    
                    # Print GIF path even when stopped
                    if gif_path and os.path.exists(gif_path):
                        console.print(f"[bold cyan]📹 GIF saved to: {gif_path}[/bold cyan]\n")
                    
                    return False
                except Exception as e:
                    console.print(f"[bold red]❌ Task error: {e}[/bold red]")
                    import traceback
                    console.print(traceback.format_exc())
                    
                    # Print GIF path even on error
                    if gif_path and os.path.exists(gif_path):
                        console.print(f"[bold cyan]📹 GIF saved to: {gif_path}[/bold cyan]\n")
                    
                    return False
            else:
                console.print("[yellow]⏹️  Task stopped by user[/yellow]")
                
                # Print GIF path even when stopped
                if gif_path and os.path.exists(gif_path):
                    console.print(f"[bold cyan]📹 GIF saved to: {gif_path}[/bold cyan]\n")
                
                return False
            
        except Exception as e:
            console.print(f"[bold red]❌ Error executing task: {e}[/bold red]")
            import traceback
            console.print(traceback.format_exc())
            
            # Print GIF path even on exception
            if gif_path and os.path.exists(gif_path):
                console.print(f"[bold cyan]📹 GIF saved to: {gif_path}[/bold cyan]\n")
            
            return False
    
    async def task_loop(self):
        """Interactive loop for executing multiple tasks"""
        while True:
            console.print("\n" + "="*60)
            console.print("[bold cyan]📋 Task Menu[/bold cyan]")
            console.print("="*60)
            console.print("1. Execute new task")
            console.print("2. Clear message history")
            console.print("3. Change device")
            console.print("4. Change LLM profile")
            console.print("q. Quit")
            console.print()
            
            choice = Prompt.ask(
                "Select option",
                choices=['1', '2', '3', '4', 'q'],
                default='1'
            )

            if choice == 'q':
                console.print("[yellow]👋 Exiting...[/yellow]")
                break
            
            elif choice == '1':
                task = self.get_task_from_user()
                if task is None:
                    # User chose to quit from task input
                    console.print("[yellow]👋 Exiting...[/yellow]")
                    break
                
                await self.execute_task(task)
            
            elif choice == '2':
                if self.agent and hasattr(self.agent, 'message_manager'):
                    self.agent.message_manager.clear_message_history()
                    console.print("[green]✓ Message history cleared[/green]")
                else:
                    console.print("[yellow]No agent initialized yet[/yellow]")
            
            elif choice == '3':
                return 'change_device'
            
            elif choice == '4':
                return 'change_llm'
            
            else:
                console.print(f"[dim]DEBUG: No branch matched! choice='{choice}'[/dim]")
        
        return 'quit'
    
    async def main_loop(self):
        """Main CLI loop"""
        self.show_logo()
        
        while True:
            # Step 1: Select device
            device_id = self.select_device()
            if not device_id:
                console.print("[yellow]👋 Goodbye![/yellow]")
                return
            
            # Step 2: Select LLM profile
            selected_profile = self.select_llm_profile()
            if not selected_profile:
                console.print("[yellow]👋 Goodbye![/yellow]")
                return
            
            profile_name, profile_config = list(selected_profile.items())[0]
            llm = self.create_llm_from_profile(profile_name, profile_config)
            if not llm:
                console.print("[bold red]❌ Failed to create LLM instance![/bold red]")
                return
            
            # Step 3: Initialize Android context and agent (reusable across tasks)
            try:
                config = AndroidContextConfig(
                    highlight_elements=True,
                    device_id=device_id
                )
                android_context = AndroidContext(config)
                
                # Create agent settings
                agent_settings = AgentSettings(
                    generate_gif="",  # Will be set per task
                    use_vision=profile_config.get('use_vision', True),
                )
                
                # Create agent (persistent across tasks)
                self.agent = AndroidUseAgent(
                    agent_settings=agent_settings,
                    llm=llm,
                    android_context=android_context
                )
                
                console.print(f"[bold green]✓ Agent initialized with device: {device_id}[/bold green]")
                console.print(f"[bold green]✓ Using LLM profile: {profile_name}[/bold green]\n")
                
            except Exception as e:
                console.print(f"[bold red]❌ Error initializing agent: {e}[/bold red]")
                import traceback
                console.print(traceback.format_exc())
                return
            
            # Step 4: Enter task loop
            result = await self.task_loop()
            
            if result == 'quit':
                console.print("[bold green]✓ Session completed![/bold green]")
                break
            elif result == 'change_device':
                # Reinitialize with new device
                self.agent = None
                continue
            elif result == 'change_llm':
                # Reinitialize with new LLM
                self.agent = None
                continue


def main():
    """Entry point for the CLI"""
    # Check if webui mode is requested
    if len(sys.argv) > 1 and sys.argv[1] == "webui":
        from android_use import app
        # Remove 'webui' from arguments so it doesn't interfere with app's argument parsing
        sys.argv.pop(1)
        app.main()
        return

    try:
        cli = AndroidUseCLI()
        asyncio.run(cli.main_loop())
    except KeyboardInterrupt:
        console.print("\n[yellow]👋 Interrupted by user. Goodbye![/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]❌ Fatal error: {e}[/bold red]")
        import traceback
        console.print(traceback.format_exc())


if __name__ == '__main__':
    main()