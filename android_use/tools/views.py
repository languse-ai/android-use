import enum
import logging
from typing import Dict, Any, Optional, Type, TypeVar, Generic, List, Literal, Tuple  # Added Literal, Tuple

from pydantic import BaseModel, Field


class DoneAction(BaseModel):
    text: str
    success: bool


class ClickElementAction(BaseModel):
    """Params: Click an element by its index or coordinates."""
    index: Optional[int] = Field(None, description="Index of the element to click.")
    x: Optional[float] = Field(None, description="Optional x coordinate.")
    y: Optional[float] = Field(None, description="Optional y coordinate.")


class LongPressElementAction(BaseModel):
    """Params: Long-press an element by its index or coordinates."""
    index: Optional[int] = Field(None, description="Index of the element to long-press.")
    x: Optional[float] = Field(None, description="Optional x coordinate.")
    y: Optional[float] = Field(None, description="Optional y coordinate.")
    duration: Optional[float] = Field(2.0, description="Duration of the long press in seconds.")


class InputTextAction(BaseModel):
    """Params: Input text, optionally clicking an element first."""
    text: str = Field(..., description="The text to type.")
    # Index is now optional, default is None
    index: Optional[int] = Field(None, description="Index of the element (e.g., input field) to click before typing.")
    x: Optional[float] = Field(None, description="Optional x coordinate.")
    y: Optional[float] = Field(None, description="Optional y coordinate.")
    # Clear has a default value
    clear: Optional[bool] = Field(False, description="Whether to clear the field before typing.")


class SwipeAction(BaseModel):
    """Params: Swipe screen using coordinates."""
    x1: float = Field(..., description="Start x coordinate.")
    y1: float = Field(..., description="Start y coordinate.")
    x2: float = Field(..., description="End x coordinate.")
    y2: float = Field(..., description="End y coordinate.")


class PressKeyAction(BaseModel):
    """Params: Press a system key."""
    # Keys limited by Literal
    key: Literal["home", "back", "recent"] = Field(..., description="Name of the system key to press.")


class ShellCommandAction(BaseModel):
    """Params: Execute an ADB shell command."""
    command: str = Field(..., description="The shell command string to execute.")


class PushFileAction(BaseModel):
    """Params: Upload a local file to the device."""
    local_path: str = Field(..., description="Local file path.")
    device_path: str = Field(..., description="Destination path on device.")


class PullFileAction(BaseModel):
    """Params: Download a file from the device."""
    device_path: str = Field(..., description="File path on device.")
    local_path: str = Field(..., description="Local destination path.")


class DragAction(BaseModel):
    """Params: Drag from one element's center to another's center or use coordinates."""
    start_index: Optional[int] = Field(None, description="Index of the element to start dragging from.")
    end_index: Optional[int] = Field(None, description="Index of the element to drag to.")
    x1: Optional[float] = Field(None, description="Optional start x coordinate.")
    y1: Optional[float] = Field(None, description="Optional start y coordinate.")
    x2: Optional[float] = Field(None, description="Optional end x coordinate.")
    y2: Optional[float] = Field(None, description="Optional end y coordinate.")
    duration: Optional[float] = Field(2.0, description="Duration of the drag in seconds.")


class LaunchAppAction(BaseModel):
    """Params: Launch an app by name."""
    app_name: str = Field(..., description="Name of the app to launch (must be in supported apps list).")


class RecordImportantContentAction(BaseModel):
    """Params: Record important content from the screen."""
    content: str = Field(..., description="The important content to record.")


class GenerateOrUpdateTodosAction(BaseModel):
    """Params: Generate or update a markdown-formatted TODO list to track task progress."""
    todos: str = Field(
        ...,
        description='Generate or update a markdown-formatted TODO list to track task progress. Use at task start to plan, then update as you complete sub-tasks or encounter new situations.',
    )
