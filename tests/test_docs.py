# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from itertools import permutations
from pathlib import Path

from boltons.iterutils import flatten
from extra_platforms import Group, Platform
from yaml import Loader, load

from .conftest import all_managers

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from meta_package_manager.cli import encoding_args
from meta_package_manager.inventory import MAIN_PLATFORMS
from meta_package_manager.labels import MANAGER_PREFIX, PLATFORM_PREFIX
from meta_package_manager.pool import pool

""" Test all non-code artifacts depending on manager definitions.

Covers:
    * Documentation (sphinx, readme, etc.)
    * CI/CD scripts
    * GitHub project config

These tests are mainly there to remind us keep extra stuff in sync on new
platform or manager addition.
"""

PROJECT_ROOT = Path(__file__).parent.parent


def test_platform_groups_no_overlap():
    """Check our platform groups are mutually exclusive."""
    for a, b in permutations(MAIN_PLATFORMS, 2):
        if isinstance(a, Group):
            assert a.isdisjoint(b)


@all_managers
def test_all_platforms_covered_by_groups(manager):
    """Check all platforms supported by managers are covered by a local group."""
    leftover_platforms = set(manager.platforms.copy())

    for p_obj in MAIN_PLATFORMS:
        if isinstance(p_obj, Group):
            # Check the group fully overlap the manager platforms.
            if p_obj.issubset(manager.platforms):
                # Remove the group platforms from the uncovered list.
                leftover_platforms -= set(p_obj.platforms)
        elif isinstance(p_obj, Platform):
            if p_obj in manager.platforms and p_obj in leftover_platforms:
                leftover_platforms.remove(p_obj)

    assert len(leftover_platforms) == 0
    # At this stage we know all platforms of the manager can be partitioned by a
    # combination of PLATFORM_GROUPS elements, without any overlap or leftover.


def test_project_metadata():
    # Fetch general information about the project from pyproject.toml.
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    toml_config = tomllib.loads(toml_path.read_text(**encoding_args))
    # Check all managers are referenced in Python package keywords.
    assert set(pool.all_manager_ids).issubset(toml_config["project"]["keywords"])


def test_changelog():
    content = PROJECT_ROOT.joinpath("changelog.md").read_text(**encoding_args)

    assert content.startswith("# Changelog\n")

    entry_pattern = re.compile(r"^\* \[(?P<category>[a-z,]+)\] (?P<entry>.+)")
    for line in content.splitlines():
        if line.startswith("*"):
            match = entry_pattern.match(line)
            assert match
            entry = match.groupdict()
            assert entry["category"]
            assert set(entry["category"].split(",")).issubset(
                flatten(
                    (
                        pool.all_manager_ids,
                        (p.id for p in MAIN_PLATFORMS if isinstance(p, Platform)),
                        (
                            g.platform_ids
                            for g in MAIN_PLATFORMS
                            if isinstance(g, Group)
                        ),
                        "mpm",
                        "bar-plugin",
                    ),
                ),
            )


def test_new_package_manager_issue_template():
    """Check all platforms groups are referenced in the issue template."""
    content = PROJECT_ROOT.joinpath(
        ".github/ISSUE_TEMPLATE/new-package-manager.yaml",
    ).read_text(**encoding_args)
    assert content

    template_platforms = load(content, Loader=Loader)["body"][3]["attributes"][
        "options"
    ]

    reference_labels = []
    for p_obj in MAIN_PLATFORMS:
        label = f"{p_obj.icon} {p_obj.name}"
        if isinstance(p_obj, Group) and len(p_obj) > 1:
            label += f" ({', '.join(p.name for p in p_obj.platforms)})"
        reference_labels.append({"label": label})

    assert template_platforms == reference_labels


def test_labeller_rules():
    # Extract list of extra labels.
    content = PROJECT_ROOT.joinpath(".github/labels-extra.json").read_text(
        **encoding_args,
    )
    assert content

    extra_labels = [lbl["name"] for lbl in json.loads(content)]
    assert extra_labels

    # Canonical labels are uniques.
    assert len(extra_labels) == len(set(extra_labels))
    canonical_labels = set(extra_labels)
    assert canonical_labels

    # Extract and categorize labels.
    canonical_managers = {
        lbl
        for lbl in canonical_labels
        if lbl.startswith(MANAGER_PREFIX) and "mpm" not in lbl
    }
    assert canonical_managers
    canonical_platforms = {
        lbl for lbl in canonical_labels if lbl.startswith(PLATFORM_PREFIX)
    }
    assert canonical_platforms

    # Extract rules from json blurb serialized into YAML.
    content = PROJECT_ROOT.joinpath(
        ".github/workflows/labeller-content-based.yaml",
    ).read_text(**encoding_args)
    assert "kdeldycke/workflows/.github/workflows/labeller-file-based.yaml" in content
    extra_rules = load(content, Loader=Loader)["jobs"]["labeller"]["with"][
        "extra-rules"
    ]
    rules = load(extra_rules, Loader=Loader)
    assert rules

    # Each keyword match one rule only.
    rules_keywords = Counter(flatten(rules.values()))
    assert rules_keywords
    assert max(rules_keywords.values()) == 1

    # Check that all canonical labels are referenced in rules.
    assert (canonical_labels - {"📦 manager: mpm"}).issubset(rules.keys())
