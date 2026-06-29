"""Test koneksi dan publish ke WordPress REST API."""
import asyncio
import base64
import os
import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv()

import httpx

async def test():
    wp_url   = os.environ.get("WP_URL", "").rstrip("/")
    wp_user  = os.environ.get("WP_USERNAME", "")
    wp_pass  = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "")

    print(f"URL      : {wp_url}")
    print(f"Username : {wp_user}")
    print(f"Password : {'*' * len(wp_pass)} ({len(wp_pass)} chars)")
    print()

    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    # Try both HTTPS and HTTP
    base_urls = []
    if wp_url.startswith("https://"):
        base_urls = [wp_url, wp_url.replace("https://", "http://", 1)]
    else:
        base_urls = [wp_url]

    working_url = None
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:

        for base in base_urls:
            api = f"{base}/wp-json/wp/v2/"
            print(f"Testing: {api}")
            try:
                r = await client.get(api, headers=headers)
                print(f"  Status: {r.status_code}")
                if r.status_code == 200:
                    print("  ✓ REST API aktif")
                    working_url = base
                    break
                else:
                    print(f"  Body: {r.text[:100]}")
            except Exception as e:
                print(f"  Error: {type(e).__name__}: {str(e)[:80]}")

        if not working_url:
            print("\n✗ Tidak bisa terhubung ke WordPress")
            return

        # Cek auth
        print(f"\nCek autentikasi di {working_url}...")
        r = await client.get(f"{working_url}/wp-json/wp/v2/users/me", headers=headers)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"✓ Login sebagai: {data.get('name')} | Roles: {data.get('roles')}")
        else:
            print(f"✗ Auth gagal: {r.text[:200]}")
            return

        # Buat draft test
        print("\nMembuat draft test post...")
        payload = {
            "title": "[TEST] SEO Agent Draft",
            "content": "<p>Test post dari SEO Agent. Boleh dihapus.</p>",
            "excerpt": "Test post dari SEO Agent.",
            "status": "draft",
        }
        r = await client.post(f"{working_url}/wp-json/wp/v2/posts", json=payload, headers=headers)
        print(f"Status: {r.status_code}")
        if r.status_code in (200, 201):
            data = r.json()
            print(f"✓ BERHASIL! Post ID: {data.get('id')} | URL: {data.get('link')}")
            print(f"\nSilakan cek di WordPress Dashboard > Posts > Drafts")

            # Hapus test post
            pid = data.get('id')
            r2 = await client.delete(f"{working_url}/wp-json/wp/v2/posts/{pid}?force=true", headers=headers)
            if r2.status_code == 200:
                print(f"(Test post sudah dihapus otomatis)")
        else:
            print(f"✗ Gagal: {r.text[:300]}")
            return

    print(f"\n{'='*50}")
    print(f"WordPress SIAP digunakan!")
    print(f"Working URL: {working_url}")
    print(f"Update WP_URL di .env ke: {working_url}")

asyncio.run(test())
