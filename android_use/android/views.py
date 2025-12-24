from typing import List, Any
import logging
from functools import cached_property
from dataclasses import dataclass, field
from typing import Optional
import re
import hashlib

from android_use.utils import time_execution_sync

logger = logging.getLogger(__name__)


class DOMElementNode: pass  # Forward declaration for type hinting


@dataclass(frozen=False)
class DOMBaseNode:
    parent: Optional[DOMElementNode] = None
    bounding_box: Optional[List[float]] = None  # Bounding box [x1, y1, x2, y2]

    @staticmethod
    def _parse_bounds(bounds_str: Optional[str]) -> Optional[List[float]]:
        """
        Parses the bounds string "[x1,y1][x2,y2]" from XML into a list of floats.

        Args:
            bounds_str: The bounds string obtained from the XML attribute.

        Returns:
            A list containing four floats [x1, y1, x2, y2], or None if parsing fails.
        """
        if not bounds_str:
            return None
        try:
            # Use regex to match bounds format, strip potential leading/trailing whitespace
            match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str.strip())
            if match:
                x1, y1, x2, y2 = map(float, match.groups())
                # Basic validation: ensure x1 <= x2 and y1 <= y2
                if x1 <= x2 and y1 <= y2:
                    return [x1, y1, x2, y2]
                else:
                    # If coordinate order is incorrect, log a warning
                    logging.warning(f"Invalid bounds order detected: {bounds_str}")
                    return None  # Or handle as appropriate
        except (ValueError, IndexError):
            # If converting numbers or indexing fails, log a warning
            logging.warning(f"Failed to parse bounds string: {bounds_str}")
            pass
        return None


# --- Node Type Constants ---
NODE_TYPE_INTERACTIVE = 'INTERACTIVE_NODE'  # Interactive node
NODE_TYPE_NON_INTERACTIVE = 'NON_INTERACTIVE_NODE'  # Non-interactive node (no text)
NODE_TYPE_TEXT = 'TEXT_NODE'  # Text node (non-interactive but has text or content-desc)


@dataclass
class DOMHistoryElement:
    highlight_index: Optional[int]
    node_type: str = ""
    xpath: str = ""
    text: str = ""
    node_index: str = ""
    package: str = ""
    class_name: str = ""
    resource_id: str = ""

    def to_dict(self) -> dict:
        return {
            "highlight_index": self.highlight_index,
            'node_type': self.node_type,
            'text': self.text,
            'xpath': self.xpath,
            'node_index': self.node_index,
            'package': self.package,
            'class_name': self.class_name,
            'resource_id': self.resource_id
        }


@dataclass(frozen=False)
class DOMElementNode(DOMBaseNode):
    # Node basic info
    text: str = ""  # text attribute
    node_type: str = 'INTERACTIVE_NODE'  # Node type (Interactive, Non-interactive, Text)

    # XML attribute mapping
    node_index: str = ""  # 'index' attribute from XML (string form)
    package: str = ""  # package attribute
    class_name: str = ""  # class attribute
    resource_id: str = ""  # resource-id attribute

    children: List[DOMElementNode] = field(default_factory=list)  # List of child nodes

    def convert_dom_element_to_history_element(self, highlight_index: Optional[int] = None) -> DOMHistoryElement:
        return DOMHistoryElement(
            highlight_index=highlight_index,
            node_type=self.node_type,
            node_index=self.node_index,
            package=self.package,
            class_name=self.class_name,
            resource_id=self.resource_id,
            xpath=self.get_xpath,
            text=self.text,
        )

    @cached_property
    def get_xpath(self) -> str:
        """
        Computes and returns the absolute XPath for this node.
        The path is constructed based on the node tag 'node' and the 'index' attribute from the XML.
        Assumes the root element is <hierarchy>.

        Args:
            use_cache (bool): Whether to use the cached XPath if previously computed. Defaults to True.

        Returns:
            str: The XPath string for the node.

        Raises:
            ValueError: If the node's 'node_index' attribute is invalid or missing,
                        preventing XPath calculation.
        """
        components = []  # To store the parts of the XPath
        current_node = self  # Start backtracking from the current node
        while current_node is not None:
            try:
                step = f"node[{current_node.node_index}]"
            except Exception as e:
                logging.debug(f"Failed to compute XPath for node {current_node}: {e}")
                continue
            components.insert(0, step)  # Build path from end to start, so insert at the beginning of the list
            current_node = current_node.parent  # Move to the parent node

        # Assume XML always starts with <hierarchy> as the root tag
        full_xpath = "/hierarchy/" + "/".join(components)
        return full_xpath

    @cached_property
    def hash(self) -> str:
        return hashlib.sha256(self.get_xpath.encode()).hexdigest()

    def get_all_text_till_next_clickable_element(self, max_depth: int = -1) -> str:
        text_parts = []

        def collect_text(node: DOMBaseNode, current_depth: int) -> None:
            if max_depth != -1 and current_depth > max_depth:
                return

            # Skip this branch if we hit a highlighted element (except for the current node)
            if isinstance(node, DOMElementNode) and node != self and node.node_type == NODE_TYPE_INTERACTIVE:
                return

            if node.text.strip() not in text_parts:
                text_parts.append(node.text.strip())

            if len(node.children) > 1:
                return

            for child in node.children:
                collect_text(child, current_depth + 1)

        collect_text(self, 0)
        return '\n'.join(text_parts).strip()

    @cached_property
    def has_parent_with_interactive_node(self) -> bool:
        current = self.parent
        while current is not None and len(current.children) <= 1:
            # stop if the element has a highlight index (will be handled separately)
            if current.node_type == NODE_TYPE_INTERACTIVE:
                return True

            current = current.parent
        return False


SelectorMap = dict[int, DOMElementNode]


@dataclass
class DOMState:
    element_tree: Optional[DOMElementNode] = None
    selector_map: Optional[SelectorMap] = field(default_factory=dict)


@dataclass
class AndroidState(DOMState):
    device_id: Optional[str] = None
    timestamp: Optional[str] = None
    element_description: Optional[str] = None
    xml: Optional[str] = None
    screenshot: Optional[str] = None
    highlight_screenshot: Optional[str] = None


@dataclass
class AndroidStateHistory:
    device_id: Optional[str] = None
    timestamp: Optional[str] = None
    element_description: Optional[str] = None
    xml: Optional[str] = None
    screenshot: Optional[str] = None
    highlight_screenshot: Optional[str] = None
    interacted_element: list[DOMHistoryElement | None] | list[None] = field(default_factory=list)


    def to_dict(self) -> dict[str, Any]:
        data = {}
        data['device_id'] = self.device_id
        data['screenshot'] = self.screenshot
        data['highlight_screenshot'] = self.highlight_screenshot
        data['element_description'] = self.element_description
        data['xml'] = self.xml
        data['timestamp'] = self.timestamp
        data['interacted_element'] = [el.to_dict() if el else None for el in self.interacted_element]
        return data
