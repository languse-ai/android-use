import asyncio
import os
import sys

sys.path.append(".")


async def test_openai_llm():
    from android_use.llm.openai.chat import ChatOpenAI
    from android_use.llm import SystemMessage, UserMessage, AssistantMessage

    llm = ChatOpenAI(model="gemini-3-flash-preview", base_url=os.getenv("OPENAI_ENDPOINT"),
                     api_key=os.getenv("OPENAI_API_KEY"))
    chat_messages = [SystemMessage(content="you are a helpful AI assistant"),
                     UserMessage(content="do you like my project name: android-use?")]
    response_message = await llm.ainvoke(chat_messages)
    print(response_message)


if __name__ == '__main__':
    asyncio.run(test_openai_llm())
