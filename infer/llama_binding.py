"""
Minimal ctypes binding for llama.dll
Provides low-level access to llama.cpp C API.
"""
import ctypes
import os
import sys
import json
from ctypes import (
    c_void_p, c_char_p, c_int32, c_uint32, c_int64, c_size_t,
    c_float, c_double, c_bool, c_int8, POINTER, Structure, byref,
    cast, pointer, CFUNCTYPE
)

# ============================================================
# DLL Loading
# ============================================================
_DLL_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_DLL_DIR)

os.add_dll_directory(_ROOT_DIR)
os.add_dll_directory(r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin')

_lib = ctypes.CDLL(os.path.join(_ROOT_DIR, 'llama.dll'))

# ============================================================
# Opaque types
# ============================================================
llama_model_p       = c_void_p
llama_context_p     = c_void_p
llama_vocab_p       = c_void_p
llama_sampler_p     = c_void_p
llama_memory_p      = c_void_p
ggml_backend_dev_p  = c_void_p

# ============================================================
# Basic types
# ============================================================
llama_token   = c_int32
llama_pos     = c_int32
llama_seq_id  = c_int32

# ============================================================
# Enums (as c_int32)
# ============================================================
LLAMA_SPLIT_MODE_NONE = 0
LLAMA_SPLIT_MODE_LAYER = 1
LLAMA_SPLIT_MODE_ROW = 2

LLAMA_CONTEXT_TYPE_DEFAULT = 0
LLAMA_ROPE_SCALING_TYPE_UNSPECIFIED = -1
LLAMA_POOLING_TYPE_UNSPECIFIED = -1
LLAMA_ATTENTION_TYPE_UNSPECIFIED = -1
LLAMA_FLASH_ATTN_TYPE_AUTO = 0

# ============================================================
# Struct: llama_token_data
# ============================================================
class llama_token_data(Structure):
    _fields_ = [
        ("id", c_int32),
        ("logit", c_float),
        ("p", c_float),
    ]

# ============================================================
# Struct: llama_token_data_array
# ============================================================
class llama_token_data_array(Structure):
    _fields_ = [
        ("data", POINTER(llama_token_data)),
        ("size", c_size_t),
        ("selected", c_int64),
        ("sorted", c_bool),
    ]

# ============================================================
# Struct: llama_batch
# ============================================================
class llama_batch(Structure):
    _fields_ = [
        ("n_tokens", c_int32),
        ("token", POINTER(llama_token)),
        ("embd", POINTER(c_float)),
        ("pos", POINTER(llama_pos)),
        ("n_seq_id", POINTER(c_int32)),
        ("seq_id", POINTER(POINTER(llama_seq_id))),
        ("logits", POINTER(c_int8)),
    ]

# ============================================================
# Struct: llama_model_params
# ============================================================
class llama_model_params(Structure):
    _fields_ = [
        ("devices", POINTER(ggml_backend_dev_p)),
        ("tensor_buft_overrides", c_void_p),
        ("n_gpu_layers", c_int32),
        ("split_mode", c_int32),
        ("main_gpu", c_int32),
        ("_pad1", c_int32),  # padding to 8-byte align
        ("tensor_split", POINTER(c_float)),
        ("progress_callback", c_void_p),
        ("progress_callback_user_data", c_void_p),
        ("kv_overrides", c_void_p),
        ("vocab_only", c_bool),
        ("use_mmap", c_bool),
        ("use_direct_io", c_bool),
        ("use_mlock", c_bool),
        ("check_tensors", c_bool),
        ("use_extra_bufts", c_bool),
        ("no_host", c_bool),
        ("no_alloc", c_bool),
    ]

_actual_mparams = llama_model_params()
# Calculate actual size... the struct layout might differ. Let's use the default function.

# ============================================================
# Struct: llama_sampler_chain_params
# ============================================================
class llama_sampler_chain_params(Structure):
    _fields_ = [
        ("no_perf", c_bool),
    ]

# ============================================================
# Struct: llama_context_params
# ============================================================
class llama_context_params(Structure):
    _fields_ = [
        ("n_ctx", c_uint32),
        ("n_batch", c_uint32),
        ("n_ubatch", c_uint32),
        ("n_seq_max", c_uint32),
        ("n_rs_seq", c_uint32),
        ("n_outputs_max", c_uint32),
        ("n_threads", c_int32),
        ("n_threads_batch", c_int32),
        ("ctx_type", c_int32),
        ("rope_scaling_type", c_int32),
        ("pooling_type", c_int32),
        ("attention_type", c_int32),
        ("flash_attn_type", c_int32),
        ("rope_freq_base", c_float),
        ("rope_freq_scale", c_float),
        ("yarn_ext_factor", c_float),
        ("yarn_attn_factor", c_float),
        ("yarn_beta_fast", c_float),
        ("yarn_beta_slow", c_float),
        ("yarn_orig_ctx", c_uint32),
        ("defrag_thold", c_float),
        ("cb_eval", c_void_p),
        ("cb_eval_user_data", c_void_p),
        ("type_k", c_int32),
        ("type_v", c_int32),
        ("abort_callback", c_void_p),
        ("abort_callback_data", c_void_p),
        ("embeddings", c_bool),
        ("offload_kqv", c_bool),
        ("no_perf", c_bool),
        ("op_offload", c_bool),
        ("swa_full", c_bool),
        ("kv_unified", c_bool),
        ("samplers", c_void_p),
        ("n_samplers", c_size_t),
        ("ctx_other", c_void_p),
    ]

# ============================================================
# Progress callback type
# ============================================================
llama_progress_callback_t = CFUNCTYPE(c_bool, c_float, c_void_p)

# ============================================================
# Function signatures
# ============================================================

# Model
_lib.llama_model_default_params.restype = llama_model_params
_lib.llama_model_default_params.argtypes = []

_lib.llama_context_default_params.restype = llama_context_params
_lib.llama_context_default_params.argtypes = []

_lib.llama_sampler_chain_default_params.restype = llama_sampler_chain_params
_lib.llama_sampler_chain_default_params.argtypes = []

_lib.llama_model_load_from_file.restype = llama_model_p
_lib.llama_model_load_from_file.argtypes = [c_char_p, llama_model_params]

_lib.llama_init_from_model.restype = llama_context_p
_lib.llama_init_from_model.argtypes = [llama_model_p, llama_context_params]

_lib.llama_model_get_vocab.restype = llama_vocab_p
_lib.llama_model_get_vocab.argtypes = [llama_model_p]

_lib.llama_model_free.restype = None
_lib.llama_model_free.argtypes = [llama_model_p]

_lib.llama_free.restype = None
_lib.llama_free.argtypes = [llama_context_p]

# Tokenizer
_lib.llama_tokenize.restype = c_int32
_lib.llama_tokenize.argtypes = [llama_vocab_p, c_char_p, c_int32, POINTER(llama_token), c_int32, c_bool, c_bool]

_lib.llama_vocab_get_text.restype = c_char_p
_lib.llama_vocab_get_text.argtypes = [llama_vocab_p, llama_token]

_lib.llama_vocab_eos.restype = llama_token
_lib.llama_vocab_eos.argtypes = [llama_vocab_p]

_lib.llama_vocab_eot.restype = llama_token
_lib.llama_vocab_eot.argtypes = [llama_vocab_p]

# Batch
_lib.llama_batch_get_one.restype = llama_batch
_lib.llama_batch_get_one.argtypes = [POINTER(llama_token), c_int32]

_lib.llama_batch_init.restype = llama_batch
_lib.llama_batch_init.argtypes = [c_int32, c_uint32, c_int32]

_lib.llama_batch_free.restype = None
_lib.llama_batch_free.argtypes = [llama_batch]

# Decode
_lib.llama_decode.restype = c_int32
_lib.llama_decode.argtypes = [llama_context_p, llama_batch]

# Sampler
_lib.llama_sampler_chain_init.restype = llama_sampler_p
_lib.llama_sampler_chain_init.argtypes = [llama_sampler_chain_params]

_lib.llama_sampler_chain_add.restype = None
_lib.llama_sampler_chain_add.argtypes = [llama_sampler_p, llama_sampler_p]

_lib.llama_sampler_init_greedy.restype = llama_sampler_p
_lib.llama_sampler_init_greedy.argtypes = []

_lib.llama_sampler_init_top_k.restype = llama_sampler_p
_lib.llama_sampler_init_top_k.argtypes = [c_int32]

_lib.llama_sampler_init_top_p.restype = llama_sampler_p
_lib.llama_sampler_init_top_p.argtypes = [c_float, c_size_t]

_lib.llama_sampler_init_temp.restype = llama_sampler_p
_lib.llama_sampler_init_temp.argtypes = [c_float]

_lib.llama_sampler_init_dist.restype = llama_sampler_p
_lib.llama_sampler_init_dist.argtypes = [c_uint32]

_lib.llama_sampler_sample.restype = llama_token
_lib.llama_sampler_sample.argtypes = [llama_sampler_p, llama_context_p, c_int32]

_lib.llama_sampler_free.restype = None
_lib.llama_sampler_free.argtypes = [llama_sampler_p]

# Chat template
_lib.llama_chat_apply_template.restype = c_int32
_lib.llama_chat_apply_template.argtypes = [c_char_p, c_char_p, POINTER(c_char_p), c_int32, c_bool, c_char_p, c_int32]

# Model metadata
_lib.llama_model_meta_val_str.restype = c_int32
_lib.llama_model_meta_val_str.argtypes = [llama_model_p, c_char_p, c_char_p, c_size_t]

# Memory management
_lib.llama_get_memory.restype = llama_memory_p
_lib.llama_get_memory.argtypes = [llama_context_p]

_lib.llama_memory_clear.restype = None
_lib.llama_memory_clear.argtypes = [llama_memory_p, c_bool]

# Remove tokens from memory in position range [p0, p1). p1 < 0 means [p0, inf)
_lib.llama_memory_seq_rm.restype = c_bool
_lib.llama_memory_seq_rm.argtypes = [llama_memory_p, c_int32, c_int32, c_int32]

_lib.llama_time_us.restype = c_int64
_lib.llama_time_us.argtypes = []

# Token data
_lib.llama_token_get_text.restype = c_char_p
_lib.llama_token_get_text.argtypes = [llama_vocab_p, llama_token]

_lib.llama_token_eos.restype = llama_token
_lib.llama_token_eos.argtypes = [llama_vocab_p]


# ============================================================
# GPT-2 byte-level decoder (handles the unicode→bytes conversion)
# ============================================================
def _build_gpt2_unicode_to_bytes():
    """Build the reverse mapping for GPT-2 tokenizer byte encoding.
    GPT-2 maps raw bytes 0-255 to unicode characters:
      - printable chars '!' (33) to '~' (126) stay as-is
      - '¡' (161) to '¬' (172) and '®' (174) to 'ÿ' (255) stay as-is
      - other bytes (0-32, 127, 173) shift to U+0100+ range
    This function builds the reverse mapping (unicode char → byte).
    """
    u2b = {}
    # Characters that represent themselves
    for i in range(33, 127):
        u2b[chr(i)] = i
    for i in range(161, 173):
        u2b[chr(i)] = i
    for i in range(174, 256):
        u2b[chr(i)] = i
    # Characters shifted to U+0100+
    n = 0
    for b in range(256):
        if b not in (list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))):
            u2b[chr(256 + n)] = b
            n += 1
    return u2b

_GPT2_U2B = _build_gpt2_unicode_to_bytes()

def _gpt2_byte_decode(text: str) -> str:
    """Decode GPT-2 byte-level encoded text back to UTF-8 string."""
    bytes_list = []
    for ch in text:
        byte_val = _GPT2_U2B.get(ch)
        if byte_val is not None:
            bytes_list.append(byte_val)
        else:
            # Character not in GPT-2 mapping (e.g., Chinese chars that are valid Unicode)
            # Encode as UTF-8 bytes
            bytes_list.extend(ch.encode('utf-8'))
    return bytes(bytes_list).decode('utf-8', errors='replace')


# ============================================================
# High-level Python wrapper
# ============================================================
class LlamaModel:
    """Minimal wrapper around llama.cpp for text inference."""

    def __init__(self, model_path: str, n_gpu_layers: int = 99,
                 n_ctx: int = 4096, n_threads: int = 4,
                 kv_type: int = 1):  # 1 = GGML_TYPE_F16 (默认), 8 = GGML_TYPE_Q8_0
        self.model_path = model_path.encode('utf-8')

        # Load model
        mparams = _lib.llama_model_default_params()
        mparams.n_gpu_layers = n_gpu_layers
        self.model = _lib.llama_model_load_from_file(self.model_path, mparams)
        if not self.model:
            raise RuntimeError(f"Failed to load model: {model_path}")

        self.vocab = _lib.llama_model_get_vocab(self.model)
        self.eos_token = _lib.llama_vocab_eos(self.vocab)
        self.eot_token = _lib.llama_vocab_eot(self.vocab)

        # Create context
        cparams = _lib.llama_context_default_params()
        cparams.n_ctx = n_ctx
        cparams.n_threads = n_threads
        cparams.n_threads_batch = n_threads
        cparams.n_batch = 512
        cparams.n_ubatch = 512
        cparams.no_perf = True
        # KV cache 量化：type_k/type_v 设为 Q8_0 (8) 可减少 47% 显存、提速 ~8%
        cparams.type_k = kv_type
        cparams.type_v = kv_type
        if kv_type != 1:  # 非 F16 时启用 Flash Attention
            cparams.flash_attn_type = 1  # LLAMA_FLASH_ATTN_TYPE_ENABLED
        self.ctx = _lib.llama_init_from_model(self.model, cparams)
        if not self.ctx:
            raise RuntimeError("Failed to create context")

        self.n_ctx = n_ctx
        self._chat_template = self._get_meta("tokenizer.chat_template")
        kv_name = "Q8_0" if kv_type == 8 else "F16" if kv_type == 1 else f"type{kv_type}"
        print(f"Model loaded: n_ctx={n_ctx}, n_gpu_layers={n_gpu_layers}, kv_cache={kv_name}")

    def _get_meta(self, key: str) -> str:
        """Get a metadata string from the model by key."""
        buf = ctypes.create_string_buffer(8192)
        ret = _lib.llama_model_meta_val_str(
            self.model, key.encode('utf-8'), buf, 8192)
        if ret >= 0:
            return buf.value.decode('utf-8', errors='replace')
        return ""

    def tokenize(self, text: str, add_bos: bool = True, special: bool = True) -> list[int]:
        """Tokenize text, return list of token IDs."""
        text_bytes = text.encode('utf-8')
        n_max = len(text_bytes) + 16
        tokens = (llama_token * n_max)()
        n = _lib.llama_tokenize(self.vocab, text_bytes, len(text_bytes),
                                 tokens, n_max, add_bos, special)
        if n < 0:
            raise RuntimeError(f"Tokenization failed: {n}")
        return list(tokens[:n])

    def detokenize(self, tokens: list[int]) -> str:
        """Convert token IDs back to text, handling GPT-2 byte-level encoding."""
        parts = []
        for t in tokens:
            s = _lib.llama_vocab_get_text(self.vocab, t)
            if s:
                parts.append(s.decode('utf-8', errors='replace'))
        text = ''.join(parts)
        # Apply GPT-2 byte-level decoding (convert unicode escapes back to bytes)
        return _gpt2_byte_decode(text)

    def generate(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.0, top_p: float = 0.9,
                 top_k: int = 50, echo: bool = False) -> str:
        """
        Generate text from a prompt using greedy or temperature sampling.

        Args:
            prompt: Input text
            max_tokens: Maximum tokens to generate
            temperature: 0 = greedy, >0 = sampling with temperature
            top_p: Nucleus sampling threshold
            top_k: Top-K sampling
            echo: Include prompt in output
        Returns:
            Generated text
        """
        # Tokenize
        prompt_tokens = self.tokenize(prompt, add_bos=True, special=True)

        # Build sampler chain
        sparams = _lib.llama_sampler_chain_default_params()
        chain = _lib.llama_sampler_chain_init(sparams)

        if temperature <= 0.0:
            # Greedy: picks the highest probability token
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_greedy())
        else:
            # Sampling: filter then sample from distribution
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_top_k(top_k))
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_top_p(top_p, 1))
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_temp(temperature))
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_dist(42))  # selector

        # Clear KV cache via memory
        mem = _lib.llama_get_memory(self.ctx)
        _lib.llama_memory_clear(mem, True)

        # Main generation loop
        generated_tokens = []
        ctx_size = len(prompt_tokens)

        # Process prompt in batches
        pos = 0
        while pos < len(prompt_tokens):
            batch_size = min(512, len(prompt_tokens) - pos)
            batch_tokens = (llama_token * batch_size)()
            for i in range(batch_size):
                batch_tokens[i] = prompt_tokens[pos + i]
            batch = _lib.llama_batch_get_one(batch_tokens, batch_size)
            ret = _lib.llama_decode(self.ctx, batch)
            if ret != 0:
                raise RuntimeError(f"Decode failed at position {pos}")
            pos += batch_size

        # Generate new tokens
        for i in range(max_tokens):
            # Sample
            token_id = _lib.llama_sampler_sample(chain, self.ctx, -1)

            # Check stop
            if token_id == self.eos_token or token_id == self.eot_token:
                break

            generated_tokens.append(token_id)

            # Decode next
            token_arr = (llama_token * 1)(token_id)
            batch = _lib.llama_batch_get_one(token_arr, 1)
            ret = _lib.llama_decode(self.ctx, batch)
            if ret != 0:
                break

        _lib.llama_sampler_free(chain)

        # Detokenize
        output = self.detokenize(generated_tokens) if generated_tokens else ""

        if echo:
            return prompt + output
        return output

    # ── Prefix Caching ──────────────────────────────────────────
    _prefix_tokens: list[int] = []   # cached prefix token IDs
    _prefix_len: int = 0             # number of tokens in cached prefix

    def cache_prefix(self, prefix: str):
        """
        Pre-compute KV cache for a shared prompt prefix.
        Call once with the static part of your prompt template.
        """
        tokens = self.tokenize(prefix, add_bos=True, special=True)
        mem = _lib.llama_get_memory(self.ctx)
        _lib.llama_memory_clear(mem, True)

        # Process prefix tokens in batches
        pos = 0
        while pos < len(tokens):
            batch_size = min(512, len(tokens) - pos)
            batch_tokens = (llama_token * batch_size)()
            for i in range(batch_size):
                batch_tokens[i] = tokens[pos + i]
            batch = _lib.llama_batch_get_one(batch_tokens, batch_size)
            _lib.llama_decode(self.ctx, batch)
            pos += batch_size

        self._prefix_tokens = tokens
        self._prefix_len = len(tokens)
        print(f"Prefix cached: {self._prefix_len} tokens")

    def generate_cached(self, suffix: str, max_tokens: int = 512,
                        temperature: float = 0.0, top_p: float = 0.9,
                        top_k: int = 50) -> str:
        """
        Generate using a cached prefix. Only processes the suffix tokens.
        Must call cache_prefix() first with the matching prefix.
        """
        if self._prefix_len == 0:
            raise RuntimeError("No prefix cached. Call cache_prefix() first.")

        # Tokenize suffix only (no BOS — prefix already has it)
        suffix_tokens = self.tokenize(suffix, add_bos=False, special=True)

        # Remove any leftover suffix from previous call, keep prefix
        mem = _lib.llama_get_memory(self.ctx)
        _lib.llama_memory_seq_rm(mem, -1, self._prefix_len, -1)

        # Build sampler chain
        sparams = _lib.llama_sampler_chain_default_params()
        chain = _lib.llama_sampler_chain_init(sparams)
        if temperature <= 0.0:
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_greedy())
        else:
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_top_k(top_k))
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_top_p(top_p, 1))
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_temp(temperature))
            _lib.llama_sampler_chain_add(chain, _lib.llama_sampler_init_dist(42))

        # Process only suffix tokens (positions auto-tracked from prefix_len)
        pos = 0
        while pos < len(suffix_tokens):
            batch_size = min(512, len(suffix_tokens) - pos)
            batch_tokens = (llama_token * batch_size)()
            for i in range(batch_size):
                batch_tokens[i] = suffix_tokens[pos + i]
            batch = _lib.llama_batch_get_one(batch_tokens, batch_size)
            _lib.llama_decode(self.ctx, batch)
            pos += batch_size

        # Generate tokens
        generated_tokens = []
        for i in range(max_tokens):
            token_id = _lib.llama_sampler_sample(chain, self.ctx, -1)
            if token_id == self.eos_token or token_id == self.eot_token:
                break
            generated_tokens.append(token_id)
            token_arr = (llama_token * 1)(token_id)
            batch = _lib.llama_batch_get_one(token_arr, 1)
            if _lib.llama_decode(self.ctx, batch) != 0:
                break

        _lib.llama_sampler_free(chain)
        return self.detokenize(generated_tokens) if generated_tokens else ""

    def chat(self, messages: list[dict], max_tokens: int = 512,
             temperature: float = 0.0, top_p: float = 0.9,
             top_k: int = 50) -> str:
        """
        Chat with the model using its built-in chat template.

        Args:
            messages: List of {'role': 'system'|'user'|'assistant', 'content': '...'}
            max_tokens: Maximum tokens to generate
            temperature, top_p, top_k: Sampling params
        Returns:
            Model response text
        """
        # Apply chat template
        if self._chat_template:
            n_msgs = len(messages)
            msg_array = (c_char_p * n_msgs)()
            for i, msg in enumerate(messages):
                msg_array[i] = json.dumps(msg, ensure_ascii=False).encode('utf-8')
            buf = ctypes.create_string_buffer(4096)
            ret = _lib.llama_chat_apply_template(
                self._chat_template.encode('utf-8'),
                None, msg_array, n_msgs, True,
                buf, 4096)
            if ret < 0:
                raise RuntimeError(f"Failed to apply chat template: {ret}")
            prompt = buf.value.decode('utf-8', errors='replace')
        else:
            # Fallback: simple concatenation
            prompt = "\n".join([m['content'] for m in messages])

        return self.generate(prompt, max_tokens=max_tokens,
                           temperature=temperature, top_p=top_p, top_k=top_k)

    def close(self):
        """Free resources."""
        if hasattr(self, 'ctx') and self.ctx:
            _lib.llama_free(self.ctx)
            self.ctx = None
        if hasattr(self, 'model') and self.model:
            _lib.llama_model_free(self.model)
            self.model = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ============================================================
# Test
# ============================================================
if __name__ == '__main__':
    import sys
    model_path = os.path.join(_ROOT_DIR, 'Hy-MT2-1.8B-Q8_0.gguf')
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        sys.exit(1)

    print(f"Loading: {model_path}")
    llm = LlamaModel(model_path, n_gpu_layers=99, n_ctx=2048)

    # Use chat template for translation
    messages = [
        {"role": "system", "content": "You are a professional translator. Translate English to Chinese accurately."},
        {"role": "user", "content": "Artificial intelligence has transformed many industries."},
    ]
    print(f"\nChat template: {llm._chat_template[:100]}...")
    print(f"\nMessages: {messages}")
    print("\nGenerating...")
    output = llm.chat(messages, max_tokens=256, temperature=0.0)
    print(f"\nOutput:\n{output}")

    llm.close()
