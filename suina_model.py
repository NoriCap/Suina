"""SuinaModel: talks to llama-server, manages context/history and runs the tool-call loop."""
import datetime
import json
import os
import re
from typing import Callable

import requests

# Format of a tool call in the raw model output.
CALL_RE = re.compile(r"<\|tool_call>call:(\w+)\{(.*?)\}(?:<tool_call\|>|\s*\Z)", re.S)
# Format of the "thinking" channel followed by the final answer.
CHANNEL_RE = re.compile(r"<\|channel>(.*?)<channel\|>(.*)", re.S)
# key:<|"|>value<|"|>   or   key:"value"
_ARG_RE = re.compile(r'(\w+)\s*:\s*(?:<\|"\|>(.*?)<\|"\|>|"((?:[^"\\]|\\.)*)")', re.S)


def parse_tool_args(raw: str) -> dict:
    """Turn the text between the braces of a tool call into a dict.

    Tries plain JSON first, then the key:<|"|>value<|"|> style.
    Check logs/tool_calls.txt to confirm it matches what your model really emits.
    """
    raw = raw.strip()
    if not raw:
        return {}
    try:
        return json.loads("{" + raw + "}")
    except json.JSONDecodeError:
        pass
    args = {}
    for m in _ARG_RE.finditer(raw):
        args[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return args


class SuinaModel:
    def __init__(
        self,
        model_url: str,
        tools: list[dict],
        tool_runner: Callable[[str, dict], str],
        *,
        n_predict: int = 1024,
        temperature: float = 0.8,
        max_tool_rounds: int = 5,
        context_dir: str = "context/",
        log_dir: str = "logs/",
    ):
        self.model_url = model_url
        self.tools = tools
        self.tool_runner = tool_runner
        self.n_predict = n_predict
        self.temperature = temperature
        self.max_tool_rounds = max_tool_rounds
        self.base_context_directory = context_dir
        self.base_log_directory = log_dir
        self.model_context = self.init_context()

    # -- setup / utilities --------------------------------------------------
    def status_model(self) -> bool:
        r = requests.get(self.model_url + "/health", timeout=10)
        if r.status_code != 200:
            raise Exception("Error with model check health didn't passed ")
        return True

    def init_context(self) -> str:
        with open(self.base_context_directory + "base_context.txt", "r") as f:
            return f.read()

    def some_logging(self, filename: str, content: str):
        os.makedirs(self.base_log_directory, exist_ok=True)
        with open(self.base_log_directory + filename, "a", encoding="utf-8") as f:
            f.write(content + "\n")

    # -- history ------------------------------------------------------------
    def get_chat_history(self) -> list[dict]:
        path = self.base_context_directory + "history_log.jsonl"
        history = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    e = json.loads(line)
                    # keep only what the chat template needs
                    history.append({"role": e["role"], "content": e["content"]})
        except FileNotFoundError:
            pass  # no history yet
        return history

    def save_conversation(self, user_prompt: str, model_response: str):
        author = "Nori"
        date = datetime.datetime.now().isoformat()
        entries = [
            {"role": "user", "content": user_prompt, "author": author, "date": date},
            {"role": "assistant", "content": model_response, "author": "Suina", "date": date},
        ]
        with open(self.base_context_directory + "history_log.jsonl", "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # -- prompt building / generation ---------------------------------------
    def apply_template(self, messages: list[dict]) -> str:
        r = requests.post(
            self.model_url + "/apply-template",
            json={"messages": messages, "tools": self.tools},
        )
        r.raise_for_status()
        self.some_logging("apply_template.txt", json.dumps(r.json()))
        return r.json()["prompt"]

    def clean_conversation(self, model_response: str) -> tuple[str, str]:
        print(model_response)
        if "<channel|>" in model_response:
            thinking, answer = model_response.rsplit("<channel|>", 1)
            thinking = re.sub(r"^\s*<\|channel>(thought)?", "", thinking).strip()
            return thinking, answer.strip()
        if "<|channel>" in model_response:
            # reasoning started but never closed (probably hit n_predict)
            return model_response, ""
        return "", model_response.strip()

    def send_prompt(self, msg: str) -> str:
        messages = [
            {"role": "system", "content": self.model_context},
            *self.get_chat_history(),
            {"role": "user", "content": msg},
        ]

        for round_index in range(self.max_tool_rounds):
            prompt = self.apply_template(messages)  # re-render with the updated messages
            r = requests.post(
                self.model_url + "/completion",
                json={
                    "prompt": prompt,
                    "n_predict": self.n_predict,
                    "temperature": self.temperature,
                },
            )
            r.raise_for_status()
            text = r.json()["content"]

            m = CALL_RE.search(text)
            if not m:  # no tool call detected -> final answer
                _thinking, answer = self.clean_conversation(text)
                return answer

            name, raw_args = m.group(1), m.group(2)
            args = parse_tool_args(raw_args)
            result = self.tool_runner(name, args)
            self.some_logging(
                "tool_calls.txt",
                json.dumps(
                    {"name": name, "raw_args": raw_args, "parsed_args": args, "result": result},
                    ensure_ascii=False,
                ),
            )

            call_id = f"call_{round_index}"
            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }],
            })
            messages.append({"role": "tool", "tool_call_id": call_id, "content": str(result)})

        return "there is an error in my AI"

    # -- one-call entry point used by the Discord client --------------------
    def chat(self, user_message: str) -> str:
        response = self.send_prompt(user_message)
        self.save_conversation(user_message, response)
        self.some_logging("output_model", response)
        return response