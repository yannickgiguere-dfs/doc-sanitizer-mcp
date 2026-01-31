"""CLI interface for Doc Sanitizer."""

import base64
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config_schema import PIIAction, PIIType
from .extractors import DocumentExtractor, ExtractionError
from .profiles import (
    ProfileManager,
    ProfileError,
    ProfileNotFoundError,
    ProfileValidationError,
)
from .prompts import build_sanitization_prompt, build_yaml_frontmatter

# Initialize Typer app
app = typer.Typer(
    name="doc-sanitizer",
    help="Privacy-preserving document sanitization using local LLMs",
    add_completion=False,
)

# Sub-apps
profiles_app = typer.Typer(help="Manage sanitization profiles")
server_app = typer.Typer(help="Server management commands")

app.add_typer(profiles_app, name="profiles")
app.add_typer(server_app, name="server")

# Console for rich output
console = Console()


def get_profile_manager() -> ProfileManager:
    """Get a configured ProfileManager instance."""
    storage_path = os.environ.get("PROFILE_STORAGE")
    if storage_path:
        return ProfileManager(storage_path)

    # Try common locations
    for path in [
        Path.home() / ".doc-sanitizer" / "profiles.json",
        Path("/app/data/profiles.json"),
    ]:
        if path.parent.exists():
            return ProfileManager(str(path))

    # Default to home directory
    return ProfileManager(str(Path.home() / ".doc-sanitizer" / "profiles.json"))


# ============================================================================
# Profile Commands
# ============================================================================


@profiles_app.command("list")
def profiles_list():
    """List all sanitization profiles."""
    manager = get_profile_manager()
    profiles = manager.list_profiles()

    table = Table(title="Sanitization Profiles")

    # Add columns
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("person_name", style="yellow")
    table.add_column("email", style="yellow")
    table.add_column("phone", style="yellow")
    table.add_column("company", style="yellow")
    table.add_column("address", style="yellow")
    table.add_column("financial", style="yellow")
    table.add_column("id_numbers", style="yellow")
    table.add_column("date_of_birth", style="yellow")

    for p in profiles:
        table.add_row(
            str(p.id),
            p.name,
            p.config.person_name.action.value,
            p.config.email.action.value,
            p.config.phone.action.value,
            p.config.company.action.value,
            p.config.address.action.value,
            p.config.financial.action.value,
            p.config.id_numbers.action.value,
            p.config.date_of_birth.action.value,
        )

    console.print(table)


@profiles_app.command("show")
def profiles_show(
    profile: str = typer.Argument(..., help="Profile name or ID"),
):
    """Show detailed settings for a profile."""
    manager = get_profile_manager()

    # Try to parse as int for ID lookup
    try:
        identifier = int(profile)
    except ValueError:
        identifier = profile

    try:
        detail = manager.format_profile_detail(identifier)
        console.print(detail)
    except ProfileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@profiles_app.command("create")
def profiles_create(
    name: str = typer.Argument(..., help="Name for the new profile"),
    from_profile: Optional[str] = typer.Option(
        None, "--from", "-f", help="Profile to copy settings from (default: default)"
    ),
):
    """Create a new sanitization profile."""
    manager = get_profile_manager()

    try:
        profile = manager.create_profile(name, from_profile=from_profile)
        source = from_profile or "default"
        console.print(
            f"[green]✓[/green] Created profile '{profile.name}' (ID: {profile.id}) based on '{source}'"
        )
        console.print(f"Use 'doc-sanitizer profiles edit {profile.id}' to customize settings")
    except ProfileValidationError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


@profiles_app.command("edit")
def profiles_edit(
    profile: str = typer.Argument(..., help="Profile name or ID"),
    set_options: Optional[list[str]] = typer.Option(
        None, "--set", "-s", help="Set PII type action (format: pii_type=action)"
    ),
):
    """Edit a profile's PII handling settings."""
    manager = get_profile_manager()

    # Try to parse as int for ID lookup
    try:
        identifier = int(profile)
    except ValueError:
        identifier = profile

    if not set_options:
        # Interactive mode - show current settings and available options
        try:
            p = manager.get_profile(identifier)
            console.print(f"\nProfile: {p.name} (ID: {p.id})\n")
            console.print("Current settings:")
            console.print(manager.format_profile_detail(identifier))
            console.print("\nTo edit, use: doc-sanitizer profiles edit <profile> --set <pii_type>=<action>")
            console.print("\nExample: doc-sanitizer profiles edit high_privacy --set person_name=delete")
            console.print("\nValid PII types: person_name, email, phone, company, address, financial, id_numbers, date_of_birth")
            console.print("Valid actions vary by type (delete, invent, keep_part)")
        except ProfileNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        return

    # Parse and apply changes
    changes = {}
    for opt in set_options:
        if "=" not in opt:
            console.print(f"[red]✗ Error:[/red] Invalid format '{opt}'. Use: pii_type=action")
            raise typer.Exit(1)

        pii_type_str, action_str = opt.split("=", 1)

        try:
            pii_type = PIIType(pii_type_str)
        except ValueError:
            valid_types = [t.value for t in PIIType]
            console.print(f"[red]✗ Error:[/red] Invalid PII type '{pii_type_str}'")
            console.print(f"Valid types: {', '.join(valid_types)}")
            raise typer.Exit(1)

        try:
            action = PIIAction(action_str)
        except ValueError:
            valid_actions = [a.value for a in PIIAction]
            console.print(f"[red]✗ Error:[/red] Invalid action '{action_str}'")
            console.print(f"Valid actions: {', '.join(valid_actions)}")
            raise typer.Exit(1)

        changes[pii_type_str] = action

    try:
        old_profile = manager.get_profile(identifier)
        old_config = old_profile.config

        updated = manager.update_profile(identifier, changes)

        # Show what changed
        console.print(f"[green]✓[/green] Updated profile '{updated.name}' (ID: {updated.id})")

        change_list = []
        for pii_type_str, new_action in changes.items():
            old_action = getattr(old_config, pii_type_str).action
            if old_action != new_action:
                change_list.append(f"{pii_type_str} ({old_action.value} → {new_action.value})")

        if change_list:
            console.print(f"Changed: {', '.join(change_list)}")

    except ProfileNotFoundError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)
    except ProfileValidationError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


@profiles_app.command("delete")
def profiles_delete(
    profile: str = typer.Argument(..., help="Profile name or ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a sanitization profile."""
    manager = get_profile_manager()

    # Try to parse as int for ID lookup
    try:
        identifier = int(profile)
    except ValueError:
        identifier = profile

    try:
        p = manager.get_profile(identifier)

        if not force:
            confirm = typer.confirm(
                f"Are you sure you want to delete profile '{p.name}' (ID: {p.id})?"
            )
            if not confirm:
                console.print("Cancelled.")
                raise typer.Exit(0)

        manager.delete_profile(identifier)
        console.print(f"[green]✓[/green] Deleted profile '{p.name}' (ID: {p.id})")

    except ProfileNotFoundError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)
    except ProfileValidationError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


@profiles_app.command("copy")
def profiles_copy(
    source: str = typer.Argument(..., help="Source profile name or ID"),
    new_name: str = typer.Argument(..., help="Name for the new profile"),
):
    """Create a copy of an existing profile."""
    manager = get_profile_manager()

    # Try to parse source as int for ID lookup
    try:
        source_identifier = int(source)
    except ValueError:
        source_identifier = source

    try:
        source_profile = manager.get_profile(source_identifier)
        new_profile = manager.copy_profile(source_identifier, new_name)
        console.print(
            f"[green]✓[/green] Created profile '{new_profile.name}' (ID: {new_profile.id}) "
            f"as a copy of '{source_profile.name}' (ID: {source_profile.id})"
        )
    except ProfileNotFoundError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)
    except ProfileValidationError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


# ============================================================================
# Sanitize Command
# ============================================================================


@app.command("sanitize")
def sanitize(
    file_path: Path = typer.Argument(..., help="Path to the document to sanitize"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile name or ID to use (default: default)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path (default: <filename>_sanitized.md)"
    ),
):
    """Sanitize a document using a local LLM."""
    import ollama

    manager = get_profile_manager()
    extractor = DocumentExtractor()

    # Validate input file
    if not file_path.exists():
        console.print(f"[red]✗ Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)

    # Get profile
    try:
        if profile:
            try:
                identifier = int(profile)
            except ValueError:
                identifier = profile
            selected_profile = manager.get_profile(identifier)
        else:
            selected_profile = manager.get_default_profile()
    except ProfileNotFoundError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)

    # Extract document
    console.print(f"Extracting text from {file_path.name}...")
    try:
        extracted = extractor.extract_from_file(file_path)
    except ExtractionError as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)

    # Build prompt
    console.print(f"Sanitizing with profile '{selected_profile.name}'...")
    prompt = build_sanitization_prompt(extracted.content, selected_profile)

    # Call LLM
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "phi4:14b")

    console.print(f"Using model: {ollama_model}")

    try:
        client = ollama.Client(host=ollama_host)
        with console.status("Processing with LLM...", spinner="dots"):
            response = client.generate(
                model=ollama_model,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_predict": 8192,
                },
            )
        sanitized_content = response["response"]
    except Exception as e:
        console.print(f"[red]✗ Error calling LLM:[/red] {e}")
        console.print("Make sure Ollama is running and the model is available.")
        raise typer.Exit(1)

    # Build output
    frontmatter = build_yaml_frontmatter(
        source_type=extracted.source_type,
        model_used=ollama_model,
        profile_name=selected_profile.name,
    )
    result = frontmatter + sanitized_content

    # Write output
    if output is None:
        output = file_path.parent / f"{file_path.stem}_sanitized.md"

    output.write_text(result)
    console.print(f"[green]✓[/green] Sanitized document saved to: {output}")


# ============================================================================
# Server Commands
# ============================================================================


@server_app.command("start")
def server_start():
    """Start the MCP server."""
    from .server import main as server_main
    server_main()


@server_app.command("status")
def server_status():
    """Check if the MCP server is running."""
    import httpx

    port = int(os.environ.get("PORT", 8000))
    url = f"http://localhost:{port}/health"

    try:
        response = httpx.get(url, timeout=5)
        if response.status_code == 200:
            console.print(f"[green]✓[/green] Server is running on port {port}")
        else:
            console.print(f"[yellow]![/yellow] Server responded with status {response.status_code}")
    except httpx.RequestError:
        console.print(f"[red]✗[/red] Server is not running on port {port}")
        raise typer.Exit(1)


# ============================================================================
# Main Entry Point
# ============================================================================


@app.callback()
def main():
    """Doc Sanitizer - Privacy-preserving document sanitization using local LLMs."""
    pass


def cli_main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli_main()
