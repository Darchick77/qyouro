"""DataMatrix encoder using libdmtx-64.dll (v0.7.4)."""
import ctypes
import numpy as np
from PIL import Image

DLL_PATH = r'C:\Users\talki\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\pylibdmtx\libdmtx-64.dll'
_lib = ctypes.CDLL(DLL_PATH)

_lib.dmtxEncodeCreate.restype = ctypes.c_void_p
_lib.dmtxEncodeCreate.argtypes = []
_lib.dmtxEncodeSetProp.restype = ctypes.c_int
_lib.dmtxEncodeSetProp.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
_lib.dmtxEncodeDataMatrix.restype = ctypes.c_int
_lib.dmtxEncodeDataMatrix.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
_lib.dmtxEncodeDestroy.restype = ctypes.c_int
_lib.dmtxEncodeDestroy.argtypes = [ctypes.c_void_p]
_lib.dmtxImageGetProp.restype = ctypes.c_int
_lib.dmtxImageGetProp.argtypes = [ctypes.c_void_p, ctypes.c_int]


def encode(text: str, module_size: int = 8, margin: int = 4) -> Image.Image:
    """Encode text into a DataMatrix PIL Image (grayscale)."""
    data = text.encode('utf-8')
    arr = (ctypes.c_ubyte * len(data))(*data)

    enc = _lib.dmtxEncodeCreate()
    if not enc:
        raise RuntimeError("dmtxEncodeCreate failed")

    _lib.dmtxEncodeSetProp(enc, 103, module_size)  # DmtxPropModuleSize
    _lib.dmtxEncodeSetProp(enc, 102, margin)        # DmtxPropMarginSize

    ret = _lib.dmtxEncodeDataMatrix(enc, len(data), arr)
    if not ret:
        _lib.dmtxEncodeDestroy(enc)
        raise RuntimeError("dmtxEncodeDataMatrix failed")

    img_ptr = ctypes.c_void_p.from_address(enc + 40).value
    w = _lib.dmtxImageGetProp(img_ptr, 300)
    h = _lib.dmtxImageGetProp(img_ptr, 301)
    bpp = ctypes.c_int.from_address(img_ptr + 16).value
    row_size = ctypes.c_int.from_address(img_ptr + 24).value
    pxl_ptr = ctypes.c_void_p.from_address(img_ptr + 72).value

    total = h * row_size
    raw = (ctypes.c_ubyte * total).from_address(pxl_ptr)
    arr = np.frombuffer(raw, dtype=np.uint8).copy().reshape(h, row_size)

    if bpp == 3:
        arr = arr[:, :w * 3].reshape(h, w, 3).min(axis=2)
    else:
        if row_size > w:
            arr = arr[:, :w]

    _lib.dmtxEncodeDestroy(enc)
    return Image.fromarray(arr.astype(np.uint8), mode='L')
