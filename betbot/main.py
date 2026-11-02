import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from telethon import TelegramClient, events

from .store import Store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

async def main():
    token = os.environ['BOT_TOKEN']
    group = int(os.environ['GROUP_ID'])
    admins = {int(x) for x in os.environ['ADMIN_IDS'].split(',')}
    store = Store(os.getenv('DB_PATH', 'data/bot.sqlite3'))
    bot = Bot(token)
    dp = Dispatcher()

    async def access(user_id):
        # Join requests prevent a shared invite from admitting non-subscribers.
        await bot.unban_chat_member(group, user_id, only_if_banned=True)
        invite = await bot.create_chat_invite_link(group, creates_join_request=True,
            expire_date=datetime.now(timezone.utc)+timedelta(minutes=15))
        await bot.send_message(user_id, f'Доступ активен. Ссылка действует 15 минут:\n{invite.invite_link}')

    @dp.message(Command('start', 'status'))
    async def start(m):
        if store.active(m.from_user.id):
            await access(m.from_user.id)
        else:
            await m.answer('Доступ на 30 дней. Для покупки: /buy')

    @dp.message(Command('buy'))
    async def buy(m):
        await m.answer('Доступ на 30 дней: 299 ₽. Оплата в боте пока не подключена. Для оформления обратитесь к администратору.')

    @dp.chat_join_request()
    async def join(q):
        if q.chat.id != group:
            return
        if store.active(q.from_user.id):
            await q.approve()
        else:
            await q.decline()

    @dp.message(Command('admin'))
    async def admin(m):
        if m.from_user.id in admins:
            await m.answer('/source CHANNEL_ID TOPIC_ID — подключить разрешённый источник\n/sources — список\n/remove CHANNEL_ID — отключить\n/grant USER_ID — выдать 30 дней\n/revoke USER_ID — отозвать доступ\n/subscribers — активные подписки')

    @dp.message(Command('source', 'sources', 'remove', 'grant', 'revoke', 'subscribers'))
    async def manage(m):
        if m.from_user.id not in admins or m.chat.type != 'private':
            return
        parts = m.text.split()
        cmd = parts[0].split('@')[0]
        try:
            if cmd == '/source' and len(parts) == 3:
                channel, topic = map(int,parts[1:])
                with store.db:
                    store.db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(channel,topic))
                await m.answer('Источник подключён. Подключайте только источники с разрешением на распространение.')
            elif cmd == '/sources':
                await m.answer(str(store.db.execute('SELECT * FROM sources').fetchall())[:4000])
            elif cmd == '/remove' and len(parts) == 2:
                with store.db:
                    store.db.execute('DELETE FROM sources WHERE chat_id=?',(int(parts[1]),))
                await m.answer('Источник отключён.')
            elif cmd == '/grant' and len(parts) == 2:
                uid = int(parts[1])
                store.grant(uid, 'manual:'+str(uuid.uuid4()))
                await m.answer('Доступ выдан. Пользователь может получить ссылку через /start.')
            elif cmd == '/revoke' and len(parts) == 2:
                uid = int(parts[1])
                with store.db:
                    store.db.execute('DELETE FROM subscriptions WHERE user_id=?',(uid,))
                await bot.ban_chat_member(group,uid)
                await m.answer('Доступ отозван.')
            elif cmd == '/subscribers':
                await m.answer(str(store.db.execute('SELECT * FROM subscriptions WHERE until>?',(int(time.time()),)).fetchall())[:4000])
            else:
                await m.answer('Проверьте аргументы: /admin')
        except ValueError:
            await m.answer('ID должны быть целыми числами.')

    async def expire():
        while True:
            for (uid,) in store.db.execute('SELECT user_id FROM subscriptions WHERE until<=?',(int(time.time()),)).fetchall():
                try:
                    await bot.ban_chat_member(group,uid)
                    with store.db:
                        store.db.execute('DELETE FROM subscriptions WHERE user_id=? AND until<=?',(uid,int(time.time())))
                except Exception:
                    log.exception('Cannot remove expired subscriber %s',uid)
            await asyncio.sleep(60)

    client = TelegramClient(os.getenv('TG_SESSION','data/reader'),int(os.environ['TG_API_ID']),os.environ['TG_API_HASH'])
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError('Сначала авторизуйте аккаунт: python -m betbot.login')

    @client.on(events.NewMessage())
    async def relay(event):
        topic = store.topic(event.chat_id)
        msg = event.message
        if topic is None or store.seen(event.chat_id,msg.id):
            return
        try:
            text = msg.raw_text or ''
            # Publish a fresh message: Telegram forward attribution is omitted.
            if msg.photo or msg.video or msg.document:
                blob = await client.download_media(msg, file=bytes)
                upload = BufferedInputFile(blob, filename=msg.file.name or ('photo.jpg' if msg.photo else 'attachment'))
                caption = text[:1024] or None
                if msg.photo:
                    await bot.send_photo(group,upload,caption=caption,message_thread_id=topic)
                elif msg.video:
                    await bot.send_video(group,upload,caption=caption,message_thread_id=topic)
                else:
                    await bot.send_document(group,upload,caption=caption,message_thread_id=topic)
                text = text[1024:]
            for offset in range(0,len(text),4096):
                await bot.send_message(group,text[offset:offset+4096],message_thread_id=topic)
            store.mark(event.chat_id,msg.id)
        except Exception:
            log.exception('Relay failed for %s/%s',event.chat_id,msg.id)

    worker = asyncio.create_task(expire())
    try:
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        await client.disconnect()
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())
