"""Entry point: loads config and wires tools -> model -> Discord client."""
import os

from dotenv import load_dotenv

import tools.tools as t
from discord_client import MyClient, build_intents
from suina_model import SuinaModel


def main():
    load_dotenv()
    # os.environ[...] fails loudly if a variable is missing (str(None) would give "None")
    target_channel_id = int(os.environ["TARGET_CHANNEL_ID"])
    voice_channel_id = int(os.environ["VOICE_CHANNEL_ID"])
    token = os.environ["TOKEN_DISCORD"]
    model_url = os.environ["MODEL_URL"]

    model = SuinaModel(
        model_url,
        tools=t.TOOLS,
        tool_runner=t.run_tool,
        n_predict=1024,
        temperature=0.8,
        max_tool_rounds=5,
    )
    client = MyClient(build_intents(), model, target_channel_id,voice_channel_id)
    client.run(token)


if __name__ == "__main__":
    main()