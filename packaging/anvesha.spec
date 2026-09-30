# PyInstaller spec - build on Windows with:  pyinstaller packaging\anvesha.spec --noconfirm
# Produces dist\ANVESHA\ANVESHA.exe (one-folder build; double-click opens the GUI).
import os
block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, ".."))
a = Analysis([os.path.join(root, "packaging", "launcher.py")], pathex=[root],
             datas=[(os.path.join(root, "anvesha", "ui", "static"), "anvesha/ui/static"),
                    (os.path.join(root, "configs"), "configs"),
                    (os.path.join(root, "models"), "models")],
             hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
                            "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "onnxruntime"],
             excludes=["torch", "tkinter"], cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ANVESHA", console=True)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="ANVESHA")
