"""Create an editable example and capture the real source FlowNotes interface."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.model import Atlas, Design, FlowNote, FlowStep, FlowConnection, InformationEntry, Node, Subconcept
from atlas.storage import write_atlas
from atlas.study_text import concept_link


def make_example():
    design = Design(protocols=())
    interface = Node('packet-interface', 'Network interface', 2, None, 0,
                     '## Definition\nA network interface connects a device to a link.\n\n## Example\nAn Ethernet port receives or sends a frame.', slot=7)
    ip = Node('packet-ipv4', 'IPv4', 3, None, 1,
              '## Definition\nAn IPv4 packet carries source and destination addresses.\n\n## Mechanism\nThe destination helps a router choose where to forward the packet.', slot=9)
    firewall = Node('packet-firewall', 'Firewall', 3, None, 2,
                    '## Definition\nA firewall applies policy to traffic.\n\n## Example\nA rule can permit or block a packet.', slot=1)
    route = Node('packet-route', 'Routing table', 3, None, 3,
                 '## Definition\nA routing table records routes used to choose a next hop.\n\n## Mechanism\nUse the destination to choose an outgoing route.', slot=13)
    arp = Node('packet-arp', 'ARP', 2, None, 2,
               '## Definition\nARP resolves an IPv4 address to a link address on a local network.\n\n## Example\nUse a cached neighbor entry or make a request when needed.', slot=11)
    context = tuple(Node(f'context-{i}', name, layer, None, depth, 'A contextual concept outside this process.', slot=slot)
                    for i, (name, layer, depth, slot) in enumerate((
                        ('Signals', 1, 1, 12), ('TCP', 4, 1, 7), ('UDP', 4, 0, 1),
                        ('Sessions', 5, 0, 6), ('TLS', 6, 1, 3), ('DNS', 7, 0, 5), ('HTTP', 7, 1, 9))))
    children = tuple(Subconcept(f'firewall-type-{i}', firewall.id, name, note, i*2)
                     for i, (name, note) in enumerate((
                         ('Packet filtering', '## Definition\nApply rules using packet header fields.'),
                         ('Stateful inspection', '## Definition\nConsider tracked connection context.'),
                         ('Application proxy', '## Definition\nMediate communication at the application level.'),
                         ('Next-generation firewall', '## Definition\nCombine several policy and inspection capabilities.'))))
    concepts = (interface, ip, firewall, route, arp, interface)
    actions = ('Receive packet', 'Read destination', 'Apply packet policy', 'Look up route', 'Resolve next hop', 'Send packet')
    explanations = (
        'Identify the incoming frame and the concept it belongs to.',
        'Read the destination address and relate it to ' + concept_link(route.id, route.name) + '.',
        '## Mechanism\nCheck whether the packet may continue. Choose **Allowed** or **Blocked** below.',
        'Use the destination address to choose an outgoing route.\n\nSee ' + concept_link(ip.id, 'the IPv4 concept') + '.',
        'Use a known neighbor address or resolve it when this example requires local IPv4 delivery.',
        'Send the outgoing frame. This is a second occurrence of the same **Network interface** concept.')
    steps = tuple(FlowStep(f'packet-step-{i+1}', concept.id, title, concept.name, text,
                           'What would you expect to happen next?' if i == 3 else '')
                  for i, (concept, title, text) in enumerate(zip(concepts, actions, explanations)))
    edges = tuple(FlowConnection(f'packet-edge-{i+1}', left.id, right.id, 'Allowed' if i == 2 else 'Next')
                  for i, (left, right) in enumerate(zip(steps, steps[1:])))
    edges += (FlowConnection('packet-blocked', steps[2].id, None, 'Blocked'),)
    flow = FlowNote('packet-forwarding', 'Packet forwarding',
                    'A simplified, manually authored learning example. Device-specific routing and policy order can differ.', steps, edges)
    compare_steps = tuple(FlowStep(f'compare-{i}', child.id, f'Examine {child.name}', child.name,
                                  'Compare this shared concept with ' + concept_link(firewall.id, 'Firewall') + '.')
                          for i, child in enumerate(children))
    compare = FlowNote('firewall-comparison', 'Compare firewall types',
                       'Read each existing suborbital note. These steps form a comparison guide, not a simulated packet path.',
                       compare_steps, tuple(FlowConnection(f'compare-edge-{i}', a.id, b.id, 'Compare next')
                                            for i, (a, b) in enumerate(zip(compare_steps, compare_steps[1:]))))
    entries = tuple(InformationEntry(f'policy-entry-{i}', firewall.id, title, body) for i, (title, body) in enumerate((
        ('Match criteria', 'A rule can describe the traffic it applies to.'),
        ('Policy action', 'A matching rule has a permitted or blocked outcome in this example.'),
        ('Inspect context', 'Stateful policies also use tracked context.'),
        ('Compare types', 'Different firewall mechanisms inspect different aspects of traffic.'))))
    return Atlas((interface, ip, firewall, route, arp)+context, design, children, entries, (flow, compare))


def capture(directory, document):
    from tempfile import TemporaryDirectory
    import time
    import tkinter as tk
    from PIL import ImageGrab
    from atlas.ui import AtlasApp

    def settle(root, app):
        deadline = time.monotonic()+4
        for _ in range(5):
            root.update()
            time.sleep(.03)
        while (app._render_job or app.label_manager._settle_job or app.label_manager._animation_job) and time.monotonic() < deadline:
            root.update()
            time.sleep(.025)

    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=ROOT / 'build') as folder:
        path = Path(folder) / 'atlas.json'
        write_atlas(path, document, backup=False)
        root = tk.Tk()
        app = AtlasApp(root, path, document, automatic_updates=False)
        try:
            root.geometry('1500x960+20+20')
            app.set_view_mode('nodes')
            app.information.color_mode.set('Information heat')
            app.information.change_color()
            app.flows.open()
            app.flows.show_flow_layers()
            app.flows.show_entire_flow()
            steps = app.flows.draft.steps

            def save(name):
                app._set_status('FlowNotes · unpackaged source preview · illustrative data')
                app.request_render()
                settle(root, app)
                if name == 'flownotes-branch.png':
                    frame = app.flows.choices_frame
                    limit = app.flows.study_scroll.canvas.winfo_rooty()+app.flows.study_scroll.canvas.winfo_height()
                    assert frame.winfo_rooty()+frame.winfo_height() <= limit, 'Branch choices must be visible without scrolling at this window size'
                ImageGrab.grab(window=root.winfo_id()).save(directory / name)

            app.flows.select_step(steps[2].id)
            app.flows.set_mode('edit')
            save('flownotes-editor.png')
            app.flows.set_mode('study')
            app.flows.select_step(steps[3].id)
            save('flownotes-study.png')
            app.flows.select_step(steps[2].id)
            app.flows.choice.set(next(e.id for e in app.flows.run.choices if e.label == 'Allowed'))
            app.flows.choose_branch()
            save('flownotes-branch.png')
            app.flows.load(document.flows[1], mode='study')
            app.flows.show_entire_flow()
            save('flownotes-suborbitals.png')
            root.geometry('1020x780+20+20')
            save('flownotes-minimum.png')
            print('Captured five real source views with disposable data in', directory)
        finally:
            app.shutdown()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/flows-previews')
    parser.add_argument('--example', type=Path)
    parser.add_argument('--example-only', action='store_true')
    args = parser.parse_args()
    document = make_example()
    if args.example:
        write_atlas(args.example, document, backup=False)
    if not args.example_only:
        capture(args.output, document)
