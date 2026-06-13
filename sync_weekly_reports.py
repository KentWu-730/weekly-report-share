#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import subprocess
from pathlib import Path

from accio_paths import (
    CURRENT_AUTH_STATE_FILE,
    CURRENT_SHOP_CONTEXT_FILE,
    PUBLIC_SITE_URL_FILE,
    ROOT,
    WEEKLY_REPORT_DIR,
)


WEEKLY_REPORT_NAME_RE = re.compile(r"^weekly_report_\d{4}_\d{2}\.md$")
DEFAULT_ACCURATE_SOURCE_DIR = Path(
    "/Users/wukk/.accio/accounts/1749696687/agents/DID-D464A3-31D464A3U1777360-4698-D4DA77/project/reports"
)
DEFAULT_PUBLIC_OUTPUT_DIR = WEEKLY_REPORT_DIR
AUTH_REAUTHORIZE_PROMPT_FILE = ROOT / "output" / "current_auth_state.request.md"
AUTH_BRIDGE_SCRIPT = ROOT / "bootstrap_accio_auth_state.py"


def load_shop_context() -> dict[str, str]:
    if not CURRENT_SHOP_CONTEXT_FILE.exists():
        return {}
    try:
        data = json.loads(CURRENT_SHOP_CONTEXT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}


def validate_shop_context(context: dict[str, str]) -> dict[str, str]:
    required = (
        "web_shop_id",
        "web_shop_name",
        "accio_pair_shop_id",
        "accio_pair_shop_name",
        "report_source_dir",
        "report_output_dir",
    )
    if not context:
        raise SystemExit(
            "shop context required: missing current_shop_context.json or it is empty. "
            "Refresh the active shop context before running the weekly review."
        )
    missing = [key for key in required if not context.get(key, "").strip()]
    if missing:
        raise SystemExit(
            "shop context required: current_shop_context.json is missing fields: "
            + ", ".join(missing)
        )
    return context


def load_auth_state() -> dict[str, str]:
    if not CURRENT_AUTH_STATE_FILE.exists():
        return {}
    try:
        data = json.loads(CURRENT_AUTH_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "connected", "authorized", "ok"}


def ensure_authorized() -> None:
    if not CURRENT_AUTH_STATE_FILE.exists() and AUTH_BRIDGE_SCRIPT.exists():
        subprocess.run(
            ["python3", str(AUTH_BRIDGE_SCRIPT), "--output", str(CURRENT_AUTH_STATE_FILE)],
            check=False,
        )

    auth = load_auth_state()
    if not auth:
        prompt = AUTH_REAUTHORIZE_PROMPT_FILE.read_text(encoding="utf-8") if AUTH_REAUTHORIZE_PROMPT_FILE.exists() else ""
        raise SystemExit(
            f"authorization required: missing {CURRENT_AUTH_STATE_FILE}.\n"
            f"{prompt}".strip()
        )

    if not any(is_truthy(auth.get(key, "")) for key in ("authorized", "connected", "active", "ready")):
        prompt = AUTH_REAUTHORIZE_PROMPT_FILE.read_text(encoding="utf-8") if AUTH_REAUTHORIZE_PROMPT_FILE.exists() else ""
        raise SystemExit(
            f"authorization required: {CURRENT_AUTH_STATE_FILE} does not report an active connection.\n"
            f"{prompt}".strip()
        )


def resolve_source_dir() -> Path:
    context = validate_shop_context(load_shop_context())
    for key in (
        "report_source_dir",
        "REPORT_SOURCE_DIR",
        "source_dir",
        "source_report_dir",
    ):
        value = context.get(key, "").strip()
        if value:
            return Path(value)
    if DEFAULT_ACCURATE_SOURCE_DIR.exists():
        return DEFAULT_ACCURATE_SOURCE_DIR
    return DEFAULT_PUBLIC_OUTPUT_DIR


def resolve_shop_label() -> str:
    context = validate_shop_context(load_shop_context())
    for key in ("accio_pair_shop_name", "web_shop_name", "shop_name"):
        value = context.get(key, "").strip()
        if value:
            return value
    return "unknown-shop"


def get_public_site_url() -> str:
    if PUBLIC_SITE_URL_FILE.exists():
        value = PUBLIC_SITE_URL_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "https://kentwu-730.github.io/weekly-report-share/weekly_report/latest.md"


def get_current_shop_context() -> dict[str, str]:
    return validate_shop_context(load_shop_context())


def newest_md_file(directory: Path) -> Path | None:
    candidates = [
        path
        for path in directory.glob("*.md")
        if path.is_file() and WEEKLY_REPORT_NAME_RE.match(path.name)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def ensure_share_section(md_text: str) -> str:
    cleaned = re.sub(
        r"\n?---\n\n## Fixed Share Section[\s\S]*$",
        "",
        md_text.strip(),
    )
    cleaned = re.sub(
        r"\n?---\n\n## 附：分享入口[\s\S]*$",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\n?---\n\n## 页面分享[\s\S]*$",
        "",
        cleaned,
    )
    return cleaned.strip() + "\n"


def canonical_weekly_markdown_files(directory: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in directory.glob("*.md")
            if path.is_file() and WEEKLY_REPORT_NAME_RE.match(path.name)
        ],
        key=lambda path: path.stat().st_mtime,
    )


def sync_reports(input_dir: Path, output_dir: Path | None = None) -> list[Path]:
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve() if output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    for md_path in canonical_weekly_markdown_files(input_dir):
        md_text = ensure_share_section(md_path.read_text(encoding="utf-8"))
        md_path.write_text(md_text, encoding="utf-8")
        html_path = output_dir / md_path.with_suffix(".html").name
        if html_path.exists():
            html_path.unlink()
        generated.append(md_path)
    latest_md = newest_md_file(input_dir)
    if latest_md:
        latest_target = output_dir / "latest.md"
        latest_target.write_text(latest_md.read_text(encoding="utf-8"), encoding="utf-8")
        generated.append(latest_target)
    return generated


def sync_site_from_reports(input_dir: Path) -> list[Path]:
    """
    Rebuild the public site after report HTML files are regenerated.
    This keeps the desktop renderer and mobile latest-report page in sync.
    """
    generated = mirror_reports(input_dir, WEEKLY_REPORT_DIR)
    subprocess.run(["python3", str(Path(__file__).resolve().parent / "build_github_pages_site.py")], check=True)

    share_links = [
        ("desktop_upload_and_render_url", "https://kentwu-730.github.io/weekly-report-share/md-viewer.html"),
        ("mobile_latest_report_url", "https://kentwu-730.github.io/weekly-report-share/weekly_report/latest.html"),
    ]
    share_text = "\n".join(f"{key}: {value}" for key, value in share_links) + "\n"
    (WEEKLY_REPORT_DIR / "latest_share_links.txt").write_text(share_text, encoding="utf-8")
    (WEEKLY_REPORT_DIR / "latest_share_links.json").write_text(
        json.dumps({key: value for key, value in share_links}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return generated


def finalize_weekly_review(input_dir: Path) -> list[Path]:
    """
    Canonical weekly-review finalization path.

    This mirrors the runtime report directory into the repository output folder,
    rebuilds the public site, and refreshes the share-link metadata in one step.
    """
    return sync_site_from_reports(input_dir)


def mirror_reports(source_dir: Path, output_dir: Path) -> list[Path]:
    """
    Mirror the Accio runtime report directory into the repository output folder.
    """
    source_dir = source_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source_md_files = canonical_weekly_markdown_files(source_dir)
    source_md_names = {path.name for path in source_md_files}
    for stale_path in list(output_dir.glob("weekly_report_*.md")):
        if stale_path.name not in source_md_names:
            stale_path.unlink()
    for stale_path in list(output_dir.glob("weekly_report_*.html")):
        stale_path.unlink()

    generated: list[Path] = []
    for md_path in source_md_files:
        target_md = output_dir / md_path.name
        md_text = ensure_share_section(md_path.read_text(encoding="utf-8"))
        target_md.write_text(md_text, encoding="utf-8")
        target_html = output_dir / md_path.with_suffix(".html").name
        if target_html.exists():
            target_html.unlink()
        generated.append(target_md)

    latest_md = newest_md_file(output_dir)
    if latest_md:
        latest_target = output_dir / "latest.md"
        latest_target.write_text(latest_md.read_text(encoding="utf-8"), encoding="utf-8")
        generated.append(latest_target)

        share_links = {
            "source_report_dir": str(source_dir),
            "public_output_dir": str(output_dir),
            "desktop_upload_and_render_url": "https://kentwu-730.github.io/weekly-report-share/md-viewer.html",
            "mobile_latest_report_url": "https://kentwu-730.github.io/weekly-report-share/weekly_report/latest.html",
        }
        (output_dir / "latest_share_links.txt").write_text(
            "\n".join(f"{k}: {v}" for k, v in share_links.items()) + "\n",
            encoding="utf-8",
        )
        (output_dir / "latest_share_links.json").write_text(
            json.dumps(share_links, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return generated


def watch_reports(input_dir: Path, output_dir: Path | None = None, interval: float = 2.0) -> None:
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve() if output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    seen_mtimes: dict[Path, float] = {}
    print(f"watching {input_dir} -> {output_dir} every {interval:.1f}s")

    while True:
        current_files = sorted(input_dir.glob("*.md"))
        changed = False
        for md_path in current_files:
            try:
                mtime = md_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if seen_mtimes.get(md_path) != mtime:
                seen_mtimes[md_path] = mtime
                changed = True

        removed = [path for path in list(seen_mtimes) if path not in current_files]
        if removed:
            for path in removed:
                seen_mtimes.pop(path, None)
                html_path = (output_dir / path.with_suffix(".html").name)
                if html_path.exists():
                    html_path.unlink()
                    print(f"removed {html_path}")
            changed = True

        if changed:
            generated = sync_reports(input_dir, output_dir)
            for path in generated:
                print(path)

        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync weekly Markdown reports to HTML.")
    parser.add_argument(
        "--input-dir",
        default=str(resolve_source_dir()),
        help="Directory containing weekly_report_*.md files",
    )
    parser.add_argument(
        "--output-dir",
        default=str(WEEKLY_REPORT_DIR),
        help="Directory for mirrored report files and generated HTML. Defaults to repository output directory.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously watch the directory and regenerate HTML on changes.",
    )
    parser.add_argument(
        "--build-site",
        action="store_true",
        help="After syncing reports, rebuild the public site assets as well.",
    )
    parser.add_argument(
        "--finalize-weekly-review",
        action="store_true",
        help="Run the canonical weekly-review finalization path: mirror reports, rebuild the site, and refresh share links.",
    )
    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="Fail fast unless the current_auth_state.json marker says the web authorization is active.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds for watch mode.",
    )
    args = parser.parse_args()

    context = get_current_shop_context()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_PUBLIC_OUTPUT_DIR
    context_input_dir = Path(context["report_source_dir"])
    context_output_dir = Path(context["report_output_dir"])

    if input_dir.resolve() != context_input_dir.expanduser().resolve():
        raise SystemExit(
            f"shop context mismatch: --input-dir ({input_dir}) does not match "
            f"current_shop_context.json report_source_dir ({context_input_dir})."
        )
    if output_dir.resolve() != context_output_dir.expanduser().resolve():
        raise SystemExit(
            f"shop context mismatch: --output-dir ({output_dir}) does not match "
            f"current_shop_context.json report_output_dir ({context_output_dir})."
        )

    if args.require_auth:
        ensure_authorized()

    if args.watch:
        watch_reports(input_dir, output_dir, args.interval)
        return

    if args.finalize_weekly_review:
        generated = finalize_weekly_review(input_dir)
    elif args.build_site:
        generated = sync_site_from_reports(input_dir)
    else:
        if input_dir.resolve() != output_dir.resolve():
            generated = mirror_reports(input_dir, output_dir)
        else:
            generated = sync_reports(input_dir, output_dir)
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
