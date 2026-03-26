import requests
import json
import time

# ================= 配置区域 =================
# 如果你想在本地测试，用下面这行:
# BASE_URL = "http://127.0.0.1:8000"

# 如果你想通过公网测试（手机也能调通），用下面这行:
BASE_URL = "http://15437a6f.r40.cpolar.top"

print(f"🌍 正在连接后端服务器: {BASE_URL} ...")

# 全局 Session，自动处理 Cookie (虽然这里主要用 Token)
session = requests.Session()


def print_response(title, res):
    """美化打印响应结果"""
    print(f"\n--- {title} ---")
    print(f"状态码: {res.status_code}")
    try:
        # 尝试格式化 JSON 输出
        data = res.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except:
        print(res.text)
    return res.json() if res.status_code == 200 else None


# ================= 测试流程 =================

def run_test():
    test_email = "2642308874@qq.com"  # 生成唯一邮箱防止冲突
    test_password = "123456"

    # 1. 发送验证码
    print("\n[Step 1] 请求发送验证码...")
    # 注意：因为是模拟模式，验证码会打印在后端服务器的黑色控制台里！
    res = session.post(f"{BASE_URL}/api/auth/send-code", json={
        "email": test_email,
        "type": "register"
    })
    print_response("发送验证码结果", res)
    print("⚠️ 请去后端服务器控制台查看真实的验证码！")
    fake_code = input("👉 请输入后端控制台显示的验证码 (直接回车默认使用 888888 如果是纯模拟): ")
    if not fake_code:
        fake_code = "888888"  # 如果你的 auth_engine 有默认模拟码

    # 2. 用户注册
    print("\n[Step 2] 正在注册用户...")
    res = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": test_email,
        "password": test_password,
        "code": fake_code
    })
    data = print_response("注册结果", res)
    if not data:
        print("❌ 注册失败，停止测试。")
        return

    # 3. 用户登录
    print("\n[Step 3] 正在登录...")
    res = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    data = print_response("登录结果", res)
    if not data or "access_token" not in data:
        print("❌ 登录失败，停止测试。")
        return

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"✅ 登录成功，获取到 Token: {token[:20]}...")

    # 4. 创建日程 (模拟两个不同的用户数据，虽然当前接口没做用户隔离，但数据结构上是独立的)
    print("\n[Step 4] 创建日程数据 (作为匹配池)...")

    # 日程 A (我的档案)
    my_schedule = {
        "title": "我想找前端开发伙伴",
        "time_range": "14:00-16:00",
        "content": "我正在做一个基于 FastAPI 和 Vue 的项目，需要交流技术。"
    }

    # 日程 B (候选人 1 - 时间匹配，内容相关)
    candidate_1 = {
        "title": "前端工程师求职",
        "time_range": "14:30-15:30",
        "content": "精通 Vue 和 React，对后端接口设计也很感兴趣。"
    }

    # 日程 C (候选人 2 - 时间不匹配)
    candidate_2 = {
        "title": "下午在睡觉",
        "time_range": "19:00-21:00",
        "content": "晚上才有空，白天别找我。"
    }

    # 日程 D (候选人 3 - 时间匹配，内容无关)
    candidate_3 = {
        "title": "寻找饭搭子",
        "time_range": "14:00-15:00",
        "content": "中午想吃火锅，有人一起吗？完全不懂编程。"
    }

    # 先存入数据库 (模拟其他人已经发布了日程)
    candidates_data = [candidate_1, candidate_2, candidate_3]
    stored_candidates = []

    for i, cand in enumerate(candidates_data):
        res = session.post(f"{BASE_URL}/api/schedule/", json=cand, headers=headers)
        if res.status_code == 200:
            stored_candidates.append(res.json())
            print(f"   - 已存入候选人 {i + 1}: {cand['title']}")
        else:
            print(f"   - 存入候选人 {i + 1} 失败")

    # 5. 执行匹配 (核心测试)
    print("\n[Step 5] 执行智能匹配...")
    match_payload = {
        "my_profile": my_schedule,
        "candidates": candidates_data  # 直接发送数据测试匹配算法，不查库
    }

    res = session.post(f"{BASE_URL}/api/match", json=match_payload, headers=headers)
    data = print_response("匹配结果", res)

    if data and "matches" in data:
        matches = data["matches"]
        print(f"\n🎯 最终结论: 找到了 {len(matches)} 个匹配对象。")
        for m in matches:
            print(f"   - 匹配对象: {m['id']} (时间: {m['time']})")
            print(f"     内容摘要: {m['content'][:30]}...")

        # 简单验证逻辑
        ids = [m['id'] for m in matches]
        if "c0" in ids:  # candidate_1 应该被匹配
            print("✅ 逻辑正确：时间重叠且内容相关的 '前端工程师' 被成功匹配！")
        else:
            print("⚠️ 注意：预期的高匹配度用户未出现在首位，可能需要调整模型或权重。")

        if "c1" not in ids:  # candidate_2 (时间不重叠) 应该不被匹配
            print("✅ 逻辑正确：时间不重叠的 '睡觉党' 被成功过滤！")
        else:
            print("⚠️ 注意：时间不重叠的用户也被匹配了，需检查时间过滤逻辑。")

    else:
        print("❌ 匹配接口返回异常。")


if __name__ == "__main__":
    try:
        run_test()
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 错误：无法连接到 {BASE_URL}")
        print("请检查：1. 后端服务器是否运行？ 2. cpolar 隧道是否开启？ 3. 公网地址是否变更？")
    except Exception as e:
        print(f"\n❌ 发生未知错误: {e}")