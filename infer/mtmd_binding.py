"""
Minimal ctypes binding for mtmd.dll (multimodal support).
Wraps only the functions needed for OCR (vision + text).
"""
import ctypes, os
from ctypes import (
    c_void_p, c_char_p, c_int32, c_uint32, c_size_t,
    c_float, c_double, c_bool, POINTER, Structure, byref
)

_DLL_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_DLL_DIR)

os.add_dll_directory(_ROOT_DIR)
os.add_dll_directory(r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin')

_mtmd = ctypes.CDLL(os.path.join(_ROOT_DIR, 'mtmd.dll'))

# Opaque types
mtmd_context_p       = c_void_p
mtmd_bitmap_p         = c_void_p
mtmd_input_chunks_p   = c_void_p
mtmd_input_chunk_p    = c_void_p
mtmd_batch_p          = c_void_p
mtmd_helper_video_p   = c_void_p

# ============================================================
# Struct: mtmd_context_params
# ============================================================
class mtmd_context_params(Structure):
    _fields_ = [
        ("use_gpu", c_bool),
        ("print_timings", c_bool),
        ("n_threads", c_int32),
        ("image_marker", c_char_p),
        ("media_marker", c_char_p),
        ("flash_attn_type", c_int32),
        ("warmup", c_bool),
        ("image_min_tokens", c_int32),
        ("image_max_tokens", c_int32),
        ("cb_eval", c_void_p),
        ("cb_eval_user_data", c_void_p),
        ("batch_max_tokens", c_int32),
        ("progress_callback", c_void_p),
        ("progress_callback_user_data", c_void_p),
    ]

# ============================================================
# Struct: mtmd_input_text
# ============================================================
class mtmd_input_text(Structure):
    _fields_ = [
        ("text", c_char_p),
        ("text_len", c_size_t),
        ("add_special", c_bool),
        ("parse_special", c_bool),
    ]

# ============================================================
# Struct: mtmd_helper_bitmap_wrapper
# ============================================================
class mtmd_helper_bitmap_wrapper(Structure):
    _fields_ = [
        ("bitmap", mtmd_bitmap_p),
        ("video_ctx", mtmd_helper_video_p),
    ]

# ============================================================
# Struct: mtmd_decoder_pos
# ============================================================
class mtmd_decoder_pos(Structure):
    _fields_ = [
        ("t", c_uint32),
        ("x", c_uint32),
        ("y", c_uint32),
        ("z", c_uint32),
    ]

# ============================================================
# Function signatures
# ============================================================

_mtmd.mtmd_context_params_default.restype = mtmd_context_params
_mtmd.mtmd_context_params_default.argtypes = []

_mtmd.mtmd_default_marker.restype = c_char_p
_mtmd.mtmd_default_marker.argtypes = []

_mtmd.mtmd_init_from_file.restype = mtmd_context_p
_mtmd.mtmd_init_from_file.argtypes = [c_char_p, c_void_p, mtmd_context_params]

_mtmd.mtmd_free.restype = None
_mtmd.mtmd_free.argtypes = [mtmd_context_p]

_mtmd.mtmd_support_vision.restype = c_bool
_mtmd.mtmd_support_vision.argtypes = [mtmd_context_p]

# Bitmap creation from raw data
_mtmd.mtmd_bitmap_init.restype = mtmd_bitmap_p
_mtmd.mtmd_bitmap_init.argtypes = [c_uint32, c_uint32, c_void_p]

_mtmd.mtmd_bitmap_free.restype = None
_mtmd.mtmd_bitmap_free.argtypes = [mtmd_bitmap_p]

# Bitmap from file (helper)
_mtmd.mtmd_helper_bitmap_init_from_file.restype = mtmd_helper_bitmap_wrapper
_mtmd.mtmd_helper_bitmap_init_from_file.argtypes = [mtmd_context_p, c_char_p, c_bool]

# Tokenize
_mtmd.mtmd_input_chunks_init.restype = mtmd_input_chunks_p
_mtmd.mtmd_input_chunks_init.argtypes = []

_mtmd.mtmd_input_chunks_free.restype = None
_mtmd.mtmd_input_chunks_free.argtypes = [mtmd_input_chunks_p]

_mtmd.mtmd_tokenize.restype = c_int32
_mtmd.mtmd_tokenize.argtypes = [mtmd_context_p, mtmd_input_chunks_p,
                                  POINTER(mtmd_input_text),
                                  POINTER(mtmd_bitmap_p), c_size_t]

# Eval helper (handles both text and image chunks automatically)
_mtmd.mtmd_helper_eval_chunks.restype = c_int32
_mtmd.mtmd_helper_eval_chunks.argtypes = [mtmd_context_p, c_void_p,
                                            mtmd_input_chunks_p, c_int32,
                                            c_int32, c_int32, c_bool,
                                            POINTER(c_int32)]

# Chunk info
_mtmd.mtmd_input_chunks_size.restype = c_size_t
_mtmd.mtmd_input_chunks_size.argtypes = [mtmd_input_chunks_p]

_mtmd.mtmd_input_chunk_get_type.restype = c_int32
_mtmd.mtmd_input_chunk_get_type.argtypes = [mtmd_input_chunk_p]

_mtmd.mtmd_input_chunk_get_tokens_text.restype = c_void_p  # returns const llama_token*
_mtmd.mtmd_input_chunk_get_tokens_text.argtypes = [mtmd_input_chunk_p, POINTER(c_size_t)]

_mtmd.mtmd_input_chunk_get_n_tokens.restype = c_size_t
_mtmd.mtmd_input_chunk_get_n_tokens.argtypes = [mtmd_input_chunk_p]

_mtmd.mtmd_helper_get_n_tokens.restype = c_size_t
_mtmd.mtmd_helper_get_n_tokens.argtypes = [mtmd_input_chunks_p]

# Logging
_mtmd.mtmd_log_set.restype = None
_mtmd.mtmd_log_set.argtypes = [c_void_p, c_void_p]


# ============================================================
# OCR-specific wrapper
# ============================================================
class MtmdOCR:
    """
    OCR using Unlimited-OCR via mtmd (multimodal) library.
    Handles mmproj loading, image preprocessing, and vision+text inference.
    """

    def __init__(self, mmproj_path: str, text_model_ptr,
                 n_threads: int = 4, use_gpu: bool = True):
        """
        Args:
            mmproj_path: Path to mmproj-Unlimited-OCR-F16.gguf
            text_model_ptr: llama_model pointer from llama_binding
            n_threads: CPU threads
            use_gpu: Whether to use GPU for vision encoding
        """
        params = _mtmd.mtmd_context_params_default()
        params.use_gpu = use_gpu
        params.n_threads = n_threads
        params.print_timings = False
        params.warmup = True
        params.image_min_tokens = 0
        params.image_max_tokens = 0  # read from metadata

        self.ctx = _mtmd.mtmd_init_from_file(
            mmproj_path.encode('utf-8'),
            text_model_ptr,
            params)
        if not self.ctx:
            raise RuntimeError(f"Failed to init mtmd context from {mmproj_path}")

        self.has_vision = _mtmd.mtmd_support_vision(self.ctx)
        print(f"MTMD loaded: vision={self.has_vision}")

    def load_bitmap_from_file(self, image_path: str):
        """Load an image file as a bitmap. Returns mtmd_helper_bitmap_wrapper."""
        result = _mtmd.mtmd_helper_bitmap_init_from_file(
            self.ctx,
            image_path.encode('utf-8'),
            False)  # not placeholder
        if not result.bitmap:
            raise RuntimeError(f"Failed to load image: {image_path}")
        return result

    def tokenize_prompt_with_images(self, prompt: str,
                                     bitmaps: list) -> mtmd_input_chunks_p:
        """
        Tokenize a prompt with image markers (<__media__>).
        Number of markers must match number of bitmaps.

        Args:
            prompt: Text with <__media__> markers
            bitmaps: List of mtmd_bitmap pointers

        Returns:
            mtmd_input_chunks pointer
        """
        text_struct = mtmd_input_text()
        text_struct.text = prompt.encode('utf-8')
        text_struct.text_len = len(prompt.encode('utf-8'))
        text_struct.add_special = True
        text_struct.parse_special = True

        chunks = _mtmd.mtmd_input_chunks_init()

        n_bitmaps = len(bitmaps)
        bitmap_array = (mtmd_bitmap_p * n_bitmaps)()
        for i, bm in enumerate(bitmaps):
            bitmap_array[i] = bm

        ret = _mtmd.mtmd_tokenize(self.ctx, chunks,
                                   byref(text_struct),
                                   bitmap_array, n_bitmaps)
        if ret != 0:
            raise RuntimeError(f"mtmd_tokenize failed: {ret}")
        return chunks

    def eval_chunks(self, llama_ctx_ptr, chunks, n_past: int = 0,
                    seq_id: int = 0, n_batch: int = 512,
                    logits_last: bool = True) -> int:
        """
        Evaluate all chunks (text + images) using llama context.
        Returns new n_past value.
        """
        new_n_past = c_int32(n_past)
        ret = _mtmd.mtmd_helper_eval_chunks(
            self.ctx, llama_ctx_ptr, chunks,
            n_past, seq_id, n_batch, logits_last,
            byref(new_n_past))
        if ret != 0:
            raise RuntimeError(f"mtmd_helper_eval_chunks failed: {ret}")
        return new_n_past.value

    def total_tokens(self, chunks) -> int:
        """Get total number of tokens in all chunks."""
        return _mtmd.mtmd_helper_get_n_tokens(chunks)

    def get_marker(self) -> str:
        """Get the default media marker string."""
        marker = _mtmd.mtmd_default_marker()
        return marker.decode('utf-8') if marker else "<__media__>"

    def free_chunks(self, chunks):
        """Free input chunks."""
        _mtmd.mtmd_input_chunks_free(chunks)

    def free_bitmap(self, wrapper):
        """Free a bitmap loaded from file. Call bitmap_free on wrapper.bitmap."""
        if wrapper.bitmap:
            _mtmd.mtmd_bitmap_free(wrapper.bitmap)
        # video_ctx is freed together with bitmap

    def close(self):
        if self.ctx:
            _mtmd.mtmd_free(self.ctx)
            self.ctx = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
