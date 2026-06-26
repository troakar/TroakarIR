The Troakar Physical Acoustic Synthesis Orchestrator lacks a formal build system, relying entirely on manual execution and ad-hoc dependency management. 

### Build & Packaging Approach
- **No Build Automation**: There are no `Makefile`, `setup.py`, `pyproject.toml`, or shell scripts for compilation, testing, or packaging. The project is designed to be run directly via the Python interpreter (`python main.py`).
- **Dependency Management**: Dependencies are listed informally in the `README.md` (`numpy`, `scipy`, `pyroomacoustics`, `taichi`, `Pillow`, `tkinterdnd2`) rather than in a lockfile or manifest like `requirements.txt`. Developers must manually install these packages.
- **Artifact Handling**: Generated audio artifacts (`.wav`, `.multisample`) and simulation logs (`.jsonl`, `.log`) are explicitly excluded from version control via `.gitignore`, indicating a "source-only" repository strategy where outputs are generated locally and not tracked.

### CI/CD & Deployment
- **No CI/CD Pipeline**: The repository contains no configuration for continuous integration or deployment (e.g., GitHub Actions, GitLab CI). 
- **Version Control**: A `GIT_COMMANDS.md` file provides basic Git cheat sheets for manual committing and pushing, reinforcing the informal, solo-developer workflow.

### Developer Conventions
- **Direct Execution**: The entry point is `main.py`, which initializes a Tkinter GUI and dynamically loads DLC modules.
- **Local State**: Debug logs (`troakar_debug.log`) and physics logs (`taichi_physics_log.jsonl`) are generated in the root directory during runtime and ignored by Git.
- **Plugin Architecture**: The "build" process for new instruments involves creating a new folder in `dlc/` with a specific structure (`engine.py`, `gui.py`, `manifest.py`), which is then discovered at runtime by `dlc_loader.py`.