# env_utils.py
# this utility will check a students setup to verify it has
# packages loaded, python installed and api keys available
# it references the pyproject.toml file and .env.example for requirements
# students never run this file directly; each project's check_setup.py runs it,
# so any command printed for them should say check_setup.py

# The repo holds one project per agent harness, each with its own
# pyproject.toml and its own .venv. That separation is deliberate - see
# README.md - so this checker reports per project rather than assuming one
# environment at the repo root. .env is shared and lives at the root.
PROJECT_DIRS = ("langgraph-agent", "claude-sdk-agent")

# ========== STANDARD LIBRARY IMPORTS ONLY (no external dependencies) ==========
import os
import sys
import shutil
import re
from pathlib import Path


# ========== EARLY PYTHON ENVIRONMENT DIAGNOSTICS ==========
def check_python_executable_and_version():
    """
    Check Python executable location and version BEFORE attempting any external imports.
    This ensures students get helpful diagnostics even if imports fail.

    Returns: tuple (success: bool, python_version_tuple, issues: list)
    """
    issues = []
    executable = Path(sys.executable).resolve()
    py_version = sys.version_info
    py_version_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"

    print("=" * 70)
    print("PYTHON ENVIRONMENT DIAGNOSTICS")
    print("=" * 70)
    print(f"Python executable: {executable}")
    print(f"Python version: {py_version_str}")
    print(f"Platform: {sys.platform}")
    print()

    # Check if running in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )

    # Each project has its own .venv, so any of them is a valid place to be
    # running from - as is a .venv at the cwd, for anyone running inside one
    # project directory.
    root = Path(__file__).resolve().parent
    candidate_venvs = [root / name / ".venv" for name in PROJECT_DIRS]
    candidate_venvs.append(Path.cwd() / ".venv")

    def _venv_python(venv: Path) -> Path:
        if sys.platform == "win32":
            return venv / "Scripts" / "python.exe"
        return venv / "bin" / "python"

    executable_in_venv = False
    expected_venv = candidate_venvs[0]
    for venv in candidate_venvs:
        try:
            if executable.resolve() == _venv_python(venv).resolve():
                executable_in_venv, expected_venv = True, venv
                break
        except (OSError, RuntimeError):
            if str(executable).startswith(str(venv)):
                executable_in_venv, expected_venv = True, venv
                break

    expected_python = _venv_python(expected_venv)

    if not in_venv:
        issues.append("⚠️  Not running in a virtual environment")
        issues.append("   This may cause import errors if required packages are not installed")
    elif not executable_in_venv:
        issues.append(f"⚠️  Python executable is not in any project's .venv")
        issues.append(f"   Expected one of: {', '.join(str(_venv_python(v)) for v in candidate_venvs)}")
        issues.append(f"   Actual:   {executable}")
        issues.append("   You may be using a different virtual environment or system Python")
    else:
        print(f"✅ Running in virtual environment: {expected_venv}")

    # Check Python version against basic requirements (pyproject.toml requires-python = ">=3.11")
    if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 11):
        issues.append(f"⚠️  Python {py_version_str} is below minimum required version 3.11")
    else:
        print(f"✅ Python version {py_version_str} is in expected range (>=3.11)")

    # Check sys.prefix and base_prefix
    print(f"\nEnvironment paths:")
    print(f"  sys.prefix:      {sys.prefix}")
    print(f"  sys.base_prefix: {sys.base_prefix}")
    if in_venv:
        print(f"  Virtual env:     {sys.prefix}")

    if issues:
        print("\n" + "!" * 70)
        print("POTENTIAL ISSUES DETECTED:")
        print("!" * 70)
        for issue in issues:
            print(issue)
        print("\nRECOMMENDATION:")
        print("  Run this script using: uv run python check_setup.py")
        print("  Or activate the virtual environment first:")
        if sys.platform == "win32":
            print("    .venv\\Scripts\\activate")
        else:
            print("    source .venv/bin/activate")
        print("!" * 70)

    print()
    return (len(issues) == 0, py_version, issues)


# ========== EXTERNAL DEPENDENCY IMPORTS (with error handling) ==========
try:
    from dotenv import dotenv_values, load_dotenv
    import tomllib
    from importlib import metadata
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
    EXTERNAL_IMPORTS_AVAILABLE = True
except ImportError as e:
    EXTERNAL_IMPORTS_AVAILABLE = False
    IMPORT_ERROR = e
    print("=" * 70)
    print("IMPORT ERROR DETECTED")
    print("=" * 70)
    print(f"Failed to import required package: {e}")
    print()
    print("This usually means you're running Python outside the virtual environment")
    print("or the required packages are not installed.")
    print()
    print("SOLUTIONS:")
    print("  1. Run using uv (recommended):")
    print("       uv run python check_setup.py")
    print()
    print("  2. Activate the virtual environment first:")
    if sys.platform == "win32":
        print("       .venv\\Scripts\\activate")
    else:
        print("       source .venv/bin/activate")
    print("     Then run:")
    print("       python check_setup.py")
    print()
    print("  3. Install dependencies:")
    print("       uv sync")
    print("=" * 70)
    print()


def summarize_value(key: str, value: str, example_value: str = None) -> str:
    """Return masked form for API keys, or full value for non-API keys.

    Args:
        key: The environment variable name
        value: The current value
        example_value: The example/placeholder value from .env.example (optional)

    Returns:
        - For *API_KEY variables: masked form (****last4) unless it matches the example value
        - For *API_KEY variables matching example: full value (to show it needs changing)
        - For non-API_KEY variables: full value (not obscured)
        - For boolean strings: lowercase boolean
    """
    lower = value.lower()
    if lower in ("true", "false"):
        return lower

    # Check if this is an API_KEY variable
    is_api_key = key.endswith("API_KEY")

    if not is_api_key:
        # Non-API_KEY variables are never obscured
        return value

    # For API_KEY variables, show full value if it matches the example (needs changing)
    if example_value and value == example_value:
        return value

    # Otherwise, obscure the API key
    return "****" + value[-4:] if len(value) > 4 else "****" + value


def _parse_required_keys(example_file_path: str) -> dict:
    """Read required values, excluding defaults and inactive authentication paths."""
    required_keys = {}
    with open(example_file_path, 'r') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '=' in stripped:
                key = stripped.split('=')[0].strip()
                value = stripped.split('=', 1)[1].strip()
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                elif value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                required_keys[key] = value
    for key in ("OPENAI_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT", "DATASET_NAME"):
        required_keys.pop(key, None)
    if os.getenv("LANGSMITH_TRACING", "").lower() in {"true", "1", "yes"}:
        required_keys.setdefault("LANGSMITH_API_KEY", "")
    else:
        required_keys.pop("LANGSMITH_API_KEY", None)
    for key in _model_required_keys():
        required_keys.setdefault(key, "")
    return required_keys


def check_env_file_exists(env_file_path: str = ".env", example_file_path: str = ".env.example"):
    """Check if .env file exists. If not, check if required variables are in system env.

    Args:
        env_file_path: Path to the .env file
        example_file_path: Path to the .env.example file
    Returns:
        True if .env exists, False otherwise
    """
    if os.path.exists(env_file_path):
        return True

    # .env doesn't exist — check if required vars are set in system environment
    if not os.path.exists(example_file_path):
        print("⚠️  No .env file found and no .env.example to check against")
        print(f"   Run: cp .env.example .env")
        print()
        return False

    required_keys = _parse_required_keys(example_file_path)
    found = {}
    missing = []

    for key, example_val in required_keys.items():
        sys_val = os.environ.get(key)
        if sys_val is not None:
            # Check if it's still a placeholder value
            if _is_unfilled(sys_val):
                missing.append(key)
            else:
                found[key] = sys_val
        else:
            missing.append(key)

    print("=" * 70)
    print("⚠️  NO .env FILE FOUND")
    print("=" * 70)

    if missing and not found:
        # Nothing set anywhere
        print("No .env file found and required variables are not set in system environment.")
        print()
        print("Required variables not set:")
        for key in missing:
            print(f"  - {key}")
        print()
        print("SOLUTION: Create a .env file from the example:")
        print("  cp .env.example .env")
        print("  Then edit .env with your API keys.")
    elif missing:
        # Some set in system env, some missing
        print("No .env file found. Some required variables found in system environment,")
        print("but others are missing.")
        print()
        print("Using system environment values for:")
        for key in found:
            print(f"  ✅ {key}")
        print()
        print("Missing:")
        for key in missing:
            print(f"  ⚠️  {key}")
        print()
        print("SOLUTION: Create a .env file from the example:")
        print("  cp .env.example .env")
        print("  Then edit .env with your API keys.")
    else:
        # All required vars found in system env
        print("No .env file found, but all required variables are set in system environment.")
        print()
        print("Using system environment values for:")
        for key in found:
            print(f"  ✅ {key}")
        print()
        print("NOTE: You can still create a .env file if preferred:")
        print("  cp .env.example .env")

    print("=" * 70)
    print()
    return False


def check_env_conflicts(env_file_path: str):
    """Report variables set in both the system environment and the .env file.

    This project loads with ``load_dotenv(override=True)``, so the .env value
    wins wherever the two disagree. That is the intended behavior, but it is
    worth surfacing: a stale API key exported in a shell profile is a common
    reason someone's traces land somewhere unexpected.

    Args:
        env_file_path: Path to the .env file
    """
    if not os.path.exists(env_file_path):
        return

    # Parse the .env file to get what values SHOULD be loaded
    from dotenv import dotenv_values
    env_file_vars = dotenv_values(env_file_path)

    conflicts = []
    for key, file_value in env_file_vars.items():
        # Check if this key already exists in the environment
        sys_value = os.environ.get(key)
        if sys_value is not None and sys_value != file_value:
            # There's a conflict - system env var exists and differs from .env file
            conflicts.append({
                'key': key,
                'system_value': sys_value,
                'file_value': file_value
            })

    if conflicts:
        print("=" * 70)
        print("ℹ️  SYSTEM ENVIRONMENT DIFFERS FROM .env")
        print("=" * 70)
        print("The following variables are set in your system environment and")
        print("differ from your .env file. This project loads with")
        print("load_dotenv(override=True), so the .env value below is the one")
        print("that will be used. No action needed unless a value looks wrong.")
        print()
        for conflict in conflicts:
            key = conflict['key']
            print(f"Variable: {key}")
            if key.endswith('API_KEY'):
                # Obscure API keys in the output
                sys_val = "****" + conflict['system_value'][-4:] if len(conflict['system_value']) > 4 else "****"
                file_val = "****" + conflict['file_value'][-4:] if len(conflict['file_value']) > 4 else "****"
                print(f"  System value:      {sys_val}")
                print(f"  .env value (used): {file_val}")
            else:
                print(f"  System value:      {conflict['system_value']}")
                print(f"  .env value (used): {conflict['file_value']}")
            print()

        print("If the .env value is the one you want, you're done. Otherwise:")
        print("  1. Correct the value in your .env file, or")
        print("  2. Unset the system environment variable:")
        if sys.platform == "win32":
            print("     CMD:")
            for conflict in conflicts:
                print(f"       set {conflict['key']}=")
            print("     PowerShell:")
            for conflict in conflicts:
                print(f"       Remove-Item Env:\\{conflict['key']}")
        else:
            for conflict in conflicts:
                print(f"       unset {conflict['key']}")
        print("=" * 70)
        print()


def check_manual_installs(file_path: str):
    """Check if manually installed applications are available in PATH.

    Looks for a comment line like: # Manual installs for checking: app1, app2, app3

    Args:
        file_path: Path to the .env.example file to check
    """
    if not os.path.exists(file_path):
        return

    manual_installs = []
    with open(file_path, 'r') as f:
        for line in f:
            stripped = line.strip()
            # Look for the manual installs comment
            if stripped.startswith('# Manual installs for checking:'):
                # Extract the comma-delimited list after the colon
                apps_str = stripped.split(':', 1)[1].strip()
                if apps_str:
                    manual_installs = [app.strip() for app in apps_str.split(',')]
                break

    if not manual_installs:
        return

    # Check each application
    issues = []
    found = []

    for app in manual_installs:
        if shutil.which(app) is not None:
            found.append(f"✅ {app}")
        else:
            issues.append(f"⚠️  {app} not found in PATH")

    # Print results
    print("Manual Installs Check:")
    for item in found:
        print(item)
    for issue in issues:
        print(issue)
    print()


def _gateway_enabled() -> bool:
    """Match the LangChain integrations' gateway flag semantics."""
    value = os.getenv("LANGSMITH_GATEWAY", "")
    return bool(value) and value.lower() not in {"false", "0", "no"}


def _is_unfilled(value: str | None) -> bool:
    """Recognize missing, empty, and example credentials without validating secrets."""
    value = (value or "").strip().lower()
    return not value or value == "****" or any(
        marker in value for marker in ("your_", "your-", "_here", "...", "<", ">")
    )


def _model_required_keys() -> set[str]:
    """Select credentials for the active local chat setup."""
    project = _active_project(_projects())
    if project is not None and project.name == "claude-sdk-agent":
        return {"ANTHROPIC_API_KEY"} if "ANTHROPIC_API_KEY" in os.environ else set()
    if project is None:
        return set()
    if not _gateway_enabled():
        return {"OPENAI_API_KEY"}
    override = os.getenv("LANGSMITH_GATEWAY_API_KEY")
    return {"LANGSMITH_GATEWAY_API_KEY" if override else "LANGSMITH_API_KEY"}


def _check_model_environment() -> list[str]:
    """Report routing configuration separately from credential presence."""
    issues = []
    project = _active_project(_projects())
    if project is not None and project.name == "claude-sdk-agent":
        return issues
    if _gateway_enabled():
        gateway = os.environ["LANGSMITH_GATEWAY"]
        if gateway.lower() not in {"true", "1", "yes"}:
            from urllib.parse import urlsplit

            try:
                parsed = urlsplit(gateway)
                valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            except ValueError:
                valid = False
            if not valid:
                issues.append("LANGSMITH_GATEWAY must be true or a gateway base URL (or false, 0, no to disable)")
        for key in ("OPENAI_API_BASE", "OPENAI_BASE_URL", "ANTHROPIC_API_URL", "ANTHROPIC_BASE_URL"):
            if os.getenv(key):
                issues.append(f"{key} overrides automatic gateway routing; unset it to use LANGSMITH_GATEWAY")
        print("LangChain chat mode: LangSmith LLM Gateway (no local provider key needed for supported chat models)")
    else:
        print("LangChain chat mode: direct provider (default)")
    return issues


def doublecheck_env(file_path: str):
    """Check the loaded environment using mode-aware credential requirements."""
    if not os.path.exists(file_path):
        print(f"Did not find file {file_path}.")
        return
    example_values = dict(dotenv_values(file_path))
    required = set(_parse_required_keys(file_path))
    if os.getenv("LANGSMITH_TRACING", "").lower() in {"true", "1", "yes"}:
        required.add("LANGSMITH_API_KEY")
        print("Tracing requires LANGSMITH_API_KEY separately from any gateway override.")
    keys = set(example_values) | required | {"LANGSMITH_GATEWAY", "LANGSMITH_GATEWAY_API_KEY"}
    issues = _check_model_environment()
    print("Environment variables (presence check only; credentials are not authenticated):")
    for key in sorted(keys):
        current = os.getenv(key)
        summary = summarize_value(key, current, example_values.get(key)) if current is not None else "<not set>"
        print(f"{key}={summary}")
        if key in required and _is_unfilled(current):
            issues.append(f"{key} is required but missing, empty, or a placeholder")
    project = _active_project(_projects())
    if project is None or project.name == "claude-sdk-agent":
        print("Claude Agent SDK: CLI login is not checked here; authenticate with a claude CLI login or ANTHROPIC_API_KEY; LANGSMITH_GATEWAY does not configure this harness.")
    print("Server-side evaluations: configure the OpenAI provider secret in LangSmith separately; local gateway credentials do not replace it.")
    print("LangSmith datasets and evaluations also require LANGSMITH_API_KEY, even with tracing disabled.")
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\nRequired environment values for checked paths are set (authentication is not verified).")
    print()


def check_venv(expected_venv_path: str = ".venv"):
    """Check if virtual environment is properly activated.

    Args:
        expected_venv_path: Expected path to the virtual environment (default: ".venv")
    """
    issues = []

    # Check sys.prefix - this is set to the venv path when activated
    current_prefix = Path(sys.prefix).resolve()
    expected_path_obj = Path(expected_venv_path).resolve()

    # Check if running in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

    if not in_venv:
        issues.append("⚠️  Virtual environment is not activated")
        issues.append("   Run: source .venv/bin/activate  (or .venv\\Scripts\\activate on Windows)")
    else:
        # Virtual env is activated, check it is one of the projects' venvs
        root = Path(__file__).resolve().parent
        known = [(root / name / ".venv").resolve() for name in PROJECT_DIRS]
        known.append(expected_path_obj)
        if current_prefix not in known:
            issues.append(f"⚠️  Activated venv ({current_prefix}) is not one of this repo's project venvs")
            issues.append(f"   Expected one of: {', '.join(str(k) for k in known)}")

    # Check if uv is available
    uv_available = shutil.which("uv") is not None

    if not uv_available:
        issues.append("ℹ️  'uv' command not found - this project recommends using uv for package management")
        issues.append("   Install uv: https://docs.astral.sh/uv/")

    # Print results
    if issues:
        print("Virtual Environment Check:")
        for issue in issues:
            print(issue)
        print()
    else:
        print("✅ Virtual environment is properly activated")
        if uv_available:
            print("✅ uv is available")
        print()


# ========== utility to check packages and python based on pyproject.toml  =====================================

def _repo_root() -> Path:
    """Directory holding this file: the repo root, where .env lives."""
    return Path(__file__).resolve().parent


def _projects() -> list[Path]:
    """Project directories that actually exist and carry a pyproject.toml."""
    root = _repo_root()
    return [root / name for name in PROJECT_DIRS if (root / name / "pyproject.toml").is_file()]


def _active_project(projects: list[Path]) -> Path | None:
    """The project whose .venv the running interpreter belongs to, if any."""
    prefix = Path(sys.prefix).resolve()
    for project in projects:
        try:
            if (project / ".venv").resolve() == prefix:
                return project
        except (OSError, RuntimeError):
            continue
    return None


def _fmt_row(cols, widths):
    return " | ".join(str(c).ljust(w) for c, w in zip(cols, widths))

def doublecheck_pkgs(pyproject_path="pyproject.toml", verbose=False):
    p = Path(pyproject_path)
    if not p.exists():
        print(f"ERROR: {pyproject_path} not found.")
        return None

    # Load pyproject + python requirement
    with p.open("rb") as f:
        data = tomllib.load(f)
    project = data.get("project", {})
    python_spec_str = project.get("requires-python") or ">=3.11"

    py_ver = Version(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    py_ok = py_ver in SpecifierSet(python_spec_str)

    # Load deps (PEP 621), plus the `dev` group. uv syncs `dev` by default, so
    # anything declared there (the langgraph CLI that `uv run langgraph dev`
    # needs) is part of a student's setup and has to be checked with the rest.
    deps = list(project.get("dependencies", []))
    deps += data.get("dependency-groups", {}).get("dev", [])
    if not deps:
        if verbose or not py_ok:
            print("No [project].dependencies found in pyproject.toml.")
            print(f"Python {py_ver} {'satisfies' if py_ok else 'DOES NOT satisfy'} requires-python: {python_spec_str}")
            print(f"Executable: {sys.executable}")
        return None

    # Evaluate deps
    results = []
    problems = []
    for dep in deps:
        try:
            req = Requirement(dep)
            name = req.name
            spec = str(req.specifier) if req.specifier else "(any)"
        except Exception:
            name, spec = dep, "(unparsed)"

        rec = {"package": name, "required": spec, "installed": "-", "path": "-", "status": "❌ Missing"}

        try:
            installed_ver = metadata.version(name)
            rec["installed"] = installed_ver
            try:
                dist = metadata.distribution(name)
                rec["path"] = str(dist.locate_file(""))
            except Exception:
                rec["path"] = "(unknown)"

            # Check if package is in correct Python version's site-packages
            expected_py_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            path_str = str(rec["path"]).lower()

            # Check for version mismatch in path (if path contains a python version)
            wrong_version = False
            if "python" in path_str and rec["path"] != "(unknown)":
                # Look for patterns like python3.11, python3.13, etc. that don't match current version
                py_versions_in_path = re.findall(r'python\d+\.\d+', path_str)
                if py_versions_in_path:
                    # If we found python version(s) in path, check if any match current version
                    if expected_py_version.lower() not in py_versions_in_path:
                        wrong_version = True
                        rec["status"] = "⚠️ Wrong Python version"

            if not wrong_version:
                if spec not in ("(any)", "(unparsed)") and any(op in spec for op in "<>="):
                    sset = SpecifierSet(spec)
                    if Version(installed_ver) in sset:
                        rec["status"] = "✅ OK"
                    else:
                        rec["status"] = "⚠️ Version mismatch"
                else:
                    rec["status"] = "✅ OK"

        except metadata.PackageNotFoundError:
            # keep defaults: installed "-", status "❌ Missing"
            pass

        results.append(rec)
        if rec["status"] != "✅ OK":
            problems.append(rec)

    should_print = verbose or (not py_ok) or bool(problems)
    if should_print:
        # Python status
        print(f"Python {py_ver} {'satisfies' if py_ok else 'DOES NOT satisfy'} requires-python: {python_spec_str}")

        # Table (no hints column)
        headers = ["package", "required", "installed", "status", "path"]
        def short_path(s, maxlen=80):
            s = str(s)
            return s if len(s) <= maxlen else ("…" + s[-(maxlen-1):])
        rows = [[r["package"], r["required"], r["installed"], r["status"], short_path(r["path"])] for r in results]
        widths = [max(len(h), *(len(str(row[i])) for row in rows)) for i, h in enumerate(headers)]
        print(_fmt_row(headers, widths))
        print(_fmt_row(["-"*w for w in widths], widths))
        for row in rows:
            print(_fmt_row(row, widths))

        # Summarize issues without prescribing a tool
        if problems:
            print("\nIssues detected:")
            for r in problems:
                print(f"- {r['package']}: {r['status']} (required {r['required']}, installed {r['installed']}, path {r['path']})")

        if verbose or problems or not py_ok:
            print("\nEnvironment:")
            print(f"- Executable: {sys.executable}")

    return None


if __name__ == "__main__":
    # Run early diagnostics FIRST (uses only standard library)
    success, py_version, issues = check_python_executable_and_version()

    # If external imports failed, exit with helpful message
    if not EXTERNAL_IMPORTS_AVAILABLE:
        print("Cannot proceed with full environment check due to missing dependencies.")
        print("Please follow the solutions above to fix the import errors.")
        sys.exit(1)

    # Proceed with remaining checks (require external dependencies)
    check_venv()
    # .env and .env.example are shared by both projects and live at the repo
    # root, so anchor to this file rather than the cwd.
    root = Path(__file__).resolve().parent
    env_file = str(root / ".env")
    env_example = str(root / ".env.example")

    check_manual_installs(env_example)

    # Check if .env file exists; if not, check system env for required vars
    env_exists = check_env_file_exists(env_file, env_example)

    if env_exists:
        # Report differences BEFORE loading, while os.environ still holds only
        # the system values.
        check_env_conflicts(env_file)

        # override=True to match how the rest of the project loads .env, so the
        # values reported below are the ones the agent will actually use.
        load_dotenv(override=True)

    # Check environment variables and API keys
    doublecheck_env(env_example)

    # Package versions can only be read from the interpreter that is actually
    # running, so this reports on whichever project's venv that is. Each
    # project has its own dependency set - that is the point of the split - and
    # checking one venv against the other's pyproject.toml would report
    # confident nonsense.
    projects = _projects()
    if not projects:
        print("ERROR: no project directories found. Expected: " + ", ".join(PROJECT_DIRS))
        sys.exit(1)

    current = _active_project(projects)

    print()
    print("=" * 70
    )
    if current is None:
        # Not inside either venv: say what to run rather than report on a
        # Python that is not one of the projects.
        print("Packages: not running inside a project venv")
        print("=" * 70)
        print("Set up the agent you want to use, then check it from inside it:")
        for project in projects:
            state = "ready" if (project / ".venv").is_dir() else "not synced yet"
            print(f"  cd {project.name} && uv sync && uv run python check_setup.py     ({state})")
        print()
        print("You only need the one you plan to run.")
    else:
        print(f"Packages for {current.name}/")
        print("=" * 70)
        doublecheck_pkgs(pyproject_path=str(current / "pyproject.toml"), verbose=True)
        others = [p for p in projects if p != current]
        if others:
            print("The other project has its own venv. If you want it too:")
            for project in others:
                print(f"  cd {project.name} && uv sync && uv run python check_setup.py")
