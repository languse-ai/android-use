"""
Action highlighting module for visualizing actions on screenshots.
This module provides functions to draw visual indicators for different action types.
"""

import base64
import io
import logging
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from android_use import utils

logger = logging.getLogger(__name__)


def draw_circle(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    radius: int = 40,
    color: Tuple[int, int, int] = (255, 0, 0),
    width: int = 8
) -> None:
    """
    Draw a circle at the specified coordinates.
    
    Args:
        draw: ImageDraw object
        x: X coordinate
        y: Y coordinate
        radius: Circle radius
        color: RGB color tuple
        width: Line width
    """
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        outline=color,
        width=width
    )


def draw_cross(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    size: int = 35,
    color: Tuple[int, int, int] = (255, 0, 0),
    width: int = 8
) -> None:
    """
    Draw an X (cross) at the specified coordinates.
    
    Args:
        draw: ImageDraw object
        x: X coordinate
        y: Y coordinate
        size: Cross size
        color: RGB color tuple
        width: Line width
    """
    # Draw two diagonal lines forming an X
    draw.line([x - size, y - size, x + size, y + size], fill=color, width=width)
    draw.line([x - size, y + size, x + size, y - size], fill=color, width=width)


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: Tuple[int, int, int] = (0, 255, 0),
    width: int = 8,
    arrow_size: int = 30
) -> None:
    """
    Draw an arrow from (x1, y1) to (x2, y2).
    
    Args:
        draw: ImageDraw object
        x1: Start X coordinate
        y1: Start Y coordinate
        x2: End X coordinate
        y2: End Y coordinate
        color: RGB color tuple
        width: Line width
        arrow_size: Size of arrow head
    """
    import math
    
    # Draw the main line
    draw.line([x1, y1, x2, y2], fill=color, width=width)
    
    # Calculate angle of the line
    angle = math.atan2(y2 - y1, x2 - x1)
    
    # Draw arrow head (two lines forming a V)
    arrow_angle = math.pi / 6  # 30 degrees
    
    # Left side of arrow
    left_x = x2 - arrow_size * math.cos(angle - arrow_angle)
    left_y = y2 - arrow_size * math.sin(angle - arrow_angle)
    draw.line([x2, y2, left_x, left_y], fill=color, width=width)
    
    # Right side of arrow
    right_x = x2 - arrow_size * math.cos(angle + arrow_angle)
    right_y = y2 - arrow_size * math.sin(angle + arrow_angle)
    draw.line([x2, y2, right_x, right_y], fill=color, width=width)


def draw_text_center(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    text: str,
    font_size: int = 40,
    color: Tuple[int, int, int] = (255, 255, 0),
    bg_color: Tuple[int, int, int, int] = (0, 0, 0, 200)
) -> None:
    """
    Draw text in the center of the image with background.
    
    Args:
        draw: ImageDraw object
        image: PIL Image object
        text: Text to draw
        font_size: Font size
        color: Text color RGB tuple
        bg_color: Background color RGBA tuple (with alpha for transparency)
    """
    # Get or create font
    font = utils.get_font(font_size)
    
    # Get text bounding box
    if hasattr(font, 'getbbox'):
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        # Fallback for older PIL versions
        text_width, text_height = font.getsize(text)
    
    # Calculate center position
    x = (image.width - text_width) // 2
    y = (image.height - text_height) // 2
    
    # Draw semi-transparent background rectangle
    padding = 20
    bg_bbox = [
        x - padding,
        y - padding,
        x + text_width + padding,
        y + text_height + padding
    ]
    
    # Create a temporary image for the background with alpha
    tmp = Image.new('RGBA', image.size, (0, 0, 0, 0))
    tmp_draw = ImageDraw.Draw(tmp)
    tmp_draw.rounded_rectangle(bg_bbox, radius=10, fill=bg_color)
    
    # Composite the background onto the main image
    image.paste(tmp, (0, 0), tmp)
    
    # Draw text on top
    draw.text((x, y), text, font=font, fill=color)


def highlight_tap_action(
    screenshot_base64: str,
    x: float,
    y: float
) -> str:
    """
    Highlight a tap action with a red X.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        x: X coordinate
        y: Y coordinate
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw red X
        draw_cross(draw, x, y, size=35, color=(255, 0, 0), width=8)
        
        return utils.pil_image_to_base64(image, "PNG")
    except Exception as e:
        logger.error(f"Error highlighting tap action: {e}")
        return screenshot_base64


def highlight_input_text_action(
    screenshot_base64: str,
    x: float,
    y: float
) -> str:
    """
    Highlight an input_text action with a green circle.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        x: X coordinate
        y: Y coordinate
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw green circle
        draw_circle(draw, x, y, radius=40, color=(0, 255, 0), width=8)
        
        return utils.pil_image_to_base64(image, "PNG")
    except Exception as e:
        logger.error(f"Error highlighting input_text action: {e}")
        return screenshot_base64


def highlight_long_press_action(
    screenshot_base64: str,
    x: float,
    y: float
) -> str:
    """
    Highlight a long_press action with a purple circle and X.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        x: X coordinate
        y: Y coordinate
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw purple circle with X inside
        color = (128, 0, 128)  # Purple
        draw_circle(draw, x, y, radius=40, color=color, width=8)
        draw_cross(draw, x, y, size=30, color=color, width=8)
        
        return utils.pil_image_to_base64(image, "PNG")
    except Exception as e:
        logger.error(f"Error highlighting long_press action: {e}")
        return screenshot_base64


def highlight_swipe_action(
    screenshot_base64: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float
) -> str:
    """
    Highlight a swipe action with a yellow arrow.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        x1: Start X coordinate
        y1: Start Y coordinate
        x2: End X coordinate
        y2: End Y coordinate
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw yellow arrow
        draw_arrow(draw, x1, y1, x2, y2, color=(255, 255, 0), width=8, arrow_size=40)
        
        return utils.pil_image_to_base64(image, "PNG")
    except Exception as e:
        logger.error(f"Error highlighting swipe action: {e}")
        return screenshot_base64


def highlight_drag_action(
    screenshot_base64: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float
) -> str:
    """
    Highlight a drag action with a cyan arrow.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        x1: Start X coordinate
        y1: Start Y coordinate
        x2: End X coordinate
        y2: End Y coordinate
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw cyan arrow
        draw_arrow(draw, x1, y1, x2, y2, color=(0, 255, 255), width=8, arrow_size=40)
        
        return utils.pil_image_to_base64(image, "PNG")
    except Exception as e:
        logger.error(f"Error highlighting drag action: {e}")
        return screenshot_base64


def highlight_press_key_action(
    screenshot_base64: str,
    key: str
) -> str:
    """
    Highlight a press_key action with text in the center.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        key: Key name
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        image = image.convert('RGBA')
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw text in center
        text = f"Press: {key}"
        draw_text_center(draw, image, text, font_size=60, color=(255, 255, 0))
        
        return utils.pil_image_to_base64(image.convert('RGB'), "PNG")
    except Exception as e:
        logger.error(f"Error highlighting press_key action: {e}")
        return screenshot_base64


def highlight_shell_command_action(
    screenshot_base64: str,
    command: str
) -> str:
    """
    Highlight a shell command action with text in the center.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        command: Shell command (truncated if too long)
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        image = image.convert('RGBA')
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Truncate command if too long
        max_length = 50
        if len(command) > max_length:
            display_command = command[:max_length] + "..."
        else:
            display_command = command
        
        # Draw text in center
        text = f"Shell: {display_command}"
        draw_text_center(draw, image, text, font_size=50, color=(255, 255, 0))
        
        return utils.pil_image_to_base64(image.convert('RGB'), "PNG")
    except Exception as e:
        logger.error(f"Error highlighting shell_command action: {e}")
        return screenshot_base64


def highlight_launch_app_action(
    screenshot_base64: str,
    app_name: str
) -> str:
    """
    Highlight a launch_app action with text in the center.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        app_name: App name
    
    Returns:
        Base64 encoded screenshot with highlight
    """
    try:
        image = utils.base64_to_pil_image(screenshot_base64)
        image = image.convert('RGBA')
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw text in center with Chinese
        text = f"启动应用: {app_name}"
        draw_text_center(draw, image, text, font_size=60, color=(255, 255, 0))
        
        return utils.pil_image_to_base64(image.convert('RGB'), "PNG")
    except Exception as e:
        logger.error(f"Error highlighting launch_app action: {e}")
        return screenshot_base64