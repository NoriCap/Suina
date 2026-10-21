"""Discord client: receives messages and forwards them to the model."""
import asyncio

import discord
from discord import Intents, Message


def build_intents() -> Intents:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True  # must also be enabled in the Discord developer portal
    intents.guilds = True
    intents.guild_messages = True
    return intents


class MyClient(discord.Client):
    def __init__(self, intents_settings: Intents, model, target_channel_id: int):
        super().__init__(intents=intents_settings)
        self.model = model
        self.target_channel_id = target_channel_id

    async def on_ready(self):
        print(f"We have logged in as {self.user}")
        print(f"MODEL CONFIGURED AT {self.model.model_url}")
        # requests is blocking, so run it in a worker thread
        ok = await asyncio.to_thread(self.model.status_model)
        print(f"HEALTH CHECK CONTACTING MODEL : {ok}")

    async def on_message(self, message: Message):
        if message.channel.id != self.target_channel_id:
            return
        if message.author == self.user:
            return

        print("RECEIVED MESSAGE", message.content)
        # Generation can take a while: keep the event loop free so Discord's
        # heartbeat isn't blocked, and show the "typing..." indicator.
        async with message.channel.typing():
            response = await asyncio.to_thread(self.model.chat, message.content)
        await message.channel.send(response)