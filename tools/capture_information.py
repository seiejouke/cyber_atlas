"""Build an illustrative atlas and capture the actual information-heat UI."""
import argparse
from dataclasses import replace
from math import pi
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.model import Atlas, Design, InformationEntry, Node, Subconcept
from atlas.storage import write_atlas


def example():
    topics = (
        ("Copper", "Fiber", "Radio", "Encoding", "Modulation", "Clocking", "Noise", "Signal loss", "Interfaces", "Bandwidth", "Cabling", "Repeaters"),
        ("Ethernet", "Frames", "MAC", "Switching", "VLANs", "Bridging", "ARP", "Wi-Fi", "STP", "MTU", "LLDP", "LACP"),
        ("IPv4", "Routing", "Subnets", "ICMP", "NAT", "IPv6", "Gateways", "Route tables", "Forwarding", "Tunnels", "Firewall", "Multicast"),
        ("TCP", "UDP", "Ports", "Connections", "Congestion", "Flow control", "Reliability", "Handshake", "Retransmission", "Segments", "Sockets", "Checksums"),
        ("Sessions", "RPC", "Dialogs", "Keepalive", "Recovery", "Tokens", "Checkpoints", "State", "Negotiation", "Synchronization", "Timeouts", "Resumption"),
        ("TLS", "Encoding", "Serialization", "Compression", "ASN.1", "Certificates", "JSON", "UTF-8", "Formats", "Encryption", "Decoding", "Representation"),
        ("HTTP", "DNS", "SSH", "SMTP", "DHCP", "NTP", "IMAP", "SNMP", "HTTPS", "FTP", "LDAP", "APIs"),
    )
    nodes, children, information = [], [], []

    def record(identity, name, count):
        return tuple(InformationEntry(f"{identity}-entry-{i}", identity, f"{name}: observation {i+1}",
                     f"Illustrative entry {i+1} about {name}. Replace this example with your own explanation, observation or worked example.")
                     for i in range(count))

    levels = (0, 1, 2, 4, 0, 8, 2, 1, 16, 4, 2, 32)
    for layer, names in enumerate(topics, 1):
        for index, name in enumerate(names):
            identity = "firewall" if name == "Firewall" else f"layer-{layer}-concept-{index}"
            depth = index // 4
            node = Node(identity, name, layer, None, depth,
                        "Personal notes are independent of the information entries counted by heat.",
                        slot=index % 4 * 4 + layer % 4)
            nodes.append(node)
            count = 8 if identity == "firewall" else levels[(index + layer) % len(levels)]
            information.extend(record(identity, name, count))
    for i, (name, count) in enumerate((("Next-generation firewall", 4), ("Packet filtering", 2),
                                      ("Stateful inspection", 10), ("Application proxy", 0))):
        child = Subconcept(f"firewall-type-{i}", "firewall", name,
                           f"Personal notes about {name.lower()}.", orbit_slot=i*2)
        children.append(child)
        information.extend(record(child.id, name, count))
    return Atlas(tuple(nodes), replace(Design(), protocols=()), tuple(children), tuple(information))


def main_note_example():
    """Demonstrate automatic note counts, different temperatures and collapsed rings."""
    base = example()
    nodes, children, entries = [], [], []
    levels = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 15)
    for index, node in enumerate(base.nodes):
        if node.id == "firewall":
            node = replace(node, id="multiplexing-strategy", name="Multiplexing strategy", layer=1, slot=11)
        node = replace(node, notes=f"Main note about {node.name}. This saved concept counts automatically as one item.")
        nodes.append(node)
        count = 0 if node.id == "multiplexing-strategy" else levels[index % len(levels)]
        if node.name == "HTTP":
            count = 9
        for entry in range(count):
            entries.append(InformationEntry(f"{node.id}-extra-{entry}", node.id, f"Additional observation {entry+1}",
                                           f"Illustrative additional information about {node.name}, item {entry+1}."))
    for parent_name, names in (
        ("Multiplexing strategy", ("Time-division multiplexing", "Statistical time-division multiplexing", "Frequency-division multiplexing")),
        ("Ethernet", ("Gigabit Ethernet", "10 Gigabit Ethernet")),
        ("HTTP", ("HTTP/1.1", "HTTP/2", "HTTP/3")),
    ):
        parent = next(node for node in nodes if node.name == parent_name)
        for index, name in enumerate(names):
            children.append(Subconcept(f"{parent.id}-orbital-{index}", parent.id, name,
                                       f"Main note about {name}. No additional entry is needed for this note to count.",
                                       orbit_slot=index*2))
    return Atlas(tuple(nodes), base.design, tuple(children), tuple(entries))


def capture(document, *, main_notes=False):
    import tkinter as tk
    from PIL import ImageGrab
    from atlas.ui import AtlasApp

    with TemporaryDirectory(prefix="information-capture-", dir=ROOT / "build") as folder:
        path = Path(folder) / "atlas.json"
        write_atlas(path, document, backup=False)
        root = tk.Tk()
        app = AtlasApp(root, path, document, automatic_updates=False)
        try:
            root.geometry("1500x960+20+20")
            app.set_view_mode("nodes")
            app._load_editor(document.get("multiplexing-strategy" if main_notes else "firewall"))
            app.information.color_mode.set("Information heat")
            app.information.change_color()
            app.scene.yaw, app.scene.elevation = pi/4, pi/15
            app.scene.scale = 4.4
            app.scene._apply_camera()
            app._set_status(f"Illustrative atlas / {len(document.nodes)} main notes / {len(document.subconcepts)} subconcepts / {len(document.information_entries)} additional entries")

            def save(name):
                app.request_render()
                for _ in range(12):
                    root.update()
                    time.sleep(.04)
                target = ROOT / "docs" / name
                if sys.platform == "win32":
                    ImageGrab.grab(window=root.winfo_id()).save(target)
                else:
                    x, y = root.winfo_rootx(), root.winfo_rooty()
                    ImageGrab.grab(bbox=(x, y, x+root.winfo_width(), y+root.winfo_height())).save(target)
                print("Captured", target.name, flush=True)

            save("main-note-heat-overview.png" if main_notes else "information-heat-overview.png")
            app.clusters.explore()
            save("main-note-heat-cluster.png" if main_notes else "information-heat-cluster.png")
        finally:
            app.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-only", action="store_true")
    parser.add_argument("--main-notes", action="store_true", help="Capture the automatic main-note heat and parent-ring source preview")
    args = parser.parse_args()
    atlas = main_note_example() if args.main_notes else example()
    filename = "main_note_heat_atlas.json" if args.main_notes else "information_heat_atlas.json"
    write_atlas(ROOT / "examples" / filename, atlas, backup=False)
    print(f"Example: {len(atlas.nodes)} concepts and {len(atlas.information_entries)} recorded entries.")
    if not args.example_only:
        capture(atlas, main_notes=args.main_notes)
