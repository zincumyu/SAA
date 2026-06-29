"""
一键启动脚本
    python run.py
启动后访问: http://localhost:8000
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,          # 代码改动自动重载
    )
