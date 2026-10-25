"""Capture the implemented orbital-cluster interface using a temporary atlas."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import tkinter as tk

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.model import Atlas, Node, Subconcept
from atlas.storage import write_atlas
from atlas.ui import AtlasApp


def main():
    parent = Node('firewall', 'Firewall', 3, 'IPv4', 1, 'Firewall concepts and their related types.', slot=5)
    names = ('Packet filtering', 'Stateful inspection', 'Application proxy', 'Next-generation firewall')
    children = tuple(Subconcept(f'type-{i}', parent.id, name,
        'Tracks the state of active connections.\n\nExample\nAllow return traffic for an established connection.' if i == 1
        else f'Study notes for {name.lower()}.', orbit_slot=i*2) for i, name in enumerate(names))
    document = Atlas((parent,), subconcepts=children)
    with TemporaryDirectory(prefix='cluster-capture-', dir=ROOT / 'build') as folder:
        path = Path(folder) / 'atlas.json'
        write_atlas(path, document, backup=False)
        root = tk.Tk()
        app = AtlasApp(root, path, document, automatic_updates=False)
        try:
            root.geometry('1300x860+30+30')
            def pump():
                app.request_render()
                for _ in range(12):
                    root.update()
                    time.sleep(.04)
            def capture(name):
                pump()
                target = ROOT / 'docs' / name
                if sys.platform == 'win32':
                    ImageGrab.grab(window=root.winfo_id()).save(target)
                else:
                    x, y = root.winfo_rootx(), root.winfo_rooty()
                    ImageGrab.grab(bbox=(x, y, x+root.winfo_width(), y+root.winfo_height())).save(target)
                print('Captured', name, flush=True)
            app.set_view_mode('nodes')
            app.clusters.select_child(children[1].id)
            app.scene.yaw = 0
            app.scene._apply_camera()
            app._set_status('Orbital cluster / 4 independent subconcepts')
            capture('orbital-cluster.png')
            app.set_view_mode('blocks')
            app.clusters.parent_note()
            app.scene.reset_camera()
            app.scene.scale = 2.6
            app.scene.target = list(app.scene.meshes[parent.id].center)
            app.scene._apply_camera()
            capture('orbital-cluster-blocks.png')
        finally:
            app.shutdown()


if __name__ == '__main__':
    main()
