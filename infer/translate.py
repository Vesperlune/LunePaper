"""
Hy-MT2 Translation — Minimal
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infer.llama_binding import LlamaModel

PROMPT = """English: {source}
Chinese:"""


class Translator:
    """Minimal translator."""

    def __init__(self, model_path: str = None, n_gpu_layers: int = 99):
        if model_path is None:
            model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'Hy-MT2-1.8B-Q8_0.gguf')
        self.llm = LlamaModel(model_path, n_gpu_layers=n_gpu_layers,
                              n_ctx=4096, n_threads=4)

    def translate(self, text: str, max_tokens: int = 512) -> str:
        output = self.llm.generate(
            PROMPT.format(source=text),
            max_tokens=max_tokens,
            temperature=0.7, top_p=0.6, top_k=20)
        return self._clean(output)

    def _clean(self, output: str) -> str:
        lines = output.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                if result: break     # stop only after content
                continue              # skip leading blanks
            if line.startswith('English:') and result: break
            result.append(line)
        return ' '.join(result).strip()

    def close(self):
        self.llm.close()
