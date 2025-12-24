from __future__ import annotations

import logging
import pdb
from typing import List, Optional, Dict

from pydantic import BaseModel, Field
from android_use.llm.messages import (
    AssistantMessage,
    BaseMessage,
    ContentPartImageParam,
    ContentPartTextParam,
    Function,
    ImageURL,
    SystemMessage,
    ToolCall,
    UserMessage
)

logger = logging.getLogger(__name__)


class MessageHistory(BaseModel):
    """Container for message history"""

    messages: List[BaseMessage] = Field(default_factory=list)

    def add_message(self, message: BaseMessage, position: Optional[int] = None) -> None:
        """Add a message"""
        if position is None:
            self.messages.append(message)
        else:
            self.messages.insert(position, message)

    def remove_message(self, index: int = -1) -> None:
        """Remove message from history"""
        if self.messages:
            self.messages.pop(index)


class MessageManagerSettings(BaseModel):
    include_attributes: list[str] = Field(default_factory=list)
    message_context: Optional[str] = None
    sensitive_data: Optional[Dict[str, str]] = None
    available_file_paths: Optional[List[str]] = None
    max_state_messages: int = 1  # Maximum number of state messages (with images) to keep
    vision_detail_level: str = "auto"  # Vision detail level for images: "low", "high", or "auto"


class MessageManager:
    def __init__(
            self,
            settings: MessageManagerSettings = MessageManagerSettings(),
            message_history: MessageHistory = None,
    ):
        self.settings = settings
        if message_history is None:
            self.message_history = MessageHistory()
        else:
            self.message_history = message_history

    def clear_message_history(self):
        self.message_history.messages = []

    def get_messages(self) -> List[BaseMessage]:
        """Get current message list"""
        return self.message_history.messages

    def add_message(self, message: BaseMessage, position: int | None = None) -> None:
        """Add message to history
        position: None for last, -1 for second last, etc.
        """
        # filter out sensitive data from the message
        if self.settings.sensitive_data:
            message = self._filter_sensitive_data(message)

        self.message_history.add_message(message, position)

    def create_message(self, role: str = "user", text: str = "", images: List[str] = None,
                       image_format: str = "png") -> BaseMessage:
        """Create a message from raw inputs"""
        # Build content parts
        content_parts = []

        if text:
            content_parts.append(ContentPartTextParam(text=text))

        if images:
            for image in images:
                # Determine media type based on image format
                if image_format == "png":
                    media_type = "image/png"
                elif image_format == "jpeg" or image_format == "jpg":
                    media_type = "image/jpeg"
                elif image_format == "webp":
                    media_type = "image/webp"
                elif image_format == "gif":
                    media_type = "image/gif"
                else:
                    media_type = "image/png"  # default
                image_url = ImageURL(
                    url=f"data:{media_type};base64,{image}",
                    media_type=media_type,
                    detail=self.settings.vision_detail_level
                )
                content_parts.append(ContentPartImageParam(image_url=image_url))

        # For system messages, only text is allowed
        if role == "system":
            if images:
                logger.warning("System messages cannot contain images, ignoring images")
            message = SystemMessage(content=text if text else "")
        elif role == "assistant":
            message = AssistantMessage(content=text if text else "")
        else:
            # User message can have both text and images
            if len(content_parts) == 0:
                message = UserMessage(content="")
            elif len(content_parts) == 1 and isinstance(content_parts[0], ContentPartTextParam):
                message = UserMessage(content=text)
            else:
                message = UserMessage(content=content_parts)

        # filter out sensitive data from the message
        if self.settings.sensitive_data:
            message = self._filter_sensitive_data(message)

        return message

    def _filter_sensitive_data(self, message: BaseMessage) -> BaseMessage:
        """Filter out sensitive data from the message"""

        def replace_sensitive(value: str) -> str:
            if not self.settings.sensitive_data:
                return value

            # Collect all sensitive values, immediately converting old format to new format
            sensitive_values: dict[str, str] = {}

            # Process all sensitive data entries
            for key_or_domain, content in self.settings.sensitive_data.items():
                if isinstance(content, dict):
                    # Already in new format: {domain: {key: value}}
                    for key, val in content.items():
                        if val:  # Skip empty values
                            sensitive_values[key] = val
                elif content:  # Old format: {key: value} - convert to new format internally
                    # We treat this as if it was {'http*://*': {key_or_domain: content}}
                    sensitive_values[key_or_domain] = content

            # If there are no valid sensitive data entries, just return the original value
            if not sensitive_values:
                logger.warning('No valid entries found in sensitive_data dictionary')
                return value

            # Replace all valid sensitive data values with their placeholder tags
            for key, val in sensitive_values.items():
                value = value.replace(val, f'<secret>{key}</secret>')

            return value

        if isinstance(message.content, str):
            message.content = replace_sensitive(message.content)
        elif isinstance(message.content, list):
            for i, item in enumerate(message.content):
                if isinstance(item, ContentPartTextParam):
                    item.text = replace_sensitive(item.text)
                    message.content[i] = item
        return message

    def _remove_user_message_by_index(self, remove_ind=-1) -> None:
        """Remove state message by index from history"""
        i = len(self.message_history.messages) - 1
        remove_cnt = 0
        while i >= 0:
            if isinstance(self.message_history.messages[i].message, UserMessage):
                remove_cnt += 1
            if remove_cnt == abs(remove_ind):
                self.message_history.remove_message(i)
                break
            i -= 1

    def limit_state_messages(self):
        """Limit the number of state messages (UserMessage with images) to max_state_messages"""
        if self.settings.max_state_messages <= 0:
            return

        # Find all state messages (UserMessage with images)
        state_message_indices = []
        for i, message in enumerate(self.message_history.messages):
            if isinstance(message, UserMessage):
                # Check if message has images
                content = message.content
                if isinstance(content, list):
                    has_image = any(
                        isinstance(item, ContentPartImageParam)
                        for item in content
                    )
                    if has_image:
                        state_message_indices.append(i)
                elif "Current step:" in content:
                    state_message_indices.append(i)

        # If we have more state messages than allowed, remove the oldest ones
        num_to_remove = len(state_message_indices) - self.settings.max_state_messages
        if num_to_remove > 0:
            # Remove in reverse order to maintain indices
            for idx in reversed(state_message_indices[:num_to_remove]):
                self.message_history.remove_message(idx)
                logger.info(
                    f"Removed old state message at index {idx} to maintain max_state_messages={self.settings.max_state_messages}")
