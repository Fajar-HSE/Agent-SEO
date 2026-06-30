"""Telegram Bot interface for SEO Agent Platform."""

import os
import sys
import asyncio
import logging
import json
from typing import Any
import httpx

# Load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure SEO Agent imports work
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from main import run_workflow, list_workflows, load_config
from agents.trends.agent import TrendsAgent

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("telegram-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS_RAW = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
ALLOWED_USERS = [u.strip() for u in ALLOWED_USERS_RAW.split(",") if u.strip()]

API_URL = f"https://api.telegram.org/bot{TOKEN}"

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set. Please set it in .env")
    sys.exit(1)

import hashlib

# Penyimpanan judul topik: {hash_key: topic_title}
# Digunakan agar callback_data tetap pendek (max 64 byte)
TOPIC_STORE = {}


async def send_message_with_keyboard(chat_id: int, text: str, keyboard: list, reply_to_message_id: int = None) -> dict:
    """Send text message to Telegram chat with inline keyboard."""
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": keyboard
        }
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 400:
            # Fallback: kirim tanpa parse_mode jika ada error formatting
            logger.warning(f"[Telegram] 400 error with HTML, retrying as plain text. Response: {resp.text}")
            payload.pop("parse_mode", None)
            payload["text"] = strip_html(text)
            resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def answer_callback_query(callback_query_id: str, text: str = None) -> dict:
    """Acknowledge Telegram callback query."""
    url = f"{API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_message(chat_id: int, text: str, reply_to_message_id: int = None) -> dict:
    """Send text message to Telegram chat."""
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 400:
            # Fallback: kirim tanpa parse_mode jika ada error formatting
            logger.warning(f"[Telegram] 400 error with HTML, retrying as plain text. Response: {resp.text}")
            payload.pop("parse_mode", None)
            payload["text"] = strip_html(text)
            resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_document(chat_id: int, file_path: str, caption: str = "") -> dict:
    """Send file document to Telegram chat."""
    url = f"{API_URL}/sendDocument"
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id, "caption": caption}
            resp = await client.post(url, data=data, files=files)
            resp.raise_for_status()
            return resp.json()


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def strip_html(text: str) -> str:
    """Strip HTML tags for plain text fallback."""
    import re
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return clean


def is_user_allowed(username: str, user_id: int) -> bool:
    """Check if the user is in the whitelist."""
    if not ALLOWED_USERS:
        # If whitelist is empty, allow anyone
        return True
    return (username and username in ALLOWED_USERS) or (str(user_id) in ALLOWED_USERS)


async def handle_command(chat_id: int, text: str, user_id: int, username: str, msg_id: int):
    """Parse and execute Telegram bot commands."""
    if not is_user_allowed(username, user_id):
        await send_message(chat_id, "❌ Anda tidak memiliki izin untuk menggunakan bot ini.", msg_id)
        return

    text = text.strip()
    if text.startswith("/start"):
        welcome = (
            "🤖 <b>SEO Agent Platform Bot</b> 🤖\n\n"
            "Halo! Saya adalah antarmuka Telegram untuk SEO Agent Platform Anda.\n"
            "Gunakan perintah berikut untuk mengontrol workflow:\n"
            "▫️ <code>/list</code> - Menampilkan daftar workflow yang tersedia.\n"
            "▫️ <code>/trends</code> - Mengambil topik tren dan menampilkannya dalam bentuk tombol.\n"
            "▫️ <code>/run &lt;workflow&gt; &lt;keyword/URL&gt;</code> - Menjalankan workflow tertentu.\n\n"
            "Contoh:\n"
            "<code>/run seo_article AI dalam bisnis</code>"
        )
        await send_message(chat_id, welcome, msg_id)

    elif text.startswith("/list"):
        wf_dir = os.path.join(ROOT, "workflows")
        if not os.path.exists(wf_dir):
            await send_message(chat_id, "❌ Direktori workflow tidak ditemukan.", msg_id)
            return

        msg = "📋 <b>Workflow yang Tersedia:</b>\n\n"
        for f in sorted(os.listdir(wf_dir)):
            if f.endswith(".yaml") or f.endswith(".yml"):
                try:
                    config = load_config(os.path.join(wf_dir, f))
                    name = escape_html(config.get("name", f))
                    desc = escape_html(config.get("description", ""))
                    msg += f"• <b>{name}</b> (file: <code>{escape_html(f)}</code>)\n<i>{desc}</i>\n\n"
                except Exception as e:
                    logger.error(f"Error loading config {f}: {e}")
        await send_message(chat_id, msg, msg_id)

    elif text.startswith("/trends") or text.startswith("/trend"):
        await send_message(
            chat_id,
            "🔍 <b>Mengambil dan Menyesuaikan Tren Terkini (Bidang Pengembangan SDM)...</b>\nMohon tunggu sebentar...",
            msg_id
        )
        try:
            from gateway.router import Router
            providers_config = load_config(os.path.join(ROOT, "config", "providers.yaml"))
            router = Router(providers_config)

            async def llm_func(messages, model="", temperature=0.7, max_tokens=4096):
                return await router.complete(
                    messages=messages,
                    model=model or "Qwen/Qwen2.5-7B-Instruct",
                    provider="huggingface",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            trends_agent = TrendsAgent()
            res = await trends_agent.run({"source": "both", "geo": "ID"}, llm_func)
            topics = res.get("topics", [])

            if not topics:
                await send_message(chat_id, "⚠️ Tidak ada topik tren yang berhasil ditemukan.", msg_id)
                return

            # Batasi maks 10 topik agar tidak melebihi batas 4096 karakter Telegram
            topics = topics[:10]

            # Bangun pesan + keyboard dengan hash pendek sebagai callback_data
            # callback_data WAJIB <= 64 byte — pakai hash 8 karakter sebagai key
            keyboard = []
            msg = "⚡ <b>Topik Tren Terkurasi — Pengembangan SDM</b>\n"
            msg += "Ketuk tombol di bawah untuk membuat artikel SEO:\n\n"

            for idx, item in enumerate(topics):
                title = item['title']
                safe_title = escape_html(title)
                msg += f"{idx+1}. {safe_title}\n"
                # Buat hash 8 karakter sebagai key unik
                key = hashlib.md5(title.encode()).hexdigest()[:8]
                TOPIC_STORE[key] = title
                # Tombol text: maks 60 karakter
                btn_text = title[:57] + ("..." if len(title) > 57 else "")
                # callback_data: "t:" + 8char = 10 byte, jauh di bawah batas 64 byte
                keyboard.append([{
                    "text": f"{idx+1}. {btn_text}",
                    "callback_data": f"t:{key}"
                }])

            # Pastikan pesan tidak melebihi 4096 karakter
            if len(msg) > 4000:
                msg = msg[:4000] + "\n<i>... dan lainnya tersedia via tombol</i>"

            await send_message_with_keyboard(chat_id, msg, keyboard, msg_id)

        except Exception as e:
            logger.exception("Error getting trends")
            err_msg = escape_html(str(e))
            await send_message(chat_id, f"❌ Gagal mengambil tren: <code>{err_msg}</code>", msg_id)

    elif text.startswith("/run"):
        parts = text.split(" ", 2)
        if len(parts) < 3:
            await send_message(
                chat_id,
                "❌ Format salah.\nContoh penggunaan: <code>/run seo_article tips seo 2026</code>",
                msg_id
            )
            return

        workflow = parts[1]
        keyword = parts[2]

        workflow_path = os.path.join(ROOT, "workflows", f"{workflow}.yaml")
        if not os.path.exists(workflow_path):
            await send_message(chat_id, f"❌ Workflow <code>{escape_html(workflow)}</code> tidak ditemukan.", msg_id)
            return

        await send_message(
            chat_id,
            f"🚀 <b>Memulai Workflow:</b> <code>{escape_html(workflow)}</code>\n"
            f"🔑 <b>Kata Kunci / URL:</b> <code>{escape_html(keyword)}</code>\n\n"
            f"Mohon tunggu, proses sedang berjalan...",
            msg_id
        )

        # Execute the workflow asynchronously in the background
        asyncio.create_task(execute_and_report(chat_id, workflow, workflow_path, keyword, msg_id))

    else:
        await send_message(chat_id, "❓ Perintah tidak dikenal. Ketik <code>/start</code> untuk bantuan.", msg_id)


async def execute_and_report(chat_id: int, workflow_name: str, path: str, keyword: str, msg_id: int):
    """Execute workflow and send updates/results back to Telegram."""
    input_data = {
        "keyword": keyword,
        "target_keyword": "",
        "extra_context": "",
        "language": "id",
    }

    # Define a callback to report steps visually
    async def step_callback(step_id, agent_name, status, step_idx, total_steps, detail=None):
        try:
            if status == "running":
                await send_message(
                    chat_id,
                    f"⏳ <b>[Langkah {step_idx}/{total_steps}]</b>\n"
                    f"Menjalankan Agen: <code>{escape_html(agent_name)}</code> (<code>{escape_html(step_id)}</code>)\n"
                    f"<i>{escape_html(str(detail) if detail else '')}</i>"
                )
            elif status == "completed":
                conf_str = ""
                if isinstance(detail, dict) and "confidence" in detail:
                    conf_str = f" (Confidence: <code>{detail['confidence']:.2f}</code>)"
                await send_message(
                    chat_id,
                    f"✅ <b>[Langkah {step_idx}/{total_steps}]</b>\n"
                    f"Agen <code>{escape_html(agent_name)}</code> selesai dengan sukses{conf_str}!"
                )
            elif status == "failed":
                detail_str = escape_html(str(detail)) if detail else "Unknown error"
                await send_message(
                    chat_id,
                    f"❌ <b>[Langkah {step_idx}/{total_steps}]</b>\n"
                    f"Agen <code>{escape_html(agent_name)}</code> GAGAL!\n"
                    f"Error: <code>{detail_str}</code>"
                )
        except Exception as cb_err:
            logger.error(f"Telegram callback send error: {cb_err}")

    try:
        # Run workflow logic with callback
        result = await run_workflow(path, input_data, step_callback=step_callback)
        
        status = result["status"].upper()
        icon = "✅" if status == "COMPLETED" else "⚠️" if status == "PARTIAL" else "❌"

        summary = (
            f"{icon} <b>Workflow Selesai: {escape_html(result['workflow'])}</b>\n"
            f"▫️ <b>Status:</b> <code>{status}</code>\n"
            f"▫️ <b>Langkah Sukses:</b> <code>{result['steps_completed']}/{result['steps_total']}</code>\n"
            f"▫️ <b>Token Terpakai:</b> <code>{result.get('total_tokens', 0)}</code>\n"
            f"▫️ <b>Perkiraan Biaya:</b> <code>${result.get('total_cost_usd', 0):.6f}</code>\n"
        )
        await send_message(chat_id, summary, msg_id)

        # ── Extract article content (same logic as main() CLI) ──────────
        import re as _re
        final = result.get("final_output", {})

        article_title = ""
        article_content = ""
        article_excerpt = ""
        meta_desc = ""
        quality_score = 0
        approved = False
        is_rewrite = "rewrite" in final

        rewrite_data = final.get("rewrite", {})
        if isinstance(rewrite_data, dict) and rewrite_data.get("content"):
            article_title   = rewrite_data.get("title", "")
            article_content = rewrite_data.get("content", "")
            article_excerpt = rewrite_data.get("excerpt", "")
            meta_desc       = rewrite_data.get("meta_description", "")

        for step_key in ("seo", "write", "writer"):
            data = final.get(step_key, {})
            if isinstance(data, dict):
                article_title   = article_title   or data.get("meta_title") or data.get("title", "")
                article_content = article_content or data.get("optimized_content") or data.get("content", "")
                article_excerpt = article_excerpt or data.get("excerpt", "")
                meta_desc       = meta_desc       or data.get("meta_description", "")

        review_data = final.get("review", {})
        if isinstance(review_data, dict):
            quality_score = review_data.get("quality_score", 0)
            approved      = review_data.get("approved", False)

        # ── Build output filename ────────────────────────────────────────
        if is_rewrite:
            src_url  = final.get("fetch", {}).get("url", keyword)
            domain   = _re.sub(r"https?://(www\.)?", "", src_url).split("/")[0]
            safe_kw  = _re.sub(r"[^\w-]", "_", domain)[:30]
        else:
            safe_kw = _re.sub(r"[^\w\s-]", "", keyword).strip().replace(" ", "_")[:40]

        out_dir  = os.path.join(ROOT, "output")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, f"{safe_kw}_{result['workflow_id']}.md")

        # ── Save article to .md file ─────────────────────────────────────
        if article_content:
            with open(out_file, "w", encoding="utf-8") as f:
                if article_title:
                    f.write(f"# {article_title}\n\n")
                if meta_desc:
                    f.write(f"**Meta:** {meta_desc}\n\n")
                if article_excerpt:
                    f.write(f"**Excerpt:** {article_excerpt}\n\n")
                f.write("---\n\n")
                f.write(article_content)
                if is_rewrite and isinstance(rewrite_data, dict):
                    seo_meta  = rewrite_data.get("seo_metadata", {})
                    int_links = rewrite_data.get("internal_links", {})
                    if seo_meta:
                        f.write("\n\n---\n\n## SEO Metadata\n\n")
                        for k, v in seo_meta.items():
                            if v:
                                f.write(f"- **{k}**: {v}\n")
                    if int_links:
                        f.write("\n\n---\n\n## Internal Link Recommendations\n\n")
                        f.write(json.dumps(int_links, ensure_ascii=False, indent=2))
                f.write(f"\n\n---\n")
                f.write(f"*Quality: {quality_score}/100 | Workflow: {result['workflow_id']}*\n")
            logger.info(f"Artikel disimpan: {out_file}")

        if os.path.exists(out_file):
            await send_document(
                chat_id,
                out_file,
                caption=f"📄 Berkas Artikel Hasil Generasi untuk: {keyword}"
            )
        else:
            await send_message(chat_id, "ℹ️ Tidak ditemukan berkas output hasil generasi.", msg_id)

    except Exception as e:
        logger.exception("Error executing workflow via Telegram")
        err_msg = escape_html(str(e))
        await send_message(chat_id, f"❌ <b>Gagal mengeksekusi workflow:</b>\n<code>{err_msg}</code>", msg_id)



async def main_loop():
    """Main Telegram polling loop."""
    logger.info("Bot Telegram SEO Agent aktif. Menunggu pesan...")
    offset = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                url = f"{API_URL}/getUpdates?offset={offset}&timeout=20"
                resp = await client.get(url)
                
                if resp.status_code != 200:
                    logger.error(f"Error calling getUpdates: Status {resp.status_code}")
                    await asyncio.sleep(5)
                    continue

                response_data = resp.json()
                updates = response_data.get("result", [])
                
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    # Handle Callback Query (Button clicks)
                    callback_query = update.get("callback_query")
                    if callback_query:
                        cb_id = callback_query["id"]
                        cb_data = callback_query.get("data", "")
                        from_user = callback_query.get("from", {})
                        user_id = from_user.get("id", 0)
                        username = from_user.get("username", "")
                        
                        logger.info(f"Received callback query from @{username} ({user_id}): {cb_data}")
                        
                        if not is_user_allowed(username, user_id):
                            await answer_callback_query(cb_id, "❌ Izin ditolak.")
                            continue

                        chat_id = callback_query["message"]["chat"]["id"]
                        msg_id = callback_query["message"]["message_id"]

                        if cb_data.startswith("t:"):
                            # Lookup judul dari TOPIC_STORE menggunakan hash key
                            try:
                                key = cb_data[2:]  # hapus prefix "t:"
                                topic_title = TOPIC_STORE.get(key, "")
                                if not topic_title:
                                    await answer_callback_query(cb_id, "⚠️ Sesi kedaluwarsa. Ketik /trends lagi.")
                                    continue

                                await answer_callback_query(cb_id, f"Memilih: {topic_title[:20]}")

                                safe_topic = escape_html(topic_title)
                                confirm_msg = (
                                    f"Anda memilih topik:\n👉 <b>{safe_topic}</b>\n\n"
                                    "Apakah Anda ingin melanjutkan ke proses pengerjaan Agen SEO?"
                                )
                                # Tombol konfirmasi: pakai key yang sama, prefix "c:"
                                keyboard = [
                                    [
                                        {"text": "✅ Ya, Lanjutkan", "callback_data": f"c:{key}"},
                                        {"text": "❌ Batalkan", "callback_data": "cancel_run"}
                                    ]
                                ]
                                await send_message_with_keyboard(chat_id, confirm_msg, keyboard)
                            except Exception as ex:
                                logger.exception("Error processing trend choice")
                                await answer_callback_query(cb_id, f"❌ Error: {str(ex)[:50]}")

                        elif cb_data.startswith("c:"):
                            # Konfirmasi → jalankan workflow
                            try:
                                key = cb_data[2:]  # hapus prefix "c:"
                                topic_title = TOPIC_STORE.get(key, "")
                                if not topic_title:
                                    await answer_callback_query(cb_id, "⚠️ Sesi kedaluwarsa. Ketik /trends lagi.")
                                    continue

                                await answer_callback_query(cb_id, "Memulai workflow...")

                                workflow_name = "seo_article"
                                workflow_path = os.path.join(ROOT, "workflows", f"{workflow_name}.yaml")

                                await send_message(
                                    chat_id,
                                    f"🚀 <b>Memulai Workflow:</b> <code>{escape_html(workflow_name)}</code>\n"
                                    f"🔑 <b>Kata Kunci (Tren):</b> <code>{escape_html(topic_title)}</code>\n\n"
                                    f"Mohon tunggu, proses sedang berjalan..."
                                )
                                asyncio.create_task(execute_and_report(chat_id, workflow_name, workflow_path, topic_title, None))
                            except Exception as ex:
                                logger.exception("Error processing confirm run")
                                await answer_callback_query(cb_id, f"❌ Error: {str(ex)[:50]}")

                        elif cb_data == "cancel_run":
                            await answer_callback_query(cb_id, "Dibatalkan.")
                            await send_message(chat_id, "❌ Pembuatan artikel dibatalkan.")
                        continue

                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                        
                    chat_id = message["chat"]["id"]
                    text = message["text"]
                    msg_id = message["message_id"]
                    
                    from_user = message.get("from", {})
                    user_id = from_user.get("id", 0)
                    username = from_user.get("username", "")
                    
                    logger.info(f"Received message from @{username} ({user_id}): {text}")
                    
                    # Handle the command asynchronously
                    asyncio.create_task(
                        handle_command(chat_id, text, user_id, username, msg_id)
                    )
                    
            except httpx.RequestError as e:
                logger.warning(f"Network error in polling loop: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna.")
