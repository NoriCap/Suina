import io, queue, threading
import torch
import discord
from pocket_tts import TTSModel

tts_model = TTSModel.load_model()
voice_state = tts_model.get_state_for_audio_prompt("alba")
print("TTS MODEL LOADED")

class StreamBuffer(io.RawIOBase):
    """File-like object that ffmpeg reads from while we keep writing to it."""
    def __init__(self):
        self.q = queue.Queue()
        self.leftover = b""

    def readable(self):
        return True

    def read(self, size=-1):
        if not self.leftover:
            data = self.q.get()          # blocks until a chunk arrives
            if data is None:             # end of stream
                return b""
            self.leftover = data
        out, self.leftover = self.leftover[:size], self.leftover[size:]
        return out

    def feed(self, data: bytes):
        self.q.put(data)

    def finish(self):
        self.q.put(None)
# producer
def _generate(text: str, buf: StreamBuffer):
    try:
        for chunk in tts_model.generate_audio_stream(voice_state, text):
            # convert audio stream into bytes ffmpeg
            pcm = (chunk.clamp(-1, 1) * 32767).to(torch.int16).cpu().numpy().tobytes()
            buf.feed(pcm)
    finally:
        buf.finish()
# consumer
def speak_streaming(voice_client, text: str):
    buf = StreamBuffer()
    threading.Thread(target=_generate, args=(text, buf), daemon=True).start()

    source = discord.FFmpegPCMAudio(
        buf,
        pipe=True,
        before_options=f"-f s16le -ar {tts_model.sample_rate} -ac 1",  # raw mono PCM in
    )
    voice_client.play(source)