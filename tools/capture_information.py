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


def capture(document):
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
            app._load_editor(document.get("firewall"))
            app.information.color_mode.set("Information heat")
            app.information.change_color()
            app.scene.yaw, app.scene.elevation = pi/4, pi/15
            app.scene.scale = 4.4
            app.scene._apply_camera()
            app._set_status(f"Example atlas / {len(document.nodes)} concepts / {len(document.information_entries)} information entries")

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

            save("information-heat-overview.png")
            app.clusters.explore()
            save("information-heat-cluster.png")
        finally:
            app.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-only", action="store_true")
    args = parser.parse_args()
    atlas = example()
    write_atlas(ROOT / "examples/information_heat_atlas.json", atlas, backup=False)
    print(f"Example: {len(atlas.nodes)} concepts and {len(atlas.information_entries)} recorded entries.")
    if not args.example_only:
        capture(atlas)
