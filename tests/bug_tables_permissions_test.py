"""
Focused Playwright verification script for bug: Mesas management buttons/actions
must appear for SUPERADMIN and ADMIN, and must not appear for waiter.

This file documents the exact browser automation run through mcp_browser_automation.
It expects an async Playwright `page` object and targets the preview URL.
"""

async def run(page):
    import re

    base_url = "https://digital-orders-3.preview.emergentagent.com"
    roles = {
        "superadmin": ("ygor@gestorresto.com", "87yOY4f@"),
        "admin": ("admin@teste.com", "123456"),
        "waiter": ("garcom@digitalcodex.com", "garcom123"),
    }

    await page.set_viewport_size({"width": 1920, "height": 1080})

    async def clean_browser_state():
        await page.goto(base_url + "/login", wait_until="domcontentloaded")
        await page.evaluate("""async () => {
          localStorage.clear(); sessionStorage.clear();
          if ('caches' in window) {
            const keys = await caches.keys();
            await Promise.all(keys.map(k => caches.delete(k)));
          }
          if (navigator.serviceWorker) {
            const regs = await navigator.serviceWorker.getRegistrations();
            await Promise.all(regs.map(r => r.unregister()));
          }
        }""")

    async def login(email, password):
        await clean_browser_state()
        await page.goto(base_url + "/login", wait_until="networkidle")
        await page.locator('[data-testid="login-email"]').fill(email)
        await page.locator('[data-testid="login-password"]').fill(password)
        await page.locator('[data-testid="login-submit"]').click()
        await page.wait_for_load_state("networkidle")
        await page.goto(base_url + "/tables", wait_until="networkidle")
        await page.locator('[data-testid="tables-page"]').wait_for(timeout=15000)

    async def create_and_delete_table(role_name, table_number):
        await page.locator('[data-testid="new-table-btn"]').wait_for(timeout=10000)
        assert await page.locator('[data-testid="new-table-btn"]').is_visible()
        await page.locator('[data-testid="new-table-btn"]').click()
        await page.locator('[data-testid="new-table-dialog"]').wait_for(timeout=5000)
        assert await page.locator('[data-testid="new-table-number-input"]').is_visible()
        assert await page.locator('[data-testid="new-table-seats-input"]').is_visible()
        async with page.expect_response(lambda r: "/api/tables" in r.url and r.request.method == "POST") as post_info:
            await page.locator('[data-testid="new-table-number-input"]').fill(str(table_number))
            await page.locator('[data-testid="new-table-seats-input"]').fill("2")
            await page.locator('[data-testid="save-new-table-btn"]').click()
        post_response = await post_info.value
        assert post_response.status in (200, 201), f"{role_name} create status {post_response.status}"
        await page.locator(f'[data-testid="table-{table_number}"]').wait_for(timeout=10000)
        await page.locator(f'[data-testid="delete-table-{table_number}"]').wait_for(timeout=10000)
        assert await page.locator(f'[data-testid="delete-table-{table_number}"]').is_visible()

        page.once("dialog", lambda dialog: dialog.accept())
        async with page.expect_response(lambda r: "/api/tables/" in r.url and r.request.method == "DELETE") as delete_info:
            await page.locator(f'[data-testid="delete-table-{table_number}"]').click(force=True)
        delete_response = await delete_info.value
        assert delete_response.status == 200, f"{role_name} delete status {delete_response.status}"
        await page.locator(f'[data-testid="table-{table_number}"]').wait_for(state="detached", timeout=10000)

    # Superadmin full create/delete UI flow
    await login(*roles["superadmin"])
    await create_and_delete_table("superadmin", 97001)

    # Admin sees and can use the same actions
    await login(*roles["admin"])
    await create_and_delete_table("admin", 97002)

    # Waiter can access tables but cannot see management buttons
    await login(*roles["waiter"])
    assert await page.locator('[data-testid="new-table-btn"]').count() == 0
    assert await page.locator('[data-testid^="delete-table-"]').count() == 0
