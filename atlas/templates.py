"""Built-in, editable example atlases used by the template browser."""
from __future__ import annotations

from dataclasses import dataclass

from .model import ANGULAR_SLOTS, CENTER_DEPTH, Atlas, Design, Layer, Node, Protocol


@dataclass(frozen=True, slots=True)
class AtlasTemplate:
    key: str
    name: str
    description: str
    atlas: Atlas


_COLORS = ("#65b6a1", "#70cbd8", "#8ca9da", "#9c8bdb", "#cb96ba", "#edbb69", "#e68172")


def _template(
    key: str,
    name: str,
    description: str,
    layer_names: tuple[str, ...],
    protocol_names: tuple[str, ...],
    rows: tuple[tuple[int, str | None, str, int, int, str], ...],
    *,
    layer_caption: str,
    protocol_caption: str,
) -> AtlasTemplate:
    layers = tuple(
        Layer(f"{key}-layer-{index + 1}", layer_name, _COLORS[index % len(_COLORS)])
        for index, layer_name in enumerate(layer_names)
    )
    protocols = tuple(Protocol(f"{key}-type-{index + 1}", protocol_name)
                      for index, protocol_name in enumerate(protocol_names))
    protocol_ids = {protocol.name: protocol.id for protocol in protocols}
    nodes = tuple(
        Node(
            f"template-{key}-{index + 1}",
            title,
            layers[layer_index].id,
            None if protocol_name is None else protocol_ids[protocol_name],
            depth,
            notes,
            slot=slot,
            span=ANGULAR_SLOTS if depth == CENTER_DEPTH else 1,
        )
        for index, (layer_index, protocol_name, title, depth, slot, notes) in enumerate(rows)
    )
    design = Design(layers, protocols, layer_caption, protocol_caption, "title")
    return AtlasTemplate(key, name, description, Atlas(nodes, design))


BLANK = AtlasTemplate(
    "blank",
    "Blank atlas",
    "A clean starting point with one editable axis level.",
    Atlas(design=Design(
        (Layer("blank-layer-1", "Starting point", _COLORS[0]),),
        (),
        "Level",
        "Category",
        "title",
    )),
)


PYTHON = _template(
    "python",
    "Python",
    "Language concepts, the standard library, packages, frameworks, and development tools.",
    ("Language basics", "Standard library", "Packages", "Frameworks", "Tooling"),
    ("Concept", "Module", "Package", "Framework", "Tool"),
    (
        (0, "Concept", "Python essentials", CENTER_DEPTH, 0, "Start with values, expressions, names, and readable code."),
        (0, "Concept", "Variables and values", 0, 0, "Explore assignment, mutability, and Python's object model."),
        (0, "Concept", "Control flow", 0, 5, "Compare conditions, loops, matching, and comprehensions."),
        (0, "Concept", "Functions", 1, 10, "Record examples involving parameters, scope, and return values."),
        (1, "Module", "Built-in toolbox", CENTER_DEPTH, 0, "Map the modules that solve common tasks without extra dependencies."),
        (1, "Module", "pathlib", 0, 1, "Work with filesystem paths as objects."),
        (1, "Module", "json", 1, 6, "Encode and decode portable structured data."),
        (1, "Module", "datetime", 2, 11, "Represent dates, times, durations, and time zones."),
        (2, "Package", "Package ecosystem", CENTER_DEPTH, 0, "Collect third-party libraries that support your projects."),
        (2, "Package", "NumPy", 1, 2, "Arrays and numerical operations."),
        (2, "Package", "pandas", 2, 7, "Tabular data exploration and transformation."),
        (2, "Package", "Requests", 3, 12, "Readable HTTP client workflows."),
        (3, "Framework", "Application frameworks", CENTER_DEPTH, 0, "Compare framework scope, conventions, and tradeoffs."),
        (3, "Framework", "Django", 1, 3, "A batteries-included web framework."),
        (3, "Framework", "FastAPI", 2, 8, "Typed APIs with automatic schema generation."),
        (4, "Tool", "Development workflow", CENTER_DEPTH, 0, "Keep the tools that make Python projects repeatable."),
        (4, "Tool", "Virtual environments", 0, 4, "Isolate a project's interpreter dependencies."),
        (4, "Tool", "pytest", 2, 13, "Organize executable checks and reusable fixtures."),
    ),
    layer_caption="Area",
    protocol_caption="Concept type",
)


TYPESCRIPT = _template(
    "typescript",
    "TypeScript",
    "A practical map from JavaScript foundations through type modeling and application tooling.",
    ("JavaScript base", "Type system", "Modules and runtime", "Application patterns", "Tooling"),
    ("Language", "Type", "Runtime", "Pattern", "Tool"),
    (
        (0, "Language", "JavaScript foundations", CENTER_DEPTH, 0, "Review values, functions, objects, and asynchronous execution."),
        (0, "Language", "Functions and closures", 0, 0, "Capture examples of scope, callbacks, and higher-order functions."),
        (0, "Language", "Promises", 1, 6, "Model asynchronous work and failure."),
        (1, "Type", "Type modeling", CENTER_DEPTH, 0, "Describe valid program states before runtime."),
        (1, "Type", "Unions and narrowing", 0, 2, "Use control flow to refine possible values."),
        (1, "Type", "Generics", 1, 8, "Preserve relationships between reusable input and output types."),
        (1, "Type", "Utility types", 2, 13, "Transform existing object types."),
        (2, "Runtime", "Modules and runtime", CENTER_DEPTH, 0, "Track where types end and JavaScript execution begins."),
        (2, "Runtime", "ES modules", 0, 3, "Organize dependencies with imports and exports."),
        (2, "Runtime", "Node.js", 2, 9, "Run JavaScript outside the browser."),
        (3, "Pattern", "Application patterns", CENTER_DEPTH, 0, "Collect reusable boundaries for larger applications."),
        (3, "Pattern", "Typed API contracts", 1, 4, "Keep clients and services aligned around shared shapes."),
        (3, "Pattern", "State modeling", 2, 10, "Represent transitions and impossible states explicitly."),
        (4, "Tool", "Toolchain", CENTER_DEPTH, 0, "Connect compilation, linting, testing, and packaging."),
        (4, "Tool", "tsc", 0, 5, "Check types and emit JavaScript."),
        (4, "Tool", "ESLint", 1, 11, "Automate project-specific code rules."),
        (4, "Tool", "Vitest", 3, 15, "Run fast tests in TypeScript projects."),
    ),
    layer_caption="Area",
    protocol_caption="Concept type",
)


WEB_APPLICATION = _template(
    "web-app",
    "Web application",
    "A full application viewed from interface and browser through services and operations.",
    ("Interface", "Browser", "API", "Services", "Data", "Operations"),
    ("Component", "Concern", "Boundary", "Store", "Practice"),
    (
        (0, "Component", "User interface", CENTER_DEPTH, 0, "Map the screens and interactions people use."),
        (0, "Concern", "Accessibility", 0, 0, "Record keyboard, semantics, contrast, and assistive-technology checks."),
        (0, "Component", "Design system", 1, 6, "Collect reusable visual and interaction decisions."),
        (1, "Component", "Browser application", CENTER_DEPTH, 0, "Organize rendering, navigation, and client-side state."),
        (1, "Concern", "Routing", 0, 2, "Map URLs to views and navigation state."),
        (1, "Concern", "Client state", 2, 8, "Separate remote, local, and derived state."),
        (2, "Boundary", "Application API", CENTER_DEPTH, 0, "Define the contract between clients and server behavior."),
        (2, "Boundary", "Validation", 0, 3, "Reject malformed input at a clear boundary."),
        (2, "Boundary", "Authentication", 2, 10, "Record identity and session decisions."),
        (3, "Component", "Domain services", CENTER_DEPTH, 0, "Keep business rules explicit and testable."),
        (3, "Concern", "Business rules", 1, 4, "Capture invariants and important decisions."),
        (3, "Concern", "Background jobs", 3, 12, "Handle durable asynchronous work."),
        (4, "Store", "Application data", CENTER_DEPTH, 0, "Map durable state and its ownership."),
        (4, "Store", "Relational database", 1, 5, "Model structured data and transactions."),
        (4, "Store", "Object storage", 3, 13, "Store large immutable objects separately from records."),
        (5, "Practice", "Operations", CENTER_DEPTH, 0, "Understand how the application runs and changes safely."),
        (5, "Practice", "Deployment", 0, 7, "Document repeatable release steps."),
        (5, "Practice", "Observability", 2, 14, "Connect logs, metrics, and traces to user outcomes."),
        (5, "Practice", "Recovery", 4, 1, "Test backup, restore, and rollback procedures."),
    ),
    layer_caption="System area",
    protocol_caption="Element type",
)


SOLAR_SYSTEM = _template(
    "solar-system",
    "Solar system",
    "Regions of the Solar System with familiar objects arranged by increasing distance.",
    ("Sun", "Inner planets", "Asteroid belt", "Outer planets", "Kuiper belt"),
    ("Star", "Planet", "Dwarf planet", "Moon", "Region"),
    (
        (0, "Star", "Sun", CENTER_DEPTH, 0, "The star at the center of the Solar System."),
        (0, "Star", "Photosphere", 0, 0, "The visible surface layer of the Sun."),
        (1, "Planet", "Inner planets", CENTER_DEPTH, 0, "The four rocky planets inside the asteroid belt."),
        (1, "Planet", "Mercury", 0, 1, "The closest planet to the Sun."),
        (1, "Planet", "Venus", 0, 5, "A rocky planet with a dense atmosphere."),
        (1, "Planet", "Earth", 1, 9, "Our home planet."),
        (1, "Planet", "Mars", 1, 13, "A cold desert world with two small moons."),
        (2, "Region", "Asteroid belt", CENTER_DEPTH, 0, "A broad region between Mars and Jupiter."),
        (2, "Dwarf planet", "Ceres", 1, 4, "The largest object in the asteroid belt."),
        (3, "Planet", "Outer planets", CENTER_DEPTH, 0, "The giant planets beyond the asteroid belt."),
        (3, "Planet", "Jupiter", 0, 2, "The largest planet."),
        (3, "Planet", "Saturn", 1, 6, "A gas giant with a prominent ring system."),
        (3, "Planet", "Uranus", 2, 10, "An ice giant rotating on its side."),
        (3, "Planet", "Neptune", 3, 14, "The outermost major planet."),
        (4, "Region", "Kuiper belt", CENTER_DEPTH, 0, "A distant region of icy bodies."),
        (4, "Dwarf planet", "Pluto", 1, 7, "A dwarf planet in the Kuiper belt."),
    ),
    layer_caption="Region",
    protocol_caption="Body type",
)


PROJECT_PLANNING = _template(
    "project-planning",
    "Project planning",
    "A lightweight project map from purpose through planning, delivery, and review.",
    ("Purpose", "Plan", "Delivery", "Review"),
    ("Decision", "Outcome", "Workstream", "Risk", "Evidence"),
    (
        (0, "Outcome", "Project purpose", CENTER_DEPTH, 0, "State the change this project should create."),
        (0, "Outcome", "Success measures", 0, 0, "Define observable evidence of success."),
        (0, "Decision", "Scope", 1, 6, "Write what belongs in this project."),
        (1, "Decision", "Delivery plan", CENTER_DEPTH, 0, "Connect milestones, owners, dependencies, and risks."),
        (1, "Workstream", "Milestones", 0, 2, "Use meaningful outcomes rather than arbitrary dates."),
        (1, "Workstream", "Dependencies", 1, 8, "Record work or decisions required from elsewhere."),
        (1, "Risk", "Risks", 2, 13, "Track uncertainty, impact, and a response owner."),
        (2, "Workstream", "Active delivery", CENTER_DEPTH, 0, "Keep current work visible and connected to outcomes."),
        (2, "Workstream", "Current work", 0, 3, "Describe the smallest useful increment in progress."),
        (2, "Decision", "Decisions", 1, 9, "Record consequential choices and their reasoning."),
        (2, "Risk", "Blockers", 2, 14, "Make impediments and owners explicit."),
        (3, "Evidence", "Review and learning", CENTER_DEPTH, 0, "Compare results with the original purpose."),
        (3, "Evidence", "Outcomes", 0, 5, "Collect results and user impact."),
        (3, "Evidence", "Lessons", 1, 11, "Capture what should change next time."),
        (3, "Decision", "Next steps", 3, 1, "Choose what to continue, change, or stop."),
    ),
    layer_caption="Stage",
    protocol_caption="Item type",
)


TEMPLATES = (BLANK, PYTHON, TYPESCRIPT, WEB_APPLICATION, SOLAR_SYSTEM, PROJECT_PLANNING)


def find_template(key: str) -> AtlasTemplate:
    found = next((template for template in TEMPLATES if template.key == key), None)
    if found is None:
        raise KeyError(key)
    return found
