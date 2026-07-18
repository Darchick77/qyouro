import os
import sys
import threading

# On Render, backend is on localhost
if "RENDER" in os.environ or "PORT" in os.environ:
    port = int(os.environ.get("PORT", 10000))
    os.environ["BACKEND_URL"] = f"http://localhost:{port}"
    os.environ["VK_BOT_TOKEN"] = os.environ.get("VK_BOT_TOKEN",
        "vk1.a.XAtzQqIzwir3KAup14kHfScscxpWcPP9fxz0o6YjMyTX9BSwlto2EsDWnUzy5z9ETw9T7pZhEuUOnLGARBRXxi-GxW_3tOMeELhK3yhJKvcrIvobfIN3VQaduQ7MSUZXLFQ9_SL6av07byLTH9uhEbwUujC_9OkHFQCFo42sMdb4BCbJQ-s9izX5n2e1ls0FbX7WA8BATNNeZu1wvcSWlQ")

# Add backend dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

def start_bot():
    bot_dir = os.path.join(os.path.dirname(__file__), "bot")
    sys.path.insert(0, bot_dir)
    from bot_core import run_bot
    run_bot()


if __name__ == "__main__":
    import uvicorn

    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    print("[Qyouro] Bot started in background")

    port = int(os.environ.get("PORT", 10000))
    print(f"[Qyouro] Web server starting on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
