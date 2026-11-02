import asyncio
import os
from pathlib import Path
from telethon import TelegramClient

async def main():
    session = os.getenv('TG_SESSION', 'data/reader')
    Path(session).parent.mkdir(parents=True,exist_ok=True)
    async with TelegramClient(session,int(os.environ['TG_API_ID']),os.environ['TG_API_HASH']):
        print('Аккаунт авторизован. Файл сессии храните как пароль.')

if __name__ == '__main__':
    asyncio.run(main())
