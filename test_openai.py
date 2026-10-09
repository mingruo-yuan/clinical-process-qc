from openai import OpenAI

# 简单封装的函数，用于调用便携AI聚合API接口获取聊天回复

def test():
    """使用OpenAI Python客户端调用聚合API，询问鲁迅和周树人的关系。

    返回:
        模型返回的文本答案
    """
    client = OpenAI(
        api_key="sk-Jes26i5ACUW3wAQ1bRd03FOBPnFYGuFZmYZzzkBM7BRybpd3",
        base_url="https://api.bianxie.ai/v1"  # 替换为聚合API的入口地址
    )

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": "鲁迅和周树人是什么关系？"}
        ]
    )

    # 提取并返回模型的第一条消息
    # ChatCompletionMessage is an object; access its content attribute
    return completion.choices[0].message.content


if __name__ == "__main__":

    answer = test()
    print("模型回复:", answer)