import asyncio
import json
import enum
import logging
import time
from typing import Dict, Generic, Optional, Type, TypeVar
from pydantic import BaseModel

from android_use.llm.base import BaseChatModel
from android_use.tools.registry.views import ActionModel
from android_use.agent.views import ActionResult
from android_use.android.context import AndroidContext
from android_use.tools.registry.service import Registry
from android_use.tools.views import (
    DoneAction,
    ClickElementAction,
    InputTextAction,
    SwipeAction,
    DragAction,
    LongPressElementAction,
    PressKeyAction,
    ShellCommandAction,
    PullFileAction,
    PushFileAction,
    LaunchAppAction,
    RecordImportantContentAction,
    GenerateOrUpdateTodosAction
)
from android_use.android.views import DOMElementNode
from android_use.utils import time_execution_async, time_execution_sync
from android_use.tools import action_highlight

logger = logging.getLogger(__name__)

Context = TypeVar('Context')


class AndroidTools(Generic[Context]):
    def __init__(
            self,
            exclude_actions: list[str] = [],
            output_model: Optional[Type[BaseModel]] = None,
    ):
        self.registry = Registry[Context](exclude_actions)

        """Register all default browser actions"""

        if output_model is not None:
            # Create a new model that extends the output model with success parameter
            class ExtendedOutputModel(BaseModel):  # type: ignore
                success: bool = True
                data: output_model

            @self.registry.action(
                'Complete task - with return text and if the task is finished (success=True) or not yet  completely finished (success=False), because last step is reached',
                param_model=ExtendedOutputModel,
            )
            async def done(params: ExtendedOutputModel):
                # Exclude success from the output JSON since it's an internal parameter
                output_dict = params.data.model_dump()

                # Enums are not serializable, convert to string
                for key, value in output_dict.items():
                    if isinstance(value, enum.Enum):
                        output_dict[key] = value.value

                return ActionResult(is_done=True, success=params.success, extracted_content=json.dumps(output_dict))
        else:

            @self.registry.action(
                'Complete task - with return text and if the task is finished (success=True) or not yet  completely finished (success=False), because last step is reached',
                param_model=DoneAction,
            )
            async def done(params: DoneAction):
                return ActionResult(is_done=True, success=params.success, extracted_content=params.text)

        @self.registry.action('Wait for x seconds.')
        async def wait(wait_secs: float = 3.0):
            msg = f'Waiting for {wait_secs} seconds'
            logger.info(msg)
            await asyncio.sleep(wait_secs)
            return ActionResult(extracted_content=msg, include_in_memory=True)

        @self.registry.action(
            'Launch an app by name.',
            param_model=LaunchAppAction
        )
        async def launch_app(params: LaunchAppAction, android: AndroidContext):
            success = android.launch_app(params.app_name)
            
            # Highlight the action on screenshot
            if android.current_state.screenshot:
                android.current_state.screenshot = action_highlight.highlight_launch_app_action(
                    android.current_state.screenshot, params.app_name
                )
            
            if success:
                return ActionResult(extracted_content=f"Launched app '{params.app_name}'")
            else:
                # Import to get the list of supported apps
                from android_use.tools.apps import APP_PACKAGES
                supported_apps = sorted(list(set(APP_PACKAGES.keys())))
                apps_list = ", ".join(supported_apps)
                error_msg = (
                    f"Failed to launch app '{params.app_name}' - app not found in supported apps list.\n"
                    f"Supported apps include: {apps_list}.\n"
                    f"Alternative: Find the app icon on the home screen or app drawer and click it using click_element action."
                )
                return ActionResult(
                    success=False,
                    extracted_content=error_msg
                )

        @self.registry.action(
            'Record important content on the screen that relative to task or helpful to accomplish the ultimate task.',
            param_model=RecordImportantContentAction
        )
        async def record_important_content(params: RecordImportantContentAction, android: AndroidContext):
            return ActionResult(extracted_content=params.content, include_in_memory=True)

        @self.registry.action(
            'Generate or update a markdown-formatted TODO list to track task progress. Use at task start to plan, then update as you complete sub-tasks or encounter new situations.',
            param_model=GenerateOrUpdateTodosAction
        )
        async def generate_or_update_todos(params: GenerateOrUpdateTodosAction, android: AndroidContext):
            """Generate or update the TODO list"""
            # Store todos in android context
            android.todos = params.todos
            logger.info(f"Updated TODO list:\n{params.todos}")
            return ActionResult(extracted_content=f"TODO list updated", include_in_memory=True)

        @self.registry.action(
            'Taps on a specific UI element by its index or coordinates.',
            param_model=ClickElementAction
        )
        async def tap(params: ClickElementAction, android: AndroidContext):
            # Prioritize index over coordinates
            if params.index is not None:
                # Use helper to get node and calculate center
                node = self._get_element_node(android, params.index)
                x1, y1, x2, y2 = node.bounding_box
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                android.click(cx, cy)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_tap_action(
                        android.current_state.screenshot, cx, cy
                    )
                
                return ActionResult(extracted_content=f"Clicked element at index {params.index}")
            elif params.x is not None and params.y is not None:
                # Use coordinates as fallback
                cx, cy = self._denormalize_coordinates(params.x, params.y, android)
                android.click(cx, cy)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_tap_action(
                        android.current_state.screenshot, cx, cy
                    )
                
                return ActionResult(extracted_content=f"Clicked at coordinates ({cx:.0f}, {cy:.0f})")
            else:
                raise ValueError("Either index or (x, y) coordinates must be provided")

        @self.registry.action(
            'Presses and holds an element by its index or coordinates.',
            param_model=LongPressElementAction
        )
        async def long_press(params: LongPressElementAction, android: AndroidContext):
            # Prioritize index over coordinates
            if params.index is not None:
                # Use helper to get node and calculate center
                node = self._get_element_node(android, params.index)
                x1, y1, x2, y2 = node.bounding_box
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                # Use the duration from params (default is 1.0s in the model)
                android.long_click(cx, cy, duration=params.duration)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_long_press_action(
                        android.current_state.screenshot, cx, cy
                    )
                
                duration_str = f" for {params.duration}s" if params.duration is not None else " for default duration"
                return ActionResult(extracted_content=f"Long pressed element {params.index}{duration_str}")
            elif params.x is not None and params.y is not None:
                # Use coordinates as fallback
                cx, cy = self._denormalize_coordinates(params.x, params.y, android)
                android.long_click(cx, cy, duration=params.duration)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_long_press_action(
                        android.current_state.screenshot, cx, cy
                    )
                
                duration_str = f" for {params.duration}s" if params.duration is not None else " for default duration"
                return ActionResult(extracted_content=f"Long pressed at coordinates ({cx:.0f}, {cy:.0f}){duration_str}")
            else:
                raise ValueError("Either index or (x, y) coordinates must be provided")

        @self.registry.action(
            'Types text. If index or coordinates are given, clicks the element first.',
            param_model=InputTextAction
        )
        async def input_text(params: InputTextAction, android: AndroidContext):
            # Prioritize index over coordinates
            if params.index is not None:
                # Click the element first to try and focus it
                node = self._get_element_node(android, params.index)  # Use helper
                x1, y1, x2, y2 = node.bounding_box
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                logger.info(f"Clicking element {params.index} at ({cx:.0f}, {cy:.0f}) before input.")
                android.click(cx, cy)
                await asyncio.sleep(1.0)  # Brief pause after click
                android.send_keys(params.text, clear=params.clear)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_input_text_action(
                        android.current_state.screenshot, cx, cy
                    )
                
                clear_str = " after clearing" if params.clear else ""
                return ActionResult(extracted_content=f"Input '{params.text}'{clear_str} into element {params.index}")
            elif params.x is not None and params.y is not None:
                # Use coordinates as fallback
                cx, cy = self._denormalize_coordinates(params.x, params.y, android)
                logger.info(f"Clicking at ({cx:.0f}, {cy:.0f}) before input.")
                android.click(cx, cy)
                await asyncio.sleep(1.0)  # Brief pause after click
                android.send_keys(params.text, clear=params.clear)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_input_text_action(
                        android.current_state.screenshot, cx, cy
                    )
                
                clear_str = " after clearing" if params.clear else ""
                return ActionResult(
                    extracted_content=f"Input '{params.text}'{clear_str} at coordinates ({cx:.0f}, {cy:.0f})")
            else:
                # No index or coordinates provided, send keys directly
                logger.warning(
                    "Inputting text without specifying an element index or coordinates. Assuming focus is correct.")
                android.send_keys(params.text, clear=params.clear)  # Clear likely has no effect here
                return ActionResult(extracted_content=f"Input '{params.text}' (no specific element)")

        @self.registry.action(
            'Swipes screen using coordinates.',
            param_model=SwipeAction
        )
        async def swipe(params: SwipeAction, android: AndroidContext):
            # Denormalize coordinates
            x1, y1 = self._denormalize_coordinates(params.x1, params.y1, android)
            x1 = max(min(android.screen_width - android.screen_width // 5, x1), android.screen_width // 5)
            y1 = max(min(android.screen_height - android.screen_height // 5, y1), android.screen_height // 5)
            x2, y2 = self._denormalize_coordinates(params.x2, params.y2, android)
            x2 = max(min(android.screen_width - android.screen_width // 5, x2), android.screen_width // 5)
            y2 = max(min(android.screen_height - android.screen_height // 5, y2), android.screen_height // 5)
            # Perform swipe
            android.swipe(x1, y1, x2, y2, duration=0.2)
            
            # Highlight the action on screenshot
            if android.current_state.screenshot:
                android.current_state.screenshot = action_highlight.highlight_swipe_action(
                    android.current_state.screenshot, x1, y1, x2, y2
                )
            
            return ActionResult(extracted_content=f"Swiped from ({x1:.0f}, {y1:.0f}) to ({x2:.0f}, {y2:.0f})")

        @self.registry.action(
            'Press System Key. Simulates pressing home, back, or recent.',
            param_model=PressKeyAction
        )
        async def press_key(params: PressKeyAction, android: AndroidContext):
            # Key is already validated by Pydantic Literal
            android.press(params.key)
            
            # Highlight the action on screenshot
            if android.current_state.screenshot:
                android.current_state.screenshot = action_highlight.highlight_press_key_action(
                    android.current_state.screenshot, params.key
                )
            
            return ActionResult(extracted_content=f"Pressed system key '{params.key}'")

        @self.registry.action(
            'Executes an ADB shell command.',
            param_model=ShellCommandAction
        )
        async def execute_shell_command(params: ShellCommandAction, android: AndroidContext):
            output = android.shell(params.command)
            
            # Highlight the action on screenshot
            if android.current_state.screenshot:
                android.current_state.screenshot = action_highlight.highlight_shell_command_action(
                    android.current_state.screenshot, params.command
                )
            
            result_text = f"Executed shell: '{params.command[:50]}...'. Output: {output if output is not None else 'Error/No output'}"
            return ActionResult(extracted_content=result_text)

        @self.registry.action(
            'Uploads a local file to the device.',
            param_model=PushFileAction
        )
        async def push_file_to_device(params: PushFileAction, android: AndroidContext):
            # (Implementation as before, with error handling)
            try:
                android.push_file(params.local_path, params.device_path)
                return ActionResult(
                    extracted_content=f"Pushed '{params.local_path}' to '{params.device_path}'")
            except FileNotFoundError:
                error_msg = f"Error: Local file not found '{params.local_path}'"
                logger.error(error_msg)
                return ActionResult(success=False, extracted_content=error_msg)
            except Exception as e:
                error_msg = f"Error pushing '{params.local_path}': {e}"
                logger.exception(error_msg)
                return ActionResult(success=False, extracted_content=error_msg)

        @self.registry.action(
            'Downloads a file from the device.',
            param_model=PullFileAction
        )
        async def pull_file_from_device(params: PullFileAction, android: AndroidContext):
            # (Implementation as before, with error handling)
            try:
                android.pull_file(params.device_path, params.local_path)
                return ActionResult(
                    extracted_content=f"Pulled '{params.device_path}' to '{params.local_path}'")
            except Exception as e:
                error_msg = f"Error pulling '{params.device_path}': {e}"
                logger.exception(error_msg)
                return ActionResult(success=False, extracted_content=error_msg)

        @self.registry.action(
            'Drags one element to another element\'s location or uses coordinates.',
            param_model=DragAction
        )
        async def drag(params: DragAction, android: AndroidContext):
            # Prioritize index over coordinates
            if params.start_index is not None and params.end_index is not None:
                # Use helper to get nodes and their centers
                start_node = self._get_element_node(android, params.start_index, "drag start")
                end_node = self._get_element_node(android, params.end_index, "drag end")

                sx1, sy1, sx2, sy2 = start_node.bounding_box
                scx, scy = (sx1 + sx2) / 2, (sy1 + sy2) / 2

                ex1, ey1, ex2, ey2 = end_node.bounding_box
                ecx, ecy = (ex1 + ex2) / 2, (ey1 + ey2) / 2

                android.drag(scx, scy, ecx, ecy, duration=params.duration)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_drag_action(
                        android.current_state.screenshot, scx, scy, ecx, ecy
                    )
                
                return ActionResult(
                    extracted_content=f"Dragged element {params.start_index} to element {params.end_index}")
            elif params.x1 is not None and params.y1 is not None and params.x2 is not None and params.y2 is not None:
                # Use coordinates as fallback
                scx, scy = self._denormalize_coordinates(params.x1, params.y1, android)
                ecx, ecy = self._denormalize_coordinates(params.x2, params.y2, android)
                android.drag(scx, scy, ecx, ecy, duration=params.duration)
                
                # Highlight the action on screenshot
                if android.current_state.screenshot:
                    android.current_state.screenshot = action_highlight.highlight_drag_action(
                        android.current_state.screenshot, scx, scy, ecx, ecy
                    )
                
                return ActionResult(extracted_content=f"Dragged from ({scx:.0f}, {scy:.0f}) to ({ecx:.0f}, {ecy:.0f})")
            else:
                raise ValueError("Either (start_index, end_index) or (x1, y1, x2, y2) coordinates must be provided")

    def _denormalize_coordinates(self, x: float, y: float, android: AndroidContext) -> tuple[float, float]:
        """
        Denormalize coordinates based on screen dimensions.
        
        If coordinates are > 1, they are treated as already in pixels (divided by 1000 first).
        If coordinates are <= 1, they are treated as normalized (0-1) and multiplied by screen dimensions.
        
        Args:
            x: X coordinate (normalized 0-1 or pixel value > 1)
            y: Y coordinate (normalized 0-1 or pixel value > 1)
            android: AndroidContext with screen dimensions
            
        Returns:
            Tuple of (denormalized_x, denormalized_y) in pixels
        """
        if x > 1000 or y > 1000:
            return x, y
        if x > 1:
            # Treat as pixel value divided by 1000
            x = (x / 1000.0) * android.screen_width
        else:
            # Treat as normalized value
            x = x * android.screen_width

        if y > 1:
            # Treat as pixel value divided by 1000
            y = (y / 1000.0) * android.screen_height
        else:
            # Treat as normalized value
            y = y * android.screen_height

        return x, y

    def _get_element_node(self, android: AndroidContext, index: int, context: str = "target") -> DOMElementNode:
        current_state = android.current_state
        if index not in current_state.selector_map:
            raise ValueError(f"Element {index} ({context}) not found.")
        node = current_state.selector_map[index]
        if not node.bounding_box:
            raise ValueError(f"Element {index} ({context}) has no bounds.")
        return node

    @time_execution_sync('--act')
    async def act(
            self,
            action: ActionModel,
            android_context: AndroidContext,
            page_extraction_llm: Optional[BaseChatModel] = None,
            sensitive_data: Optional[Dict[str, str]] = None,
            available_file_paths: Optional[list[str]] = None,
            #
            context: Context | None = None,
    ) -> ActionResult:
        """Execute an action"""

        try:
            for action_name, params in action.model_dump(exclude_unset=True).items():
                if params is not None:
                    result = await self.registry.execute_action(
                        action_name,
                        params,
                        android=android_context,
                        page_extraction_llm=page_extraction_llm,
                        sensitive_data=sensitive_data,
                        available_file_paths=available_file_paths,
                        context=context,
                    )

                    if isinstance(result, str):
                        return ActionResult(extracted_content=result)
                    elif isinstance(result, ActionResult):
                        return result
                    elif result is None:
                        return ActionResult()
                    else:
                        raise ValueError(f'Invalid action result type: {type(result)} of {result}')
            return ActionResult()
        except Exception as e:
            raise e

    async def multi_act(
            self,
            actions: list[ActionModel],
            android_context: AndroidContext,
            page_extraction_llm: Optional[BaseChatModel] = None,
            sensitive_data: Optional[Dict[str, str]] = None,
            available_file_paths: Optional[list[str]] = None,
            context: Context | None = None,
    ) -> list[ActionResult]:
        """Execute multiple actions"""
        results: list[ActionResult] = []
        time_elapsed = 0
        total_actions = len(actions)

        for i, action in enumerate(actions):
            try:
                # Get action name from the action model
                action_data = action.model_dump(exclude_unset=True)
                action_name = next(iter(action_data.keys())) if action_data else 'unknown'

                # Log action before execution
                logger.info(f'Executing action {i + 1}/{total_actions}: {action_name}')

                time_start = time.time()

                result = await self.act(
                    action=action,
                    android_context=android_context,
                    page_extraction_llm=page_extraction_llm,
                    sensitive_data=sensitive_data,
                    available_file_paths=available_file_paths,
                    context=context,
                )

                time_end = time.time()
                time_elapsed = time_end - time_start
                await asyncio.sleep(1)
                if result.error:
                    logger.error(f'Action "{action_name}" failed: {result.error}')
                elif result.is_done:
                    completion_text = result.extracted_content or 'Task marked as done.'
                    logger.info(f'Done: {completion_text}')

                results.append(result)

            except Exception as e:
                logger.error(f'❌ Executing action {i + 1} failed -> {type(e).__name__}: {e}')
                raise e

        return results
