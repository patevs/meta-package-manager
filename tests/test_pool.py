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

import inspect
from importlib import import_module
from pathlib import Path

import pytest

import meta_package_manager
from meta_package_manager.base import PackageManager
from meta_package_manager.cli import mpm
from meta_package_manager.pool import manager_classes, pool

from .conftest import (
    default_manager_ids,
    maintained_manager_ids,
    unsupported_manager_ids,
)

""" Test the pool and its content. """


def test_manager_definition_inventory():
    """Check all classes implementing a package manager are accounted for in the
    pool."""
    found_classes = set()

    # Search for manager definitions in the managers subfolder.
    for py_file in Path(inspect.getfile(meta_package_manager)).parent.glob(
        "managers/*.py"
    ):
        module = import_module(
            f"meta_package_manager.managers.{py_file.stem}", package=__package__
        )
        for _, klass in inspect.getmembers(module, inspect.isclass):
            if issubclass(klass, PackageManager) and not klass.virtual:
                found_classes.add(klass)

    assert sorted(map(str, found_classes)) == sorted(map(str, manager_classes))


def test_manager_classes_order():
    """Check manager classes are ordered by their IDs."""
    assert [c.__name__ for c in manager_classes] == sorted(
        (c.__name__ for c in manager_classes), key=str.casefold
    )


def test_manager_count():
    """Check all implemented package managers are accounted for, and unique."""
    assert len(manager_classes) == 35
    assert len(pool) == 35
    assert len(pool) == len(pool.all_manager_ids)
    assert pool.all_manager_ids == tuple(sorted(set(pool)))


def test_cached_pool():
    assert pool == pool
    assert pool is pool


@maintained_manager_ids
def test_maintained_managers(manager_id):
    assert pool[manager_id].deprecated is False


@default_manager_ids
def test_supported_managers(manager_id):
    assert pool[manager_id].supported is True


@unsupported_manager_ids
def test_unsupported_managers(manager_id):
    assert pool[manager_id].supported is False


def test_manager_groups():
    """Test relationships between manager groups."""
    assert set(pool.maintained_manager_ids).issubset(pool.all_manager_ids)
    assert set(pool.default_manager_ids).issubset(pool.all_manager_ids)
    assert set(pool.unsupported_manager_ids).issubset(pool.all_manager_ids)

    assert set(pool.default_manager_ids).issubset(pool.maintained_manager_ids)
    assert set(pool.unsupported_manager_ids).issubset(pool.maintained_manager_ids)

    assert len(pool.default_manager_ids) + len(pool.unsupported_manager_ids) == len(
        pool.maintained_manager_ids,
    )
    assert (
        tuple(sorted(set(pool.default_manager_ids).union(pool.unsupported_manager_ids)))
        == pool.maintained_manager_ids
    )


def test_extra_option_allowlist():
    assert pool.ALLOWED_EXTRA_OPTION.issubset(opt.name for opt in mpm.params)


selection_cases = {
    "single_selector": (
        {"keep": ("uv",)},
        ("uv",),
    ),
    "list_input": (
        {"keep": ["uv"]},
        ("uv",),
    ),
    "set_input": (
        {"keep": {"uv"}},
        ("uv",),
    ),
    "empty_selector": (
        {"keep": ()},
        (),
    ),
    "duplicate_selectors": (
        {"keep": ("uv", "uv")},
        ("uv",),
    ),
    "multiple_selectors": (
        {"keep": ("uv", "gem")},
        ("uv", "gem"),
    ),
    "ordered_selectors": (
        {"keep": ("gem", "uv")},
        ("gem", "uv"),
    ),
    "single_exclusion": (
        {"drop": {"uv"}},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "uv"
        ),
    ),
    "duplicate_exclusions": (
        {"drop": ("uv", "uv")},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "uv"
        ),
    ),
    "multiple_exclusions": (
        {"drop": ("uv", "gem")},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid not in ("uv", "gem")
        ),
    ),
    "selector_priority": (
        {"keep": {"uv"}, "drop": {"gem"}},
        ("uv",),
    ),
    "exclusion_override": (
        {"keep": {"uv"}, "drop": {"uv"}},
        (),
    ),
    "default_selection": (
        {},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "explicit_default_selection": (
        {"keep": None, "drop": None},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_deprecated": (
        {"keep_deprecated": True},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_deprecated": (
        {"keep_deprecated": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_unsupported": (
        {"keep_unsupported": True},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_unsupported": (
        {"keep_unsupported": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "drop_inactive": (
        {"drop_inactive": True},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_inactive": (
        {"drop_inactive": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported
        ),
    ),
}


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        pytest.param(kwargs, expected, id=test_id)
        for test_id, (kwargs, expected) in selection_cases.items()
    ),
)
def test_select_managers(kwargs, expected):
    """We use tuple everywhere so we can check that select_managers() conserve the
    original order."""
    selection = pool._select_managers(**kwargs)
    assert tuple(m.id for m in selection) == expected
