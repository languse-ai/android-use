import pdb
import sys
import uuid
import asyncio

sys.path.append(".")


async def test_controller():
    from android_use.tools.service import AndroidTools

    controller = AndroidTools()
    print(controller.registry.get_prompt_description())


if __name__ == '__main__':
    asyncio.run(test_controller())
