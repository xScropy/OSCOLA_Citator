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

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["psycopg", "psycopg_binary", "pytest", "tkinter"],
)
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
