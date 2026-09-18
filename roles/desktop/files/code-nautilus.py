from subprocess import Popen
from gi.repository import Nautilus, GObject


class VSCodeExtension(GObject.GObject, Nautilus.MenuProvider):
    def launch_vscode(self, _menu, files):
        paths = [
            f.get_location().get_path()
            for f in files
            if f.get_location() and f.get_location().get_path()
        ]
        if paths:
            Popen(["code"] + paths)

    def get_file_items(self, *args):
        files = args[-1]
        item = Nautilus.MenuItem(
            name="VSCodeOpen",
            label="Open in VS Code",
            tip="Open the selected files or folders in Visual Studio Code",
        )
        item.connect("activate", self.launch_vscode, files)
        return [item]

    def get_background_items(self, *args):
        file_ = args[-1]
        item = Nautilus.MenuItem(
            name="VSCodeOpenBackground",
            label="Open in VS Code",
            tip="Open the current directory in Visual Studio Code",
        )
        item.connect("activate", self.launch_vscode, [file_])
        return [item]
