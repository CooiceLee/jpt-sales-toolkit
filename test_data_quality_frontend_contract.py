#!/usr/bin/env python3
"""Static contract for imported data-quality prompts in lead cards and panels."""

from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def main() -> None:
    quality = (MODULES / "data-quality-view.js").read_text(encoding="utf-8")
    panel = (MODULES / "inquiry-panel.js").read_text(encoding="utf-8")
    form = (MODULES / "inquiry-form.js").read_text(encoding="utf-8")
    card = (MODULES / "card-template.js").read_text(encoding="utf-8")
    navigation = (MODULES / "lead-navigation.js").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    policy = (ROOT / "backend" / "services" / "permission_policy.py").read_text(encoding="utf-8")

    assert "Data Quality" in panel and "qualityVisible" in panel
    assert "DataQualityModule.render" in form
    assert "quality_issue_count" in card and "quality_issue_count" in navigation
    assert "canReviewQuality" in navigation and "assignment_type === 'collaborator'" in navigation
    assert "listDataQualityIssues" in quality and "updateDataQualityIssue" in quality
    assert "resolved" in quality and "ignored" in quality and "open" in quality
    assert '"quality_issue_count"' in policy
    assert 'type="button"' in quality
    assert index.index("data-quality-view.js") < index.index("inquiry-form.js")
    assert len(quality.splitlines()) <= 125
    print("PASS: lead data-quality badge, review states, and module loading contract")


if __name__ == "__main__":
    main()
