from pathlib import Path
from typing import Any, TypedDict

import json
import subprocess
import sys
import yaml


class RecipeFailure(TypedDict):
    failed_at: str


def load_failed_compatibility(file_path: Path) -> dict[str, RecipeFailure]:
    if file_path.exists():
        with file_path.open("r") as file:
            content = file.read().strip()

        if not content:
            return {}

        parsed_data: Any
        try:
            parsed_data = json.loads(content)
        except json.JSONDecodeError:
            # Some historical files were YAML-formatted despite the .json suffix.
            # Fall back to YAML parsing and normalize output to JSON on save.
            parsed_data = yaml.safe_load(content)

        if not isinstance(parsed_data, dict):
            eprint(
                f"Invalid failed compatibility format in {file_path}: expected mapping, got {type(parsed_data).__name__}"
            )
            return {}

        normalized: dict[str, RecipeFailure] = {}
        for recipe_name, failure_data in parsed_data.items():
            if not isinstance(recipe_name, str):
                continue
            if not isinstance(failure_data, dict):
                continue
            failed_at = failure_data.get("failed_at")
            if isinstance(failed_at, str):
                normalized[recipe_name] = {"failed_at": failed_at}

        return normalized
    return {}


def save_failed_compatibility(file_path: Path, data: dict[str, RecipeFailure]) -> None:
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w") as file:
        json.dump(data, file, indent=4)


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def commit_push_changes(message: str, branch_name: str) -> None:
    """
    Commit and push changes to the specified branch with a given commit message.
    If there are no changes, do nothing.
    """

    # Switch to branch
    run_command(["git", "switch", branch_name])

    # Check if there are changes to commit
    result = run_command_unchecked(["git", "diff-index", "--quiet", "HEAD"])
    if result.returncode == 0:
        eprint("No changes to commit.")
        return

    # Commit, pull and push the changes
    run_command(["git", "pull", "origin", branch_name])
    run_command(["git", "commit", "--message", message, "--no-verify"])
    run_command(["git", "push", "--set-upstream", "origin", branch_name])


def recipe_name_collisions(
    recipe_file: Path, *, channels: list[str] = ["conda-forge", "max"]
) -> bool:
    with open(recipe_file, "r") as fh:
        recipe_data = yaml.safe_load(fh)
        name = recipe_data.get("package", {}).get("name", None)

    if name is None or len(name.strip()) == 0:
        eprint("Invalid recipe yaml")
        # No collisions possible
        return False

    cmd = ["conda", "search", "--quiet", "--skip-flexible-search"]
    for channel in channels:
        cmd.extend(["--channel", channel])
    cmd.append(name.strip())

    p = run_command_unchecked(cmd)
    if p.returncode == 0:
        # Name collides with something
        eprint("Name collision detected:")
        eprint(f"{p.stdout}")
        eprint(f"{p.stderr}")
        return True
    return False


def run_command_unchecked(command: list[str]) -> subprocess.CompletedProcess[Any]:
    eprint(f"Run command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    return result


def run_command(command: list[str]) -> subprocess.CompletedProcess[Any]:
    result = run_command_unchecked(command)
    if result.returncode != 0:
        eprint("Command failed")
        print(f"stdout: {result.stdout}")
        eprint(f"stderr: {result.stderr}")
        sys.exit(result.returncode)

    return result
