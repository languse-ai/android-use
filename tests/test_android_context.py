import sys
import uuid

sys.path.append(".")


def test_take_screenshot_and_xml() -> None:
    import adbutils
    from android_use.android.context import AndroidContext, AndroidContextConfig
    from android_use import utils

    android_devices = adbutils.adb.device_list()
    device_id = android_devices[0].serial
    config = AndroidContextConfig(
        highlight_elements=True,
        device_id=device_id
    )
    android_context = AndroidContext(config)
    screenshot = android_context.take_screenshot()
    xml = android_context.get_xml()
    root_dom_node = android_context.parse_xml(xml)
    selector_map = android_context.get_selector_map(root_dom_node)
    xml_description = android_context.get_all_elements_description(selector_map)
    screenshot_highlight = android_context.highlight_screenshot(screenshot, selector_map)
    task_id = str(uuid.uuid4())
    screenshot_save_path = f"./tmp/android_{device_id}/{task_id}.png"
    highlight_screenshot_save_path = f"./tmp/android_{device_id}/{task_id}-highlight.png"
    xml_save_path = f"./tmp/android_{device_id}/{task_id}.xml"
    utils.save_base64_to_file(screenshot, screenshot_save_path)
    utils.save_base64_to_file(screenshot_highlight, highlight_screenshot_save_path)
    utils.save_xml_to_file(xml, xml_save_path)
    print(xml_description)
    print(screenshot_save_path)
    print(len(selector_map))


def test_action():
    import adbutils
    from android_use.android.context import AndroidContext, AndroidContextConfig

    android_devices = adbutils.adb.device_list()
    device_id = android_devices[0].serial
    config = AndroidContextConfig(
        highlight_elements=True,
        device_id=device_id
    )
    android_context = AndroidContext(config)

    # android_context.press("home")
    # android_context.swipe_ext("right")
    # android_context.send_keys("hello world")
    output_stdout = android_context.shell(command="ls -lh")
    print(output_stdout)

if __name__ == '__main__':
    test_take_screenshot_and_xml()
    # test_action()
