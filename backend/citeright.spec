# PyInstaller build of the CiteRight desktop app (single executable).
#   1. cd frontend && npm ci && STATIC_EXPORT=1 npm run build
#   2. cd backend  && pip install -r requirements.txt pyinstaller && pyinstaller citeright.spec
# The result is dist/CiteRight(.exe). Build on the operating system you are targeting.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("app/data", "app/data"),
    ("../frontend/out", "frontend"),
]
datas += collect_data_files("docx")
datas += collect_data_files("reportlab")

hiddenimports = collect_submodules("uvicorn") + collect_submodules("reportlab.pdfbase")
hiddenimports += ["python_multipart", "multipart", "lxml.etree", "lxml._elementpath"]  # uploads and Word files

hiddenimports += ["pymupdf"]  # PDF reading

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    # Not needed by the desktop app: PostgreSQL driver, test tools, and PyMuPDF's optional
    # layout-analysis add-ons (they would triple the size of the executable).
    excludes=["psycopg", "psycopg_binary", "pytest", "tkinter", "pymupdf.layout", "pymupdf4llm", "pymupdf_layout", "onnxruntime", "numpy"],
)


def _unused(entry) -> bool:
    name = entry[0].replace("\\", "/").lower()
    return any(part in name for part in ("pymupdf/layout", "pymupdf/mupdf-devel", "onnxruntime", "networkx", "numpy"))


a.datas = [entry for entry in a.datas if not _unused(entry)]
a.binaries = [entry for entry in a.binaries if not _unused(entry)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="CiteRight",
    console=True,  # the window shows the address and is how the app is closed
    upx=False,
)
