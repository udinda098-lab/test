import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sys
import requests

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

DATA_FILE = "/data/domain_data.json"
LOG_FILE = "/data/amp_changes.log"
CHECK_INTERVAL = 600  # 10 menit


# =====================
# DOMAIN NORMALIZER
# =====================
def normalize_domain(input_domain):
    input_domain = input_domain.strip()

    if not input_domain.startswith("http"):
        request_url = "https://" + input_domain
    else:
        request_url = input_domain

    parsed = urlparse(request_url)
    clean_domain = parsed.netloc

    return request_url, clean_domain


def get_display_url(url):
    if not url:
        return "-"
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path or ""
    return f"{domain}{path}"


# =====================
# FILE HANDLER
# =====================
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# =====================
# AMP CHECKER
# =====================
async def get_amp_url(domain):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(domain, timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                amp = soup.find("link", rel="amphtml")
                return amp["href"] if amp else None
    except:
        return None


# =====================
# COMMAND TAMBAH
# =====================
async def tambah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gunakan: /tambah example.com")
        return

    request_url, _ = normalize_domain(context.args[0])
    chat_id = update.effective_chat.id

    amp_url = await get_amp_url(request_url)
    data = load_data()

    data[request_url] = {
        "initial_amp": amp_url,
        "current_amp": amp_url,
        "last_checked": str(datetime.now()),
        "chat_id": chat_id,
        "change_notified_count": 0
    }

    save_data(data)

    await update.message.reply_text(
        "✅ *DOMAIN DITAMBAHKAN*\n"
        "────────────────────\n"
        f"🌐 Domain  : `{get_display_url(request_url)}`\n"
        f"🔎 AMP Awal : `{get_display_url(amp_url)}`\n"
        "────────────────────",
        disable_web_page_preview=True,
        parse_mode="Markdown"
    )


# =====================
# COMMAND HAPUS
# =====================
async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gunakan: /hapus example.com")
        return

    request_url, _ = normalize_domain(context.args[0])
    data = load_data()

    if request_url in data:
        del data[request_url]
        save_data(data)
        await update.message.reply_text(
            f"🗑 *DOMAIN DIHAPUS*\n────────────────────\n`{get_display_url(request_url)}`",
            disable_web_page_preview=True,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠ Domain tidak ditemukan")


# =====================
# COMMAND LIST
# =====================
async def list_domains(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_data()

    domains = [d for d, info in data.items() if info.get("chat_id") == chat_id]

    if not domains:
        await update.message.reply_text("Belum ada domain tersimpan.")
        return

    msg = ["📋 *DAFTAR DOMAIN MONITORING*\n"]

    for d in domains:
        info = data[d]
        msg.append(
            "────────────────────\n"
            f"🌐 `{get_display_url(d)}`\n"
            f"• AMP Awal     : `{get_display_url(info.get('initial_amp'))}`\n"
            f"• AMP Sekarang : `{get_display_url(info.get('current_amp'))}`\n"
            f"• Last Check   : {info.get('last_checked')}"
        )

    await update.message.reply_text(
        "\n".join(msg),
        disable_web_page_preview=True,
        parse_mode="Markdown"
    )


# =====================
# COMMAND CEK
# =====================
async def cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gunakan: /cek example.com")
        return

    request_url, _ = normalize_domain(context.args[0])
    amp = await get_amp_url(request_url)

    await update.message.reply_text(
        "🔎 *HASIL PENGECEKAN*\n"
        "────────────────────\n"
        f"🌐 Domain : `{get_display_url(request_url)}`\n"
        f"📌 AMP    : `{get_display_url(amp)}`\n"
        "────────────────────",
        disable_web_page_preview=True,
        parse_mode="Markdown"
    )


# =====================
# PERIODIC CHECK
# =====================
async def periodic_check(app):
    await asyncio.sleep(5)

    while True:
        data = load_data()
        updated = False

        for domain, info in data.items():
            initial_amp = info.get("initial_amp")
            current_amp = info.get("current_amp")
            notified_count = info.get("change_notified_count", 0)

            new_amp = await get_amp_url(domain)

            if new_amp != current_amp:
                data[domain]["current_amp"] = new_amp
                data[domain]["last_checked"] = str(datetime.now())
                data[domain]["change_notified_count"] = 0
                updated = True

            if new_amp != initial_amp:
                if notified_count < 3:
                    try:
                        await app.bot.send_message(
                            chat_id=info["chat_id"],
                            text=(
                                "🚨 *AMP BERUBAH TERDETEKSI*\n"
                                "────────────────────\n"
                                f"🌐 Domain : `{get_display_url(domain)}`\n"
                                f"🔎 AMP Awal : `{get_display_url(initial_amp)}`\n"
                                f"⚠ AMP Baru  : `{get_display_url(new_amp)}`\n"
                                f"🔔 Notif : {notified_count+1}/3\n"
                                "────────────────────"
                            ),
                            disable_web_page_preview=True,
                            parse_mode="Markdown"
                        )
                        data[domain]["change_notified_count"] += 1
                        updated = True
                    except:
                        pass

            if new_amp == initial_amp and current_amp != initial_amp:
                try:
                    await app.bot.send_message(
                        chat_id=info["chat_id"],
                        text=(
                            "✅ *AMP KEMBALI NORMAL*\n"
                            "────────────────────\n"
                            f"🌐 Domain : `{get_display_url(domain)}`\n"
                            f"📌 AMP Aktif : `{get_display_url(initial_amp)}`\n"
                            "────────────────────"
                        ),
                        disable_web_page_preview=True,
                        parse_mode="Markdown"
                    )
                except:
                    pass

                data[domain]["change_notified_count"] = 0
                updated = True

        if updated:
            save_data(data)

        await asyncio.sleep(CHECK_INTERVAL)


# =====================
# HEARTBEAT 1 JAM
# =====================
async def heartbeat_loop(app):
    while True:
        await asyncio.sleep(3600)
        data = load_data()
        chat_ids = set(info.get("chat_id") for info in data.values() if info.get("chat_id"))

        for chat_id in chat_ids:
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "💓 *BOT AKTIF*\n"
                        "────────────────────\n"
                        "Monitoring berjalan normal.\n"
                         
                    ),
                    disable_web_page_preview=True,
                    parse_mode="Markdown"
                )
            except:
                pass


# =====================
# MAIN
# =====================
def main():
    app = ApplicationBuilder().token("7997011935:AAECyfPel4PrYHhXnMI6QCVi4oQ4Esp1n7E").build()

    app.add_handler(CommandHandler("tambah", tambah))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(CommandHandler("list", list_domains))
    app.add_handler(CommandHandler("cek", cek))

    async def startup(app):
        app.create_task(periodic_check(app))
        app.create_task(heartbeat_loop(app))

    app.post_init = startup
    app.run_polling()


if __name__ == "__main__":
    main()
