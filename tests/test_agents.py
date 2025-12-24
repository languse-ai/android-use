import sys
import uuid
import asyncio
import os

sys.path.append(".")


async def test_android_use_agent():
    import adbutils
    import time
    from android_use.android.context import AndroidContext, AndroidContextConfig
    from android_use import utils
    from android_use.agent.service import AndroidUseAgent
    from android_use.llm.openai_compatible.chat import ChatOpenAICompatible
    from android_use.agent.views import AgentSettings, AgentStepInfo, StepMetadata
    from android_use.android.context import AndroidContext
    from android_use.tools.service import AndroidTools

    android_devices = adbutils.adb.device_list()
    device_id = android_devices[0].serial
    config = AndroidContextConfig(
        highlight_elements=True,
        device_id=device_id
    )
    android_context = AndroidContext(config)

    # llm = ChatOpenAICompatible(model="gemini-3-flash-preview", base_url=os.getenv("OPENAI_ENDPOINT"),
    #                            api_key=os.getenv("OPENAI_API_KEY"))

    llm = ChatOpenAICompatible(model="deepseek-chat", base_url=os.getenv("DEEPSEEK_ENDPOINT"),
                               api_key=os.getenv("DEEPSEEK_API_KEY"))

    llm = ChatOpenAICompatible(model="kimi-k2-thinking", base_url=os.getenv("MOONSHOT_ENDPOINT"),
                               api_key=os.getenv("MOONSHOT_API_KEY"))
    use_vision = False

    agent_output_dir = f"./tmp/agent_outputs/{time.time()}"
    os.makedirs(agent_output_dir, exist_ok=True)
    agent_settings = AgentSettings(
        generate_gif=os.path.join(agent_output_dir, "agent_history.gif"),
        use_vision=use_vision,
    )

    agent = AndroidUseAgent(agent_settings=agent_settings, llm=llm, android_context=android_context)

    task = "打开高德地图，导航到南锣鼓巷"
    # task = "打开抖音，去商城搜索安踏篮球鞋，获取前10的商品信息"
    task = "打开小红书，搜索browser-use，选择当前页面点赞数最多的帖子，点赞和发表一个简洁的像真人的评论，最后总结这个帖子的核心内容"
    # task = "打开微信，去视频号搜索豆包手机, 获取选择当前页面点赞数最多的视频的所有评论，分享这个视频给Vincent, 并发送总结的评论内容"
    # task = "打开美团外卖，帮我点一杯瑞幸的冰美式，选择送到北京大学30号楼学生公寓"
    # task = "打开京东搜索苹果手机17，点击进去第2个商品，获取它第一页的评论"
    task = "打开抖音，持续的刷视频，刷到觉得有意思的，点赞，至少点赞5个视频才能停下。"
    agent_result = await agent.run(task)
    agent_result.save_to_file(os.path.join(agent_output_dir, "result.json"))


if __name__ == '__main__':
    asyncio.run(test_android_use_agent())
