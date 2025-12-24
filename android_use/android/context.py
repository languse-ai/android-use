import logging
import time
import traceback
from datetime import datetime
from typing import Literal
import uiautomator2 as u2
import adbutils
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Dict, Union, Tuple
from PIL import ImageDraw
import colorsys
from pathlib import Path
from .. import utils
from android_use.tools.apps import APP_PACKAGES

from .views import DOMElementNode, DOMBaseNode, NODE_TYPE_TEXT, NODE_TYPE_INTERACTIVE, NODE_TYPE_NON_INTERACTIVE
from .views import AndroidState

logger = logging.getLogger(__name__)


@dataclass
class AndroidContextConfig:
    device_id: Union[str, adbutils.AdbDevice] = None
    highlight_elements: bool = True


class AndroidContext:
    def __init__(self, config: AndroidContextConfig):
        self.config = config
        try:
            self.android_context = u2.connect(config.device_id)
            self.screen_width = None
            self.screen_height = None
        except Exception as e:
            traceback.print_exc()
            self.android_context = None
        self.current_state = AndroidState()

    def check_context(self):
        if self.android_context is None:
            raise RuntimeError("Android context not initialized")

    def take_screenshot(self) -> str:
        self.check_context()
        screenshot_pil = self.android_context.screenshot()
        self.screen_width, self.screen_height = screenshot_pil.size
        screenshot_base64 = utils.pil_image_to_base64(image=screenshot_pil)
        return screenshot_base64

    def get_xml(self, compressed=False, pretty=False) -> str:
        self.check_context()
        xml = self.android_context.dump_hierarchy(compressed=compressed, pretty=pretty)
        return xml

    def _parse_node_recursive(self, element: ET.Element, parent_node: Optional[DOMElementNode]) -> DOMElementNode:
        """
        Recursively parses an XML element into a DOMElementNode object and updates the highlight counter.

        Args:
            element (ET.Element): The xml.etree.ElementTree.Element to parse.
            parent_node (Optional[DOMElementNode]): The parent DOMElementNode in the hierarchy.

        Returns:
            Tuple[DOMElementNode, int]: A tuple containing:
                - The created DOMElementNode object.
        """
        attributes = element.attrib  # Get all attributes of the element

        # --- Extract Attributes ---
        text = attributes.get('text', '')
        resource_id = attributes.get('resource-id', '')
        class_name = attributes.get('class', '')  # XML uses 'class' as the attribute name
        package = attributes.get('package', '')
        content_desc = attributes.get('content-desc', '')
        node_index_str = attributes.get('index', '')  # Get 'index' attribute, keep as string

        node_text = text or content_desc

        def _str_to_bool(s: Optional[str]) -> bool:
            """Converts XML attribute strings 'true'/'false' to Python bool."""
            return s is not None and s.lower() == 'true'

        # --- Parse Boolean Attributes ---
        enabled = _str_to_bool(attributes.get('enabled'))
        clickable = _str_to_bool(attributes.get('clickable'))
        focusable = _str_to_bool(attributes.get('focusable'))
        long_clickable = _str_to_bool(attributes.get('long-clickable'))
        # visible_to_user = _str_to_bool(attributes.get('visible-to-user', 'true')) # Can parse visible-to-user if needed

        # --- Parse Bounds ---
        bounds_str = attributes.get('bounds')
        bounding_box = DOMBaseNode._parse_bounds(bounds_str)

        # Check if the node is interactive
        # Include long-clickable as a valid interaction method
        is_interactive = enabled and (clickable or focusable or long_clickable)

        if is_interactive:
            node_type = NODE_TYPE_INTERACTIVE
        else:
            # If not interactive, check for text content to determine if it's TEXT_NODE
            if node_text:
                node_type = NODE_TYPE_TEXT
            else:
                # Neither interactive nor has text content
                node_type = NODE_TYPE_NON_INTERACTIVE

        # --- Create DOMElementNode Instance ---
        current_dom_node = DOMElementNode(
            parent=parent_node,  # Set parent node
            bounding_box=bounding_box,  # Set bounding box
            text=node_text,  # Set text
            node_type=node_type,  # Set node type
            node_index=node_index_str,  # Set node index (from XML)
            package=package,  # Set package name
            class_name=class_name,  # Set class name
            resource_id=resource_id,  # Set resource ID
            children=[]  # Initialize empty children list, will be filled below
        )

        # --- Recursively Parse Children ---
        for child_element in element:  # Iterate over direct children of the current element
            if child_element.tag == 'node':  # Process only child elements with the 'node' tag
                # Recursive call, passing current node as parent and updated counter
                child_dom_node = self._parse_node_recursive(
                    child_element, current_dom_node
                )
                # Add the parsed child node to the current node's children list
                current_dom_node.children.append(child_dom_node)

        # Return the created current node and the potentially updated counter
        return current_dom_node

    def parse_xml(self, xml_string: str) -> Optional[DOMElementNode]:
        """
        Parses an Android UI hierarchy XML string into a tree of DOMElementNode objects.

        Args:
            xml_string (str): The XML string obtained from the UI dump.

        Returns:
            Optional[DOMElementNode]: The root DOMElementNode of the parsed hierarchy,
                                    or None if parsing fails or the XML is empty/invalid.
        """
        if not xml_string:
            logging.error("Input XML string is empty.")
            return None
        try:
            # Parse the XML string
            root_element = ET.fromstring(xml_string)
            root_dom_node = self._parse_node_recursive(root_element, parent_node=None)
            return root_dom_node

        except ET.ParseError as e:
            # Catch and log XML parsing errors
            logging.error(
                f"Error parsing XML: {e}\nXML content snippet: {xml_string[:200]}...")  # Log a snippet of XML content to aid debugging
            return None
        except Exception as e:
            # Catch other potential unexpected errors during parsing or node creation
            logging.exception(
                f"An unexpected error occurred during XML parsing: {e}")  # Use exception to log the full traceback
            return None

    def get_selector_map(self, root_node: DOMElementNode) -> Optional[Dict[int, DOMElementNode]]:
        """
        Get Selector Map, filtering out nodes that contain multiple other highlighted nodes.

        :param root_node: The root DOM node
        :return: Dictionary mapping highlight_index to nodes, with container nodes filtered out
        """
        selector_map = {}
        highlighted_nodes = []

        # First pass: collect all highlighted nodes
        def collect_highlighted_nodes(node: DOMElementNode) -> None:
            if node.node_type == NODE_TYPE_INTERACTIVE:
                highlighted_nodes.append(node)
            elif node.node_type == NODE_TYPE_TEXT and not node.has_parent_with_interactive_node:
                highlighted_nodes.append(node)
            for child in node.children:
                collect_highlighted_nodes(child)

        collect_highlighted_nodes(root_node)

        # Create a list of nodes to exclude (containers with multiple children)
        nodes_to_exclude = set()

        # For each node, check how many other nodes it contains
        for i, container_node in enumerate(highlighted_nodes):
            contained_nodes = 0
            for j, inner_node in enumerate(highlighted_nodes):
                if i != j and container_node.bounding_box and inner_node.bounding_box:
                    iou1, iou2, _ = utils.calculate_iou(container_node.bounding_box, inner_node.bounding_box)
                    if iou2 > 0.9 and iou1 < 0.5:
                        contained_nodes += 1

            # If this node contains 2 or more other nodes, exclude it
            if contained_nodes > 2 and not container_node.text:
                nodes_to_exclude.add(i)

        highlighted_nodes_cur = [node for i, node in enumerate(highlighted_nodes) if
                                 i not in nodes_to_exclude and node and getattr(node, "bounding_box")]
        highlighted_nodes_cur = sorted(highlighted_nodes_cur, key=lambda node: (
            (node.bounding_box[1] + node.bounding_box[3]) / 2, (node.bounding_box[0] + node.bounding_box[2]) / 2))
        highlighted_nodes_new = []
        for node1 in highlighted_nodes_cur:
            flag = True
            for node2 in highlighted_nodes_new:
                iou1, iou2, iou = utils.calculate_iou(node1.bounding_box, node2.bounding_box)
                if iou > 0.7:
                    flag = False
                    break
            if flag:
                highlighted_nodes_new.append(node1)

        # Sort highlight nodes
        highlighted_nodes_sorted = sorted(highlighted_nodes_new, key=lambda node: (
            (node.bounding_box[1] + node.bounding_box[3]) / 2, (node.bounding_box[0] + node.bounding_box[2]) / 2))
        highlight_index = 0
        for i, node in enumerate(highlighted_nodes_sorted):
            highlight_index += 1
            selector_map[highlight_index] = node

        return selector_map

    def get_all_elements_description(self, selector_map: Dict[int, DOMElementNode]) -> Optional[str]:
        """
        Convert selector_map to description.
        :param selector_map:
        :return:
        """
        formatted_text = []

        for index, node in selector_map.items():
            if node.node_type == NODE_TYPE_INTERACTIVE:
                text = node.get_all_text_till_next_clickable_element()
            else:
                text = node.text
            line = f'[{index}]({text})'
            formatted_text.append(line)
        return '\n'.join(formatted_text)

    def highlight_screenshot(self, screenshot_base64: str, selector_map: Dict[int, DOMElementNode]) -> Optional[str]:
        """
        Highlight interactive elements on a screenshot with intelligent label placement.

        Args:
            screenshot_base64: Base64 encoded string of the screenshot
            selector_map: Dictionary mapping highlight_index to nodes with bounding_box information

        Returns:
            Base64 encoded string of the highlighted screenshot, or None if processing fails
        """
        try:
            # Decode base64 image
            image = utils.base64_to_pil_image(screenshot_base64)
            draw = ImageDraw.Draw(image, 'RGBA')  # Create draw object with RGBA mode for transparency

            # Function to generate visually distinct colors
            def generate_colors(n):
                colors = []
                # Use golden ratio to create well-distributed hues
                golden_ratio_conjugate = 0.618033988749895
                h = 0.1  # starting hue

                for i in range(n):
                    # Generate color using HSV for better control
                    h = (h + golden_ratio_conjugate) % 1.0
                    # Vary saturation and value slightly for better distinction
                    s = 0.65 + (i % 3) * 0.1  # Cycle between 0.65, 0.75, 0.85
                    v = 0.9 - (i % 2) * 0.1  # Cycle between 0.9 and 0.8

                    # Convert HSV to RGB
                    r, g, b = colorsys.hsv_to_rgb(h, s, v)

                    # Scale to 0-255 range
                    colors.append((int(r * 255), int(g * 255), int(b * 255)))

                return colors

            # Generate enough distinct colors for all elements
            num_elements = len(selector_map)
            colors = generate_colors(num_elements)

            # Keep track of occupied label areas to detect overlaps
            occupied_areas = []  # List of (x1, y1, x2, y2) for label areas

            # Sort nodes by size (smaller nodes first) to prioritize label placement for smaller elements
            sorted_items = sorted(
                selector_map.items(),
                key=lambda x: (x[1].bounding_box[2] - x[1].bounding_box[0]) * (
                        x[1].bounding_box[3] - x[1].bounding_box[1])
            )

            for highlight_index, node in sorted_items:
                idx = int(highlight_index) - 1
                bbox = node.bounding_box
                x1, y1, x2, y2 = bbox
                width, height = x2 - x1, y2 - y1

                # Get color for this index
                color = colors[idx % len(colors)]

                # Draw semi-transparent fill
                draw.rectangle([x1, y1, x2, y2], fill=(*color, 64))  # 25% opacity

                # Draw border with the same color (full opacity)
                draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

                # Calculate font size based on box height (adaptive sizing)
                font_size = max(18, min(32, int(height / 4)))
                font = utils.get_font(font_size)

                # Calculate the size of the label
                label = str(highlight_index)
                # Handle different PIL versions
                if hasattr(font, 'getsize'):
                    label_width, label_height = font.getsize(label)
                else:
                    bbox_text = font.getbbox(label)
                    label_width, label_height = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]

                # Create background square for the label
                padding = int(font_size * 0.2)  # 20% padding around text
                square_size = max(label_width, label_height) + (padding * 2)

                # Ensure the label fits within the bounding box
                if square_size > width * 0.5:  # If label would be more than half the width
                    square_size = int(width * 0.5)
                    # Recalculate font size to fit
                    font_size = max(12, int(square_size * 0.6))
                    font = utils.get_font(font_size)

                    # Recalculate label dimensions with new font
                    if hasattr(font, 'getsize'):
                        label_width, label_height = font.getsize(label)
                    else:
                        bbox_text = font.getbbox(label)
                        label_width, label_height = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]

                # Determine where to place the label (try different positions to avoid overlaps)
                positions = [
                    # Right-top (default)
                    (x2 - square_size, y1, x2, y1 + square_size),
                    # Left-top
                    (x1, y1, x1 + square_size, y1 + square_size),
                    # Right-bottom
                    (x2 - square_size, y2 - square_size, x2, y2),
                    # Left-bottom
                    (x1, y2 - square_size, x1 + square_size, y2),
                    # Center-top
                    (x1 + (width - square_size) / 2, y1, x1 + (width + square_size) / 2, y1 + square_size),
                    # Center-bottom
                    (x1 + (width - square_size) / 2, y2 - square_size, x1 + (width + square_size) / 2, y2)
                ]

                # Function to check if a label position overlaps with existing labels
                def is_overlapping(pos):
                    for area in occupied_areas:
                        # Check for overlap
                        if not (pos[2] < area[0] or pos[0] > area[2] or pos[3] < area[1] or pos[1] > area[3]):
                            return True
                    return False

                # Find the first non-overlapping position
                chosen_pos = positions[0]  # Default to right-top
                for pos in positions:
                    if not is_overlapping(pos):
                        chosen_pos = pos
                        break

                # Record this label's position
                occupied_areas.append(chosen_pos)

                # Draw the background square at the chosen position
                draw.rectangle(chosen_pos, fill=color)

                # Calculate text position to center it in the square
                label_pos_x1, label_pos_y1, label_pos_x2, label_pos_y2 = chosen_pos
                text_x = label_pos_x1 + (label_pos_x2 - label_pos_x1) / 2 - label_width / 2
                text_y = label_pos_y1 + (label_pos_y2 - label_pos_y1) / 2 - label_height / 2

                # Draw the text
                draw.text((text_x, text_y), label, fill=(255, 255, 255), font=font)

            # Convert back to base64
            image_draw = utils.pil_image_to_base64(image, "PNG")
            return image_draw

        except Exception as e:
            logging.error(f"Error highlighting screenshot: {e}")
            traceback.print_exc()
            return None

    def update_state(self):
        """
        Updates the current state by fetching screenshot, XML, parsing, and highlighting.
        """
        self.check_context()  # Ensure connection before proceeding
        logger.info("Updating Android state...")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # Use hyphen for file-safe names
        try:
            screenshot = self.take_screenshot()
            xml = self.get_xml()
            root_dom_node = self.parse_xml(xml)

            if root_dom_node:
                selector_map = self.get_selector_map(root_dom_node)
                xml_description = self.get_all_elements_description(selector_map)
                screenshot_highlight = self.highlight_screenshot(screenshot, selector_map)
            else:
                # Handle case where XML parsing failed
                logger.error("Failed to parse XML, state update incomplete.")
                selector_map = {}
                xml_description = "Error: Could not parse UI hierarchy."
                screenshot_highlight = screenshot  # No highlighting possible

            self.current_state = AndroidState(
                device_id=str(self.android_context.serial),  # Store serial as string
                timestamp=timestamp,
                selector_map=selector_map,
                xml=xml,
                element_tree=root_dom_node,
                element_description=xml_description,
                screenshot=screenshot,
                highlight_screenshot=screenshot_highlight,
            )
            logger.info("Android state updated successfully.")
        except Exception as e:
            logger.error(f"Error during state update: {e}")
            traceback.print_exc()
            self.current_state = AndroidState()
        return self.current_state

    def click(self, x: float, y: float):
        """
        Performs a click action at the specified coordinates.

        Args:
            x (float): The x-coordinate.
            y (float): The y-coordinate.
        """
        self.check_context()
        logger.info(f"Clicking at coordinates: ({x}, {y})")
        try:
            self.android_context.click(x, y)
            logger.info("Click action performed.")
        except Exception as e:
            logger.error(f"Failed to perform click at ({x}, {y}): {e}")
            traceback.print_exc()
            # Depending on desired behavior, you might want to re-raise the exception
            # raise

    def long_click(self, x: float, y: float, duration: Optional[float] = None):
        """
        Performs a long click action at the specified coordinates.

        Args:
            x (float): The x-coordinate.
            y (float): The y-coordinate.
            duration (Optional[float]): Duration of the long click in seconds.
                                        Defaults to uiautomator2's internal default (around 0.5s).
        """
        self.check_context()
        duration_str = f" for {duration}s" if duration is not None else ""
        logger.info(f"Long clicking at coordinates: ({x}, {y}){duration_str}")
        try:
            if duration is not None:
                self.android_context.long_click(x, y, duration=duration)
            else:
                self.android_context.long_click(x, y)  # Use default duration
            logger.info("Long click action performed.")
        except Exception as e:
            logger.error(f"Failed to perform long click at ({x}, {y}): {e}")
            traceback.print_exc()

    def press(self, key: Union[str, int], meta: Optional[int] = None):
        """
        Presses a specific key (e.g., 'home', 'back', 'enter') or key code.

        Args:
            key (Union[str, int]): The key name (string) or key code (integer).
                                   Common key names: "home", "back", "left", "right", "up", "down",
                                   "center", "menu", "search", "enter", "delete", "del",
                                   "recent", "volume_up", "volume_down", "volume_mute",
                                   "camera", "power".
            meta (Optional[int]): Meta key state (e.g., META_ALT_ON, META_SHIFT_ON). Rarely needed.
        """
        self.check_context()
        logger.info(f"Pressing key: {key}" + (f" with meta: {meta}" if meta else ""))
        try:
            self.android_context.press(key, meta=meta)
            logger.info(f"Key '{key}' pressed.")
        except Exception as e:
            logger.error(f"Failed to press key '{key}': {e}")
            traceback.print_exc()

    def send_keys(self, text: str, clear: bool = False):
        """
        Sends key events to the device, simulating keyboard input.
        Note: This usually sends keys to the currently focused element (if any)
              or globally if no element is focused.

        Args:
            text (str): The text string to send.
            clear (bool): Whether to clear the existing text in the target field before sending.
                          This might require the element to be focused first. Defaults to False.
        """
        self.check_context()
        logger.info(f"Sending keys: '{text}' (clear={clear})")
        try:
            self.android_context.send_keys(text, clear=clear)
            logger.info("Keys sent.")
        except Exception as e:
            logger.error(f"Failed to send keys '{text}': {e}")
            traceback.print_exc()

    def swipe(self, fx: float, fy: float, tx: float, ty: float, duration: float = 0.1):
        """
        Performs a swipe gesture from a starting point to an ending point.

        Args:
            fx (float): Starting x-coordinate.
            fy (float): Starting y-coordinate.
            tx (float): Ending x-coordinate.
            ty (float): Ending y-coordinate.
            duration (float): Duration of the swipe in seconds. Defaults to 0.1.
                              Lower values are faster swipes.
        """
        self.check_context()
        logger.info(f"Swiping from ({fx}, {fy}) to ({tx}, {ty}) in {duration}s")
        try:
            self.android_context.swipe(fx, fy, tx, ty, duration=duration)
            logger.info("Swipe action performed.")
        except Exception as e:
            logger.error(f"Failed to perform swipe: {e}")
            traceback.print_exc()

    def drag(self, sx: float, sy: float, ex: float, ey: float, duration: float = 1.0):
        """
        Performs a drag gesture (similar to swipe but typically slower) from a start point to an end point.

        Args:
            sx (float): Starting x-coordinate.
            sy (float): Starting y-coordinate.
            ex (float): Ending x-coordinate.
            ey (float): Ending y-coordinate.
            duration (float): Duration of the drag in seconds. Defaults to 1.0.
        """
        self.check_context()
        logger.info(f"Dragging from ({sx}, {sy}) to ({ex}, {ey}) in {duration}s")
        try:
            self.android_context.drag(sx, sy, ex, ey, duration=duration)
            logger.info("Drag action performed.")
        except Exception as e:
            logger.error(f"Failed to perform drag: {e}")
            traceback.print_exc()

    def push_file(self, src: Union[str, Path], dst: str, mode: int = 0o755):
        """
        Pushes a file or directory from the local machine to the Android device.

        Args:
            src (Union[str, Path]): Local path of the file or directory to push.
            dst (str): Destination path on the Android device.
            mode (int): File mode (permissions) for the pushed file on the device.
                        Defaults to 0o755 (rwxr-xr-x).
        """
        self.check_context()
        src_path = Path(src)  # Ensure it's a Path object for checking existence
        if not src_path.exists():
            logger.error(f"Source file/directory for push does not exist: {src}")
            raise FileNotFoundError(f"Source file/directory not found: {src}")
        logger.info(f"Pushing '{src}' to device path '{dst}' with mode {oct(mode)}")
        try:
            # uiautomator2's push method handles Path objects correctly
            push_result = self.android_context.push(src, dst, mode=mode)
            # The push method in u2/adbutils returns a result object/dict on success
            logger.info(f"File push completed. Result: {push_result}")
            # return push_result # You might want to return the result
        except Exception as e:
            logger.error(f"Failed to push file from '{src}' to '{dst}': {e}")
            traceback.print_exc()
            # raise

    def pull_file(self, src: str, dst: Union[str, Path]):
        """
        Pulls a file or directory from the Android device to the local machine.

        Args:
            src (str): Path of the file or directory on the Android device to pull.
            dst (Union[str, Path]): Local destination path. If it's a directory,
                                     the file/directory will be placed inside it.
        """
        self.check_context()
        dst_path = Path(dst)
        logger.info(f"Pulling device path '{src}' to local path '{dst_path}'")
        try:
            # Ensure the destination directory exists if dst is a file path
            if not dst_path.is_dir() and dst_path.parent:
                dst_path.parent.mkdir(parents=True, exist_ok=True)

            pull_result = self.android_context.pull(src, dst)
            # pull method returns the local destination path on success
            logger.info(f"File pull completed. Saved to: {pull_result}")
            # return pull_result # You might want to return the result path
        except Exception as e:
            # Catch specific errors like file not found on device if possible
            logger.error(f"Failed to pull file from '{src}' to '{dst_path}': {e}")
            traceback.print_exc()

    def shell(self, command: Union[str, List[str]], timeout: Optional[float] = 60.0) -> Optional[str]:
        """
        Executes a shell command on the connected Android device and returns its output.

        Args:
            command (Union[str, List[str]]): The command string or list of command arguments.
            timeout (Optional[float]): Maximum execution time in seconds. Defaults to 60.0.
                                       Set to None for no timeout.

        Returns:
            Optional[str]: The combined stdout and stderr output of the command as a string,
                           or None if the command fails or an error occurs.
        """
        self.check_context()
        cmd_str = command if isinstance(command, str) else " ".join(command)
        logger.info(f"Executing shell command: '{cmd_str}' (timeout={timeout}s)")
        try:
            # uiautomator2's shell returns a ShellResponse(output, returncode) namedtuple
            result = self.android_context.shell(command, timeout=timeout)
            output_str = result.output
            exit_code = result.exit_code
            return output_str

        except adbutils.AdbError as e:
            logger.error(f"Shell command ADB error for '{cmd_str}': {e}")
            traceback.print_exc()
            return None  # Return None on ADB specific errors
        except Exception as e:  # Catch other errors like timeouts
            logger.error(f"Shell command failed for '{cmd_str}': {e}")
            traceback.print_exc()
            return None  # Return None on general errors

    def swipe_ext(self, direction: Literal["left", "right", "up", "down"],
                  scale: float = 0.9,
                  box: Optional[Tuple[int, int, int, int]] = None,
                  **kwargs):
        """
        Wrapper for uiautomator2's built-in swipe_ext method.
        Performs a swipe gesture in a specified direction.

        Args:
            direction (Literal["left", "right", "up", "down"]): The direction to swipe.
            scale (float): Fraction of the screen/box dimension for swipe distance (default: 0.9).
            box (Optional[Tuple[int, int, int, int]]): Bounding box (x1, y1, x2, y2)
                                                     within which to swipe. If None, uses full screen.
            **kwargs: Additional keyword arguments passed directly to uiautomator2's
                      swipe_ext method (e.g., duration, steps).
        """
        self.check_context()
        action_desc = f"swipe_ext: direction='{direction}', scale={scale}"
        if box:
            action_desc += f", box={box}"
        if kwargs:
            action_desc += f", extra_args={kwargs}"
        logger.info(f"Performing {action_desc}")

        try:
            # Directly call the underlying uiautomator2 method
            self.android_context.swipe_ext(direction=direction, scale=scale, box=box, **kwargs)
            logger.info("Swipe_ext action performed successfully.")
        except Exception as e:
            logger.error(f"Swipe_ext action failed: {e}")
            traceback.print_exc()

    def launch_app(self, app_name: str, delay: float = 3.0) -> bool:
        """
        Launch an app by name.

        Args:
            app_name: The app name (must be in APP_PACKAGES).
            delay: Delay in seconds after launching. Defaults to 3.0.

        Returns:
            True if app was launched, False if app not found.
        """
        self.check_context()
        
        if app_name not in APP_PACKAGES:
            logger.error(f"App '{app_name}' not found in supported apps list.")
            return False

        package = APP_PACKAGES[app_name]
        logger.info(f"Launching app '{app_name}' (package: {package})")
        
        try:
            # Use shell command to launch app via monkey
            command = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
            result = self.shell(command, timeout=10.0)
            
            # Wait for the app to launch
            time.sleep(delay)
            logger.info(f"App '{app_name}' launched successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to launch app '{app_name}': {e}")
            traceback.print_exc()
            return False
