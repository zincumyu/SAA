import os
import dashscope
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
messages = [
{
    "role": "user",
    "content": [
    {"image": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/ctdzex/biaozhun.jpg"},
    {"text": "请仅输出图像中的文本内容。"}]
}]
response = dashscope.MultiModalConversation.call(
    #若没有配置环境变量， 请用百炼API Key将下行替换为： api_key ="sk-xxx"
    api_key = "sk-ws-H.RYYRLML.TR3w.MEUCIQDbJdlxVqgS1DnhyUWrf3fGF1GE68yiUSF3saefHSPV7wIgV17rBqWIcHFLIrczqm0QKxmohljyi0qKEtcvcB7SSIM",
    model = 'qwen-vl-max',
    messages = messages
)
print("start")
print(response.output.choices[0].message.content[0]["text"])
print("end")


