"""
Playwright 自动化测试脚本
用于测试前端功能
"""

import asyncio
from playwright.async_api import async_playwright


async def test_browser_open():
    """测试：打开浏览器并访问一个网页"""
    async with async_playwright() as p:
        # 连接到本地已安装的 Edge 浏览器
        context = await p.chromium.launch_persistent_context(
            user_data_dir=None,  # 使用默认配置
            headless=False,
            channel="msedge"  # 使用 Edge 浏览器
        )

        # 获取或创建页面
        if not context.pages:
            page = await context.new_page()
        else:
            page = context.pages[0]

        # 访问百度
        print("正在访问百度...")
        await page.goto("https://www.baidu.com")
        print(f"页面标题: {await page.title()}")

        # 截图
        await page.screenshot(path="baidu_screenshot.png")
        print("截图已保存: baidu_screenshot.png")

        # 关闭浏览器
        await context.close()
        print("[OK] 测试完成！")


async def test_local_frontend():
    """测试：访问本地前端页面"""
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            headless=False,
            channel="msedge"
        )

        if not context.pages:
            page = await context.new_page()
        else:
            page = context.pages[0]

        # 访问本地前端
        print("正在访问本地前端...")
        await page.goto("file:///C:/Users/20708/PycharmProjects/AIRAG/main_project/frontend/index.html")
        print(f"页面标题: {await page.title()}")

        # 截图
        await page.screenshot(path="local_frontend_screenshot.png")
        print("截图已保存: local_frontend_screenshot.png")

        await context.close()
        print("[OK] 本地前端测试完成！")


async def test_form_interaction():
    """测试：表单交互（模拟输入和点击）"""
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            headless=False,
            channel="msedge"
        )

        if not context.pages:
            page = await context.new_page()
        else:
            page = context.pages[0]

        # 访问百度
        await page.goto("https://www.baidu.com")

        # 找到搜索框并输入
        await page.fill("input#kw", "Playwright 自动化测试")
        print("✓ 已输入搜索内容")

        # 截图
        await page.screenshot(path="form_interaction_screenshot.png")

        await context.close()
        print("[OK] 表单交互测试完成！")


if __name__ == "__main__":
    print("=" * 50)
    print("Playwright 自动化测试")
    print("=" * 50)

    # 选择要运行的测试
    print("\n可选测试:")
    print("1. 打开浏览器并访问百度")
    print("2. 访问本地前端页面")
    print("3. 表单交互测试")

    # 运行测试1
    asyncio.run(test_browser_open())