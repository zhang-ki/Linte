# 文件: client.py (客户端)
import requests
import json

# 接口地址
URL = "http://15437a6f.r40.cpolar.top/api/match"

# 准备数据 (格式必须和服务端定义的 Pydantic 模型一致)
payload = {
    "my_profile": {
        "id": "10",
        "time_range": "21:00-22:30",
        "content": "晚饭吃撑了，去河边散散步消食"
    },
    "candidates": [
        {"id": "1", "time_range": "21:00-22:30", "content": "吃太多了，正想去公园走走消食"},
        {"id": "2", "time_range": "21:00-22:00", "content": "晚上凉快，出来夜跑5公里，暴汗"},
        {"id": "3", "time_range": "06:00-07:00", "content": "早起晨跑"}  # 时间不匹配
    ]
}

try:
    print("📡 正在发送请求到服务器...")
    # 发送 POST 请求
    response = requests.post(URL, json=payload)

    # 检查状态码
    if response.status_code == 200:
        result = response.json()
        print("✅ 服务器返回成功!")
        print("匹配结果:", json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"❌ 请求失败，状态码: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"❌ 连接错误: {e}")
    print("提示：请确保 match.py (服务端) 已经启动并且正在运行！")