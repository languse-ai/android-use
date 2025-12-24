import logging
import time
from functools import wraps
from typing import Any, Callable, Coroutine, ParamSpec, TypeVar
import base64
import io
from PIL import Image
import binascii
import os
import platform
from PIL import ImageDraw, ImageFont
import asyncio
import signal
from sys import stderr
from android_use.config import CONFIG

logger = logging.getLogger(__name__)

# Define generic type variables for return type and parameters
R = TypeVar('R')
P = ParamSpec('P')
T = TypeVar('T')


def time_execution_sync(additional_text: str = '') -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f'{additional_text} Execution time: {execution_time:.2f} seconds')
            return result

        return wrapper

    return decorator


def time_execution_async(
        additional_text: str = '',
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f'{additional_text} Execution time: {execution_time:.2f} seconds')
            return result

        return wrapper

    return decorator


def singleton(cls):
    instance = [None]

    def wrapper(*args, **kwargs):
        if instance[0] is None:
            instance[0] = cls(*args, **kwargs)
        return instance[0]

    return wrapper


def pil_image_to_base64(image: Image.Image, format: str = 'PNG') -> str:
    """
    Converts a PIL Image object to a Base64 encoded string.

    Args:
        image: The PIL.Image.Image object to convert.
        format: The image format to save as before encoding (e.g., 'PNG', 'JPEG').
                Defaults to 'PNG'. Note that JPEG does not support transparency.

    Returns:
        A Base64 encoded string representing the image.
    """
    # Create an in-memory bytes buffer
    buffer = io.BytesIO()

    # Handle potential format issues, like saving RGBA as JPEG
    img_to_save = image
    if format.upper() == 'JPEG' and image.mode == 'RGBA':
        # Convert RGBA to RGB for JPEG compatibility, as JPEG doesn't support alpha channel
        img_to_save = image.convert('RGB')

    # Save the image to the buffer in the specified format
    img_to_save.save(buffer, format=format)

    # Get the byte data from the buffer
    img_bytes = buffer.getvalue()

    # Encode the bytes using Base64
    base64_bytes = base64.b64encode(img_bytes)

    # Decode the Base64 bytes into a UTF-8 string for easier handling
    base64_string = base64_bytes.decode('utf-8')

    return base64_string


def base64_to_pil_image(base64_string: str) -> Image.Image:
    """
    Decodes a Base64 encoded string back into a PIL Image object.

    Args:
        base64_string: The Base64 encoded string representing the image.

    Returns:
        A PIL.Image.Image object.

    Raises:
        ValueError: If the input string is not valid Base64 or if the decoded
                    data cannot be identified as an image by PIL.
        binascii.Error: Specifically if Base64 decoding itself fails.
    """
    try:
        # Encode the string back to bytes, which base64 library expects
        base64_bytes = base64_string.encode('utf-8')

        # Decode the Base64 bytes to get the original image bytes
        img_bytes = base64.b64decode(base64_bytes)

        # Create an in-memory bytes buffer from the decoded image bytes
        buffer = io.BytesIO(img_bytes)

        # Open the image using PIL. It will automatically detect the format.
        image = Image.open(buffer)

        # It's crucial to copy the image data. Otherwise, the image object
        # might rely on the buffer, which could be closed or garbage collected later,
        # leading to errors when accessing image data (e.g., during save).
        return image.copy()

    except Exception as e:
        # Catch other potential errors during PIL processing
        raise ValueError(f"Failed to load image from Base64 string: {e}")


def save_base64_to_file(base64_string: str, output_filepath: str):
    """
    Decodes a Base64 string and saves the resulting raw bytes to a file.

    Args:
        base64_string: The Base64 encoded string.
        output_filepath: The full path (including filename and extension)
                         where the decoded data should be saved.

    Raises:
        ValueError: If the input string is not valid Base64.
        IOError: If there's an error writing to the specified file path
                 (e.g., permissions, invalid path).
        Exception: For other unexpected errors during the process.
    """
    try:
        # Decode the Base64 string to get the original bytes
        # First, ensure the input string is encoded to bytes (UTF-8 is common)
        base64_bytes = base64_string.encode('utf-8')
        # Perform the Base64 decoding
        decoded_bytes = base64.b64decode(base64_bytes)

    except binascii.Error as e:
        # Handle errors specifically related to invalid Base64 encoding
        raise ValueError(f"Invalid Base64 string provided: {e}")
    except Exception as e:
        # Catch any other potential errors during encoding/decoding setup
        raise ValueError(f"Error processing Base64 string before decoding: {e}")

    try:
        # Ensure the directory exists, create it if not
        output_dir = os.path.dirname(output_filepath)
        os.makedirs(output_dir, exist_ok=True)

        # Open the output file in binary write mode ('wb')
        # Using 'with' ensures the file is properly closed even if errors occur
        with open(output_filepath, 'wb') as f:
            # Write the decoded bytes to the file
            f.write(decoded_bytes)

        print(f"Successfully saved decoded data to: {output_filepath}")  # Optional: success message

    except IOError as e:
        # Handle file system errors (e.g., permission denied, path not found after check)
        raise IOError(f"Could not write to file '{output_filepath}': {e}")
    except Exception as e:
        # Catch any other unexpected errors during file writing
        raise Exception(f"An unexpected error occurred while saving the file: {e}")


def save_xml_to_file(xml: str, output_filepath: str):
    """
    Saves a XML string to a file.
    :param xml:
    :param output_filepath:
    :return:
    """
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
    with open(output_filepath, 'w', encoding="utf-8") as f:
        f.write(xml)


def get_font(font_size=10):
    """
    get font for drawing
    :param font_size:
    :return:
    """
    regular_font = None

    try:
        # Try different font options in order of preference
        # ArialUni is a font that comes with Office and can render most non-alphabet characters
        font_options = [
            'PingFang',
            'STHeiti Medium',
            'Microsoft YaHei',  # 微软雅黑
            'SimHei',  # 黑体
            'SimSun',  # 宋体
            'Noto Sans CJK SC',  # 思源黑体
            'WenQuanYi Micro Hei',  # 文泉驿微米黑
            'Helvetica',
            'Arial',
            'DejaVuSans',
            'Verdana',
        ]
        font_loaded = False

        for font_name in font_options:
            try:
                if platform.system() == 'Windows':
                    # Need to specify the abs font path on Windows
                    font_name = os.path.join(CONFIG.WIN_FONT_DIR, font_name + '.ttf')
                regular_font = ImageFont.truetype(font_name, font_size)
                font_loaded = True
                break
            except OSError:
                continue

        if not font_loaded:
            raise OSError('No preferred fonts found')

    except OSError:
        regular_font = ImageFont.load_default()

    return regular_font


def calculate_iou(box1, box2):
    """
    Calculate Intersection over Union (IoU) between two bounding boxes.
    Each box should be in format (x1, y1, x2, y2).
    """
    # Calculate intersection area
    x1_inter = max(box1[0], box2[0])
    y1_inter = max(box1[1], box2[1])
    x2_inter = min(box1[2], box2[2])
    y2_inter = min(box1[3], box2[3])

    # No intersection
    if x2_inter < x1_inter or y2_inter < y1_inter:
        return 0, 0, 0

    intersection_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)

    # Calculate area of each box
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    # Calculate IoU
    iou1 = intersection_area / box1_area
    iou2 = intersection_area / box2_area
    iou = intersection_area / float(box1_area + box2_area - intersection_area)
    return iou1, iou2, iou


def is_box_inside(box1, box2):
    """
    Determine if box1 is inside box2.

    Args:
        box1: Tuple or list (x1, y1, x2, y2) - the box to check if it's inside
        box2: Tuple or list (x1, y1, x2, y2) - the container box
        threshold: Float between 0 and 1 - the minimum percentage of box1 that must be
                  inside box2 to consider it "inside" (default: 0.9 or 90%)

    Returns:
        Boolean: True if box1 is inside box2, False otherwise
    """
    x11, y11, x12, y12 = box1
    x21, y21, x22, y22 = box2
    if x21 >= x11 and y21 >= y22 and x22 <= x12 and y22 <= y12:
        return True
    else:
        return False


def calculate_overlap_ratio(box1, box2):
    """Calculate what percentage of box1 overlaps with box2"""
    # Calculate intersection
    x1_inter = max(box1[0], box2[0])
    y1_inter = max(box1[1], box2[1])
    x2_inter = min(box1[2], box2[2])
    y2_inter = min(box1[3], box2[3])

    # No intersection
    if x2_inter <= x1_inter or y2_inter <= y1_inter:
        return 0.0

    # Calculate areas
    intersection_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)
    box1_area = calculate_area(box1)

    if box1_area == 0:
        return 0.0

    return intersection_area / box1_area


def calculate_area(box):
    """Calculate area of a box"""
    return (box[2] - box[0]) * (box[3] - box[1])


def create_task_with_error_handling(
        coro: Coroutine[Any, Any, T],
        *,
        name: str | None = None,
        logger_instance: logging.Logger | None = None,
        suppress_exceptions: bool = False,
) -> asyncio.Task[T]:
    """
    Create an asyncio task with proper exception handling to prevent "Task exception was never retrieved" warnings.

    Args:
        coro: The coroutine to wrap in a task
        name: Optional name for the task (useful for debugging)
        logger_instance: Optional logger instance to use. If None, uses module logger.
        suppress_exceptions: If True, logs exceptions at ERROR level. If False, logs at WARNING level
            and exceptions remain retrievable via task.exception() if the caller awaits the task.
            Default False.

    Returns:
        asyncio.Task: The created task with exception handling callback

    Example:
        # Fire-and-forget with suppressed exceptions
        create_task_with_error_handling(some_async_function(), name="my_task", suppress_exceptions=True)

        # Task with retrievable exceptions (if you plan to await it)
        task = create_task_with_error_handling(critical_function(), name="critical")
        result = await task  # Will raise the exception if one occurred
    """
    task = asyncio.create_task(coro, name=name)
    log = logger_instance or logger

    def _handle_task_exception(t: asyncio.Task[T]) -> None:
        """Callback to handle task exceptions"""
        exc_to_raise = None
        try:
            # This will raise if the task had an exception
            exc = t.exception()
            if exc is not None:
                task_name = t.get_name() if hasattr(t, 'get_name') else 'unnamed'
                if suppress_exceptions:
                    log.error(f'Exception in background task [{task_name}]: {type(exc).__name__}: {exc}', exc_info=exc)
                else:
                    # Log at warning level then mark for re-raising
                    log.warning(
                        f'Exception in background task [{task_name}]: {type(exc).__name__}: {exc}',
                        exc_info=exc,
                    )
                    exc_to_raise = exc
        except asyncio.CancelledError:
            # Task was cancelled, this is normal behavior
            pass
        except Exception as e:
            # Catch any other exception during exception handling (e.g., t.exception() itself failing)
            task_name = t.get_name() if hasattr(t, 'get_name') else 'unnamed'
            log.error(f'Error handling exception in task [{task_name}]: {type(e).__name__}: {e}')

        # Re-raise outside the try-except block so it propagates to the event loop
        if exc_to_raise is not None:
            raise exc_to_raise

    task.add_done_callback(_handle_task_exception)
    return task


class SignalHandler:
    """
    A modular and reusable signal handling system for managing SIGINT (Ctrl+C), SIGTERM,
    and other signals in asyncio applications.

    This class provides:
    - Configurable signal handling for SIGINT and SIGTERM
    - Support for custom pause/resume callbacks
    - Management of event loop state across signals
    - Standardized handling of first and second Ctrl+C presses
    - Cross-platform compatibility (with simplified behavior on Windows)
    """

    def __init__(
            self,
            loop: asyncio.AbstractEventLoop | None = None,
            pause_callback: Callable[[], None] | None = None,
            resume_callback: Callable[[], None] | None = None,
            custom_exit_callback: Callable[[], None] | None = None,
            exit_on_second_int: bool = True,
            interruptible_task_patterns: list[str] | None = None,
    ):
        """
        Initialize the signal handler.

        Args:
            loop: The asyncio event loop to use. Defaults to current event loop.
            pause_callback: Function to call when system is paused (first Ctrl+C)
            resume_callback: Function to call when system is resumed
            custom_exit_callback: Function to call on exit (second Ctrl+C or SIGTERM)
            exit_on_second_int: Whether to exit on second SIGINT (Ctrl+C)
            interruptible_task_patterns: List of patterns to match task names that should be
                                         canceled on first Ctrl+C (default: ['step', 'multi_act', 'get_next_action'])
        """
        self.loop = loop or asyncio.get_event_loop()
        self.pause_callback = pause_callback
        self.resume_callback = resume_callback
        self.custom_exit_callback = custom_exit_callback
        self.exit_on_second_int = exit_on_second_int
        self.interruptible_task_patterns = interruptible_task_patterns or ['step', 'multi_act', 'get_next_action']
        self.is_windows = platform.system() == 'Windows'

        # Initialize loop state attributes
        self._initialize_loop_state()

        # Store original signal handlers to restore them later if needed
        self.original_sigint_handler = None
        self.original_sigterm_handler = None

    def _initialize_loop_state(self) -> None:
        """Initialize loop state attributes used for signal handling."""
        setattr(self.loop, 'ctrl_c_pressed', False)
        setattr(self.loop, 'waiting_for_input', False)

    def register(self) -> None:
        """Register signal handlers for SIGINT and SIGTERM."""
        try:
            if self.is_windows:
                # On Windows, use simple signal handling with immediate exit on Ctrl+C
                def windows_handler(sig, frame):
                    print('\n\n🛑 Got Ctrl+C. Exiting immediately on Windows...\n', file=stderr)
                    # Run the custom exit callback if provided
                    if self.custom_exit_callback:
                        self.custom_exit_callback()
                    os._exit(0)

                self.original_sigint_handler = signal.signal(signal.SIGINT, windows_handler)
            else:
                # On Unix-like systems, use asyncio's signal handling for smoother experience
                self.original_sigint_handler = self.loop.add_signal_handler(signal.SIGINT,
                                                                            lambda: self.sigint_handler())
                self.original_sigterm_handler = self.loop.add_signal_handler(signal.SIGTERM,
                                                                             lambda: self.sigterm_handler())

        except Exception:
            # there are situations where signal handlers are not supported, e.g.
            # - when running in a thread other than the main thread
            # - some operating systems
            # - inside jupyter notebooks
            pass

    def unregister(self) -> None:
        """Unregister signal handlers and restore original handlers if possible."""
        try:
            if self.is_windows:
                # On Windows, just restore the original SIGINT handler
                if self.original_sigint_handler:
                    signal.signal(signal.SIGINT, self.original_sigint_handler)
            else:
                # On Unix-like systems, use asyncio's signal handler removal
                self.loop.remove_signal_handler(signal.SIGINT)
                self.loop.remove_signal_handler(signal.SIGTERM)

                # Restore original handlers if available
                if self.original_sigint_handler:
                    signal.signal(signal.SIGINT, self.original_sigint_handler)
                if self.original_sigterm_handler:
                    signal.signal(signal.SIGTERM, self.original_sigterm_handler)
        except Exception as e:
            logger.warning(f'Error while unregistering signal handlers: {e}')

    def _handle_second_ctrl_c(self) -> None:
        """
        Handle a second Ctrl+C press by performing cleanup and exiting.
        This is shared logic used by both sigint_handler and wait_for_resume.
        """
        global _exiting

        if not _exiting:
            _exiting = True

            # Call custom exit callback if provided
            if self.custom_exit_callback:
                try:
                    self.custom_exit_callback()
                except Exception as e:
                    logger.error(f'Error in exit callback: {e}')

        # Force immediate exit - more reliable than sys.exit()
        print('\n\n🛑  Got second Ctrl+C. Exiting immediately...\n', file=stderr)

        # Reset terminal to a clean state by sending multiple escape sequences
        # Order matters for terminal resets - we try different approaches

        # Reset terminal modes for both stdout and stderr
        print('\033[?25h', end='', flush=True, file=stderr)  # Show cursor
        print('\033[?25h', end='', flush=True)  # Show cursor

        # Reset text attributes and terminal modes
        print('\033[0m', end='', flush=True, file=stderr)  # Reset text attributes
        print('\033[0m', end='', flush=True)  # Reset text attributes

        # Disable special input modes that may cause arrow keys to output control chars
        print('\033[?1l', end='', flush=True, file=stderr)  # Reset cursor keys to normal mode
        print('\033[?1l', end='', flush=True)  # Reset cursor keys to normal mode

        # Disable bracketed paste mode
        print('\033[?2004l', end='', flush=True, file=stderr)
        print('\033[?2004l', end='', flush=True)

        # Carriage return helps ensure a clean line
        print('\r', end='', flush=True, file=stderr)
        print('\r', end='', flush=True)

        # these ^^ attempts dont work as far as we can tell
        # we still dont know what causes the broken input, if you know how to fix it, please let us know
        print('(tip: press [Enter] once to fix escape codes appearing after chrome exit)', file=stderr)

        os._exit(0)

    def sigint_handler(self) -> None:
        """
        SIGINT (Ctrl+C) handler.

        First Ctrl+C: Cancel current step and pause.
        Second Ctrl+C: Exit immediately if exit_on_second_int is True.
        """
        global _exiting

        if _exiting:
            # Already exiting, force exit immediately
            os._exit(0)

        if getattr(self.loop, 'ctrl_c_pressed', False):
            # If we're in the waiting for input state, let the pause method handle it
            if getattr(self.loop, 'waiting_for_input', False):
                return

            # Second Ctrl+C - exit immediately if configured to do so
            if self.exit_on_second_int:
                self._handle_second_ctrl_c()

        # Mark that Ctrl+C was pressed
        setattr(self.loop, 'ctrl_c_pressed', True)

        # Cancel current tasks that should be interruptible - this is crucial for immediate pausing
        self._cancel_interruptible_tasks()

        # Call pause callback if provided - this sets the paused flag
        if self.pause_callback:
            try:
                self.pause_callback()
            except Exception as e:
                logger.error(f'Error in pause callback: {e}')

        # Log pause message after pause_callback is called (not before)
        print('----------------------------------------------------------------------', file=stderr)

    def sigterm_handler(self) -> None:
        """
        SIGTERM handler.

        Always exits the program completely.
        """
        global _exiting
        if not _exiting:
            _exiting = True
            print('\n\n🛑 SIGTERM received. Exiting immediately...\n\n', file=stderr)

            # Call custom exit callback if provided
            if self.custom_exit_callback:
                self.custom_exit_callback()

        os._exit(0)

    def _cancel_interruptible_tasks(self) -> None:
        """Cancel current tasks that should be interruptible."""
        current_task = asyncio.current_task(self.loop)
        for task in asyncio.all_tasks(self.loop):
            if task != current_task and not task.done():
                task_name = task.get_name() if hasattr(task, 'get_name') else str(task)
                # Cancel tasks that match certain patterns
                if any(pattern in task_name for pattern in self.interruptible_task_patterns):
                    logger.debug(f'Cancelling task: {task_name}')
                    task.cancel()
                    # Add exception handler to silence "Task exception was never retrieved" warnings
                    task.add_done_callback(lambda t: t.exception() if t.cancelled() else None)

        # Also cancel the current task if it's interruptible
        if current_task and not current_task.done():
            task_name = current_task.get_name() if hasattr(current_task, 'get_name') else str(current_task)
            if any(pattern in task_name for pattern in self.interruptible_task_patterns):
                logger.debug(f'Cancelling current task: {task_name}')
                current_task.cancel()

    def wait_for_resume(self) -> None:
        """
        Wait for user input to resume or exit.

        This method should be called after handling the first Ctrl+C.
        It temporarily restores default signal handling to allow catching
        a second Ctrl+C directly.
        """
        # Set flag to indicate we're waiting for input
        setattr(self.loop, 'waiting_for_input', True)

        # Temporarily restore default signal handling for SIGINT
        # This ensures KeyboardInterrupt will be raised during input()
        original_handler = signal.getsignal(signal.SIGINT)
        try:
            signal.signal(signal.SIGINT, signal.default_int_handler)
        except ValueError:
            # we are running in a thread other than the main thread
            # or signal handlers are not supported for some other reason
            pass

        green = '\x1b[32;1m'
        red = '\x1b[31m'
        blink = '\033[33;5m'
        unblink = '\033[0m'
        reset = '\x1b[0m'

        try:  # escape code is to blink the ...
            print(
                f'➡️  Press {green}[Enter]{reset} to resume or {red}[Ctrl+C]{reset} again to exit{blink}...{unblink} ',
                end='',
                flush=True,
                file=stderr,
            )
            input()  # This will raise KeyboardInterrupt on Ctrl+C

            # Call resume callback if provided
            if self.resume_callback:
                self.resume_callback()
        except KeyboardInterrupt:
            # Use the shared method to handle second Ctrl+C
            self._handle_second_ctrl_c()
        finally:
            try:
                # Restore our signal handler
                signal.signal(signal.SIGINT, original_handler)
                setattr(self.loop, 'waiting_for_input', False)
            except Exception:
                pass

    def reset(self) -> None:
        """Reset state after resuming."""
        # Clear the flags
        if hasattr(self.loop, 'ctrl_c_pressed'):
            setattr(self.loop, 'ctrl_c_pressed', False)
        if hasattr(self.loop, 'waiting_for_input'):
            setattr(self.loop, 'waiting_for_input', False)
