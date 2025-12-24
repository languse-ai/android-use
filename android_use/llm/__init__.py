"""
We have switched all of our code from langchain to openai.types.chat.chat_completion_message_param.

For easier transition we have
"""

from typing import TYPE_CHECKING

# Lightweight imports that are commonly used
from android_use.llm.base import BaseChatModel
from android_use.llm.messages import (
	AssistantMessage,
	BaseMessage,
	SystemMessage,
	UserMessage,
)
from android_use.llm.messages import (
	ContentPartImageParam as ContentImage,
)
from android_use.llm.messages import (
	ContentPartRefusalParam as ContentRefusal,
)
from android_use.llm.messages import (
	ContentPartTextParam as ContentText,
)

# Type stubs for lazy imports
if TYPE_CHECKING:
	from android_use.llm.anthropic.chat import ChatAnthropic
	from android_use.llm.aws.chat_anthropic import ChatAnthropicBedrock
	from android_use.llm.aws.chat_bedrock import ChatAWSBedrock
	from android_use.llm.azure.chat import ChatAzureOpenAI
	from android_use.llm.cerebras.chat import ChatCerebras
	from android_use.llm.deepseek.chat import ChatDeepSeek
	from android_use.llm.google.chat import ChatGoogle
	from android_use.llm.groq.chat import ChatGroq
	from android_use.llm.mistral.chat import ChatMistral
	from android_use.llm.oci_raw.chat import ChatOCIRaw
	from android_use.llm.ollama.chat import ChatOllama
	from android_use.llm.openai.chat import ChatOpenAI
	from android_use.llm.openrouter.chat import ChatOpenRouter
	from android_use.llm.vercel.chat import ChatVercel
	from android_use.llm.openai_compatible.chat import ChatOpenAICompatible

	# Type stubs for model instances - enables IDE autocomplete
	openai_gpt_4o: ChatOpenAI
	openai_gpt_4o_mini: ChatOpenAI
	openai_gpt_4_1_mini: ChatOpenAI
	openai_o1: ChatOpenAI
	openai_o1_mini: ChatOpenAI
	openai_o1_pro: ChatOpenAI
	openai_o3: ChatOpenAI
	openai_o3_mini: ChatOpenAI
	openai_o3_pro: ChatOpenAI
	openai_o4_mini: ChatOpenAI
	openai_gpt_5: ChatOpenAI
	openai_gpt_5_mini: ChatOpenAI
	openai_gpt_5_nano: ChatOpenAI

	azure_gpt_4o: ChatAzureOpenAI
	azure_gpt_4o_mini: ChatAzureOpenAI
	azure_gpt_4_1_mini: ChatAzureOpenAI
	azure_o1: ChatAzureOpenAI
	azure_o1_mini: ChatAzureOpenAI
	azure_o1_pro: ChatAzureOpenAI
	azure_o3: ChatAzureOpenAI
	azure_o3_mini: ChatAzureOpenAI
	azure_o3_pro: ChatAzureOpenAI
	azure_gpt_5: ChatAzureOpenAI
	azure_gpt_5_mini: ChatAzureOpenAI

	google_gemini_2_0_flash: ChatGoogle
	google_gemini_2_0_pro: ChatGoogle
	google_gemini_2_5_pro: ChatGoogle
	google_gemini_2_5_flash: ChatGoogle
	google_gemini_2_5_flash_lite: ChatGoogle

# Models are imported on-demand via __getattr__

# Lazy imports mapping for heavy chat models
_LAZY_IMPORTS = {
	'ChatAnthropic': ('android_use.llm.anthropic.chat', 'ChatAnthropic'),
	'ChatAnthropicBedrock': ('android_use.llm.aws.chat_anthropic', 'ChatAnthropicBedrock'),
	'ChatAWSBedrock': ('android_use.llm.aws.chat_bedrock', 'ChatAWSBedrock'),
	'ChatAzureOpenAI': ('android_use.llm.azure.chat', 'ChatAzureOpenAI'),
	'ChatCerebras': ('android_use.llm.cerebras.chat', 'ChatCerebras'),
	'ChatDeepSeek': ('android_use.llm.deepseek.chat', 'ChatDeepSeek'),
	'ChatGoogle': ('android_use.llm.google.chat', 'ChatGoogle'),
	'ChatGroq': ('android_use.llm.groq.chat', 'ChatGroq'),
	'ChatMistral': ('android_use.llm.mistral.chat', 'ChatMistral'),
	'ChatOCIRaw': ('android_use.llm.oci_raw.chat', 'ChatOCIRaw'),
	'ChatOllama': ('android_use.llm.ollama.chat', 'ChatOllama'),
	'ChatOpenAI': ('android_use.llm.openai.chat', 'ChatOpenAI'),
	'ChatOpenRouter': ('android_use.llm.openrouter.chat', 'ChatOpenRouter'),
	'ChatVercel': ('android_use.llm.vercel.chat', 'ChatVercel'),
}

# Cache for model instances - only created when accessed
_model_cache: dict[str, 'BaseChatModel'] = {}


def __getattr__(name: str):
	"""Lazy import mechanism for heavy chat model imports and model instances."""
	if name in _LAZY_IMPORTS:
		module_path, attr_name = _LAZY_IMPORTS[name]
		try:
			from importlib import import_module

			module = import_module(module_path)
			attr = getattr(module, attr_name)
			return attr
		except ImportError as e:
			raise ImportError(f'Failed to import {name} from {module_path}: {e}') from e

	# Check cache first for model instances
	if name in _model_cache:
		return _model_cache[name]

	# Try to get model instances from models module on-demand
	try:
		from android_use.llm.models import __getattr__ as models_getattr

		attr = models_getattr(name)
		# Cache in our clean cache dict
		_model_cache[name] = attr
		return attr
	except (AttributeError, ImportError):
		pass

	raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
	# Message types -> for easier transition from langchain
	'BaseMessage',
	'UserMessage',
	'SystemMessage',
	'AssistantMessage',
	# Content parts with better names
	'ContentText',
	'ContentRefusal',
	'ContentImage',
	# Chat models
	'BaseChatModel',
	'ChatOpenAI',
	'ChatDeepSeek',
	'ChatGoogle',
	'ChatAnthropic',
	'ChatAnthropicBedrock',
	'ChatAWSBedrock',
	'ChatGroq',
	'ChatMistral',
	'ChatAzureOpenAI',
	'ChatOCIRaw',
	'ChatOllama',
	'ChatOpenRouter',
	'ChatVercel',
	'ChatCerebras',
	'ChatOpenAICompatible'
]
