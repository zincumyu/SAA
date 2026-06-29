"""
AI 学习网站 - 后端主文件
启动：python run.py
"""
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from io import BytesIO
from pydantic import BaseModel
from pathlib import Path

# 导入数据库模块
from backend.database import (
    create_user, login_user, get_user_by_token,
    get_errorbook_items, add_errorbook_item,
    update_errorbook_item, delete_errorbook_item,
    save_analysis, get_analysis, delete_analysis, get_all_analyses,
    get_chat_sessions, get_session_messages,
    save_session_messages, delete_chat_session,
    DATA_DIR, IMAGES_DIR
)

# ---------- 1. 创建 App ----------
app = FastAPI(title="AI 学习平台", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 禁用前端文件缓存（开发用，上线后删除这行即可）
@app.middleware("http")
async def no_cache_for_frontend(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


# ==================== 认证依赖 ====================

def get_current_user(authorization: str = Header(None)):
    """
    从请求头 Authorization: Bearer <token> 中解析当前用户
    未登录或 token 无效 → 返回 401
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    token = authorization[7:]
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


# ==================== 数据模型 ====================

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

class ImageRequest(BaseModel):
    image_base64: str

class ErrorbookAddRequest(BaseModel):
    question: str
    answer: str = ""
    image_base64: str = None   # 可选，base64 编码的图片
    subject: str = ""

class ErrorbookUpdateRequest(BaseModel):
    question: str = None
    answer: str = None
    image_base64: str = None   # 空字符串 = 不变，"__DELETE__" = 删除图片
    subject: str = None
    keep_image: bool = True

class ChatSaveRequest(BaseModel):
    messages: list[dict]   # [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]

# pytest
class PythonRequest(BaseModel):
    code: str

# #数据处理返回
# @app.get("/api/pytest")
# async def list_plan(user: dict = Depends(get_current_user)):
#     # 查数据库...
#     return {"success": True, "items": []}

# @app.post("/api/pytest")
# async def create_plan(data: PythonRequest, user: dict = Depends(get_current_user)):
#     # 写入数据库...
#     return {"success": True, "item": {...}}





# ==================== 用户 API ====================
#5527
@app.post("/api/re_python")
async def re_python(data: PythonRequest):
    notice =f"python 运行成功,测试码111"
    return{"success": True, "item": notice}

@app.post("/api/register")
async def register(data: RegisterRequest):
    """注册新用户"""
    if not data.username or not data.password:
        return {"success": False, "error": "用户名和密码不能为空"}
    if len(data.username) < 2:
        return {"success": False, "error": "用户名至少 2 个字符"}
    if len(data.password) < 4:
        return {"success": False, "error": "密码至少 4 个字符"}

    user = create_user(data.username, data.password)
    if user is None:
        return {"success": False, "error": "用户名已存在"}
    return {
        "success": True,
        "token": user["token"],
        "username": user["username"],
        "message": "注册成功"
    }


@app.post("/api/login")
async def login(data: LoginRequest):
    """用户登录"""
    user = login_user(data.username, data.password)
    if user is None:
        return {"success": False, "error": "用户名或密码错误"}
    return {
        "success": True,
        "token": user["token"],
        "username": user["username"]
    }


@app.get("/api/user/info")
async def user_info(user: dict = Depends(get_current_user)):
    """获取当前用户信息（需要登录）"""
    return {"success": True, "username": user["username"]}


# ==================== AI API ====================

@app.post("/api/chat")
async def chat(data: ChatRequest):
    """AI 对话 - 接入 DeepSeek"""
    from openai import OpenAI
    client = OpenAI(
        api_key='sk-285c5ee870f84a40968ed72158f1fb01',
        base_url="https://api.deepseek.com"
    )
    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": "你是ASS系统助教机器人,请简洁回答高中学生的问题。"},
            {"role": "user", "content": data.message},
        ]
    )
    reply = response.choices[0].message.content
    return {"success": True, "reply": reply}


@app.post("/api/image-recognize")
async def image_recognize(data: ImageRequest):
    """AI 图片识别（骨架）"""
    reply = f"🖼️ 收到一张图片（{len(data.image_base64)} 字节）。\n\n识别功能待接入视觉模型。"
    return {"success": True, "reply": reply}


# ==================== 错题本 API（需要登录） ====================

@app.get("/api/errorbook")
async def list_errorbook(user: dict = Depends(get_current_user)):
    """获取当前用户的错题本列表"""
    items = get_errorbook_items(user["id"])
    # 把 image_path 转成可访问的 URL
    for item in items:
        if item.get("image_path"):
            item["image_url"] = f"/api/errorbook/image/{Path(item['image_path']).name}"
        else:
            item["image_url"] = None
        # 不返回原始路径
        item.pop("image_path", None)
    return {"success": True, "items": items}


@app.post("/api/errorbook")
async def create_errorbook(data: ErrorbookAddRequest, user: dict = Depends(get_current_user)):
    """添加一条错题"""
    if not data.question.strip():
        return {"success": False, "error": "题目内容不能为空"}
    item = add_errorbook_item(
        user_id=user["id"],
        question=data.question,
        answer=data.answer,
        image_base64=data.image_base64,
        subject=data.subject
    )
    if item is None:
        return {"success": False, "error": "添加失败"}
    # 转换图片路径
    if item.get("image_path"):
        item["image_url"] = f"/api/errorbook/image/{Path(item['image_path']).name}"
    item.pop("image_path", None)
    return {"success": True, "item": item}


@app.put("/api/errorbook/{item_id}")
async def edit_errorbook(item_id: int, data: ErrorbookUpdateRequest, user: dict = Depends(get_current_user)):
    """修改一条错题"""
    # 处理 image_base64 的特殊值
    image_base64 = data.image_base64
    keep_image = data.keep_image
    if image_base64 == "__DELETE__":
        image_base64 = None
        keep_image = False

    item = update_errorbook_item(
        item_id=item_id,
        user_id=user["id"],
        question=data.question,
        answer=data.answer,
        image_base64=image_base64 if image_base64 else None,
        subject=data.subject,
        keep_image=keep_image
    )
    if item is None:
        return {"success": False, "error": "错题不存在或无权修改"}
    if item.get("image_path"):
        item["image_url"] = f"/api/errorbook/image/{Path(item['image_path']).name}"
    item.pop("image_path", None)
    return {"success": True, "item": item}


@app.delete("/api/errorbook/{item_id}")
async def remove_errorbook(item_id: int, user: dict = Depends(get_current_user)):
    """删除一条错题"""
    ok = delete_errorbook_item(item_id, user["id"])
    if not ok:
        return {"success": False, "error": "错题不存在或无权删除"}
    return {"success": True, "message": "已删除"}


@app.get("/api/errorbook/image/{filename}")
async def get_errorbook_image(filename: str):
    """获取错题本的图片"""
    filepath = IMAGES_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(filepath)


# ==================== 错题 AI 分析 API ====================

def analyze_errorbook_item(item: dict) -> str:
    """
    【骨架函数】AI 分析错题 — 请在此接入你的 AI 模型
    
    接入步骤：
    1. 如果 item 有 image_path，从 backend/data/{image_path} 读取图片
    2. 将图片（base64 或二进制）发给视觉模型 API
    3. 结合 item['question']、item['answer']、item['subject'] 作为 prompt 上下文
    4. 返回 AI 生成的分析报告文本（支持 Markdown）
    
    参数:
        item: dict，包含 id, question, answer, image_path, subject 等字段
    
    返回:
        str: AI 分析报告
    """
    # ────────────── 在此补充你的 AI 调用逻辑 ──────────────
    # 示例代码（取消注释后接入）：
    # from openai import OpenAI
    # import base64
    # client = OpenAI(api_key="sk-xxx", base_url="https://api.deepseek.com")
    #
    # # 读取图片
    # image_b64 = ""
    # if item.get("image_path"):
    #     img_path = DATA_DIR / item["image_path"]
    #     if img_path.exists():
    #         image_b64 = base64.b64encode(img_path.read_bytes()).decode()
    #
    # # 构建分析 prompt
    # prompt = f"请分析这道错题：\n题目：{item['question']}\n答案：{item.get('answer','')}\n科目：{item.get('subject','')}"
    # response = client.chat.completions.create(
    #     model="deepseek-v4-pro",
    #     messages=[{"role": "user", "content": prompt}]
    # )
    # return response.choices[0].message.content
    # ──────────────────────────────────────────────────────
    #test
    import dashscope
    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

    if item.get("image_path"):
        img_path = DATA_DIR / item["image_path"]
        print(img_path)
    messages = [
    {
        "role": "user",
        "content": [
        {"image": f"{img_path}"},
        {"text": f"快速请分析这道错题：\n题目：{item['question']}\n答案：{item.get('answer','')}\n科目：{item.get('subject','')}"}]
    }]

    response = dashscope.MultiModalConversation.call(
        
        api_key = "sk-ws-H.RYYRLML.TR3w.MEUCIQDbJdlxVqgS1DnhyUWrf3fGF1GE68yiUSF3saefHSPV7wIgV17rBqWIcHFLIrczqm0QKxmohljyi0qKEtcvcB7SSIM",
        model = 'qwen-vl-max',
        messages = messages
    )
    return response.output.choices[0].message.content[0]["text"]
    #testqw
    # 占位返回（接入 AI 后删除这段）
    # lines = [f"## 📊 错题分析报告"]
    # lines.append(f"\n**题目**：{item['question']}")
    # if item.get("answer"):
    #     lines.append(f"\n**当前答案**：{item['answer']}")
    # if item.get("subject"):
    #     lines.append(f"\n**科目**：{item['subject']}")
    # if item.get("image_path"):
    #     lines.append(f"\n**配图**：已上传")
    # lines.append(f"\n---")
    # lines.append(f"\n> ⚠️ **AI 分析功能待接入**")
    # lines.append(f"> 请在 `backend/main.py` 的 `analyze_errorbook_item()` 函数中补充视觉模型调用逻辑。")
    # lines.append(f"> 图片路径：`backend/data/{item.get('image_path', '无')}`")
    # return "\n".join(lines)


@app.post("/api/errorbook/{item_id}/analyze")
async def trigger_analysis(item_id: int, user: dict = Depends(get_current_user)):
    """
    触发单条错题的 AI 分析
    调用 analyze_errorbook_item()，结果存入数据库并返回
    """
    # 先获取错题信息，确认是本人数据
    items = get_errorbook_items(user["id"])
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="错题不存在")

    # 调用 AI 分析（骨架函数）
    analysis_text = analyze_errorbook_item(item)

    # 保存到数据库
    analysis = save_analysis(item_id, user["id"], analysis_text)
    if analysis is None:
        return {"success": False, "error": "保存分析报告失败"}

    return {
        "success": True,
        "analysis": {
            "id": analysis["id"],
            "text": analysis["analysis_text"],
            "created_at": analysis["created_at"]
        }
    }


@app.get("/api/errorbook/{item_id}/analysis")
async def get_errorbook_analysis(item_id: int, user: dict = Depends(get_current_user)):
    """
    获取某条错题的 AI 分析报告 + 错题详情
    """
    items = get_errorbook_items(user["id"])
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="错题不存在")

    # 转换图片路径
    if item.get("image_path"):
        item["image_url"] = f"/api/errorbook/image/{Path(item['image_path']).name}"
    item.pop("image_path", None)

    analysis = get_analysis(item_id, user["id"])

    return {
        "success": True,
        "item": item,
        "analysis": {
            "id": analysis["id"],
            "text": analysis["analysis_text"],
            "created_at": analysis["created_at"]
        } if analysis else None
    }


@app.delete("/api/errorbook/{item_id}/analysis")
async def remove_analysis(item_id: int, user: dict = Depends(get_current_user)):
    """删除某条错题的 AI 分析报告"""
    ok = delete_analysis(item_id, user["id"])
    if not ok:
        return {"success": False, "error": "错题不存在"}
    return {"success": True, "message": "分析报告已删除"}


@app.get("/api/analyses")
async def list_all_analyses(user: dict = Depends(get_current_user)):
    """
    获取当前用户所有 AI 分析报告列表（含错题摘要信息）
    """
    analyses = get_all_analyses(user["id"])
    for a in analyses:
        if a.get("image_path"):
            a["image_url"] = f"/api/errorbook/image/{Path(a['image_path']).name}"
        a.pop("image_path", None)
    return {"success": True, "items": analyses}


# ==================== 对话会话保存与导出 API ====================

class ChatSaveRequest(BaseModel):
    session_id: int = 0       # 0 = 新建会话
    messages: list[dict]      # [{"role":"user","content":"..."}, ...]
    title: str = None         # 可选，首次保存时自动从首条消息截取

@app.post("/api/chat/save")
async def save_chat(data: ChatSaveRequest, user: dict = Depends(get_current_user)):
    """
    保存消息到指定会话（session_id=0 则自动新建会话）
    返回 session_id
    """
    if not data.messages:
        return {"success": False, "error": "消息列表为空"}
    sid = save_session_messages(user["id"], data.session_id, data.messages, data.title)
    if sid == 0:
        return {"success": False, "error": "保存失败"}
    return {"success": True, "session_id": sid}


@app.get("/api/chat/sessions")
async def list_chat_sessions(user: dict = Depends(get_current_user)):
    """获取当前用户的所有会话列表"""
    sessions = get_chat_sessions(user["id"])
    return {
        "success": True,
        "sessions": [{"id": s["id"], "title": s["title"], "created_at": s["created_at"], "updated_at": s["updated_at"]} for s in sessions]
    }


@app.get("/api/chat/sessions/{session_id}")
async def load_session(session_id: int, user: dict = Depends(get_current_user)):
    """加载指定会话的全部消息"""
    messages = get_session_messages(session_id, user["id"])
    return {
        "success": True,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages]
    }


@app.delete("/api/chat/sessions/{session_id}")
async def remove_session(session_id: int, user: dict = Depends(get_current_user)):
    """删除指定会话及其全部消息"""
    ok = delete_chat_session(session_id, user["id"])
    if not ok:
        return {"success": False, "error": "会话不存在"}
    return {"success": True, "message": "已删除"}


@app.get("/api/chat/sessions/{session_id}/export")
async def export_session(session_id: int, user: dict = Depends(get_current_user)):
    """导出指定会话为 .md 文件下载"""
    messages = get_session_messages(session_id, user["id"])
    if not messages:
        return {"success": False, "error": "会话无消息"}

    lines = [f"# AI 对话记录", f"", f"**用户**：{user['username']}", f"**导出时间**：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}", f"", f"---", f""]
    for m in messages:
        role_label = "👤 用户" if m["role"] == "user" else "🤖 AI助教"
        lines.append(f"### {role_label}")
        lines.append(f"")
        lines.append(m["content"])
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
    text = "\n".join(lines)
    filename = f"AI对话_{session_id}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')}.md"
    return StreamingResponse(
        BytesIO(text.encode("utf-8")),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{__import__('urllib.parse').quote(filename)}"}
    )


@app.get("/api/errorbook/{item_id}/analysis/export")
async def export_analysis(item_id: int, user: dict = Depends(get_current_user)):
    """导出 AI 分析报告为 .md 文件下载"""
    items = get_errorbook_items(user["id"])
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="错题不存在")

    analysis = get_analysis(item_id, user["id"])
    if not analysis:
        return {"success": False, "error": "该错题暂无分析报告"}

    lines = [f"# 📊 错题分析报告", f""]
    lines.append(f"**题目**：{item['question']}")
    if item.get("answer"):
        lines.append(f"**答案**：{item['answer']}")
    if item.get("subject"):
        lines.append(f"**科目**：{item['subject']}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(analysis["analysis_text"])
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*分析时间：{analysis['created_at']}*")

    text = "\n".join(lines)
    safe_title = item['question'][:20].replace(' ', '_').replace('/', '_')
    filename = f"错题分析_{safe_title}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')}.md"
    return StreamingResponse(
        BytesIO(text.encode("utf-8")),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{__import__('urllib.parse').quote(filename)}"}
    )


# ==================== 健康检查 ====================

@app.get("/api/health")
async def health():
    return {"status": "ok", "db": str(DATA_DIR / "saa.db")}


# ==================== 挂载前端（必须放最后） ====================
frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    print(f"✅ 前端目录已挂载: {frontend_path}")
