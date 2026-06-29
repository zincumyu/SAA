import os
import dashscope

dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'


img_path = "backend\data\images\1_d3ba28346a1f.png"




messages = [
{
    "role": "user",
    "content": [
    {"image": img_path},
    {"text": "请分析这道错题："}]
}]

response = dashscope.MultiModalConversation.call(
    
    api_key = "sk-ws-H.RYYRLML.TR3w.MEUCIQDbJdlxVqgS1DnhyUWrf3fGF1GE68yiUSF3saefHSPV7wIgV17rBqWIcHFLIrczqm0QKxmohljyi0qKEtcvcB7SSIM",
    model = 'qwen-vl-max',
    messages = messages
)
print(response.output.choices[0].message.content[0]["text"])
