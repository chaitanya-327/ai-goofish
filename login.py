import asyncio
from playwright.async_api import async_playwright

# 定义保存登录状态的文件路径
STATE_FILE = "xianyu_state.json"

async def main():
    async with async_playwright() as p:
        # 启动一个非无头浏览器，这样你才能看到界面并操作
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # 打开闲鱼首页，通常会自动跳转到登录页面或显示登录入口
        await page.goto("https://www.goofish.com/")

        print("\n" + "="*50)
        print("请在打开的浏览器窗口中手动登录您的闲鱼账号。")
        print("推荐使用APP扫码登录。")
        print("登录成功后，回到这里，按 Enter 键继续...")
        print("="*50 + "\n")

        # --- 这是修改的部分 ---
        # 使用 loop.run_in_executor 来替代 asyncio.to_thread，以兼容 Python 3.8
        loop = asyncio.get_running_loop()
        # The first argument 'None' tells it to use the default thread pool executor.
        # The second argument is the blocking function to run.
        await loop.run_in_executor(None, input)
        # --- 修改结束 ---

        # 用户确认登录后，保存当前上下文的存储状态到文件
        # 这会保存 Cookies, localStorage 等信息
        await context.storage_state(path=STATE_FILE)

        print(f"登录状态已成功保存到文件: {STATE_FILE}")
        await browser.close()

if __name__ == "__main__":
    print("正在启动浏览器以进行登录...")
    asyncio.run(main())