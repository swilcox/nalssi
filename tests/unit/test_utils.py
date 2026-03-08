"""
Unit tests for utility functions.
"""

import pytest

from app.core.utils import slugify


@pytest.mark.unit
class TestSlugify:
    """Tests for the slugify function."""

    def test_basic_slugify(self):
        assert slugify("Hello World") == "hello_world"

    def test_slugify_with_commas(self):
        assert slugify("San Francisco, CA") == "san_francisco_ca"

    def test_slugify_preserves_numbers(self):
        assert slugify("Location 123") == "location_123"

    def test_slugify_strips_leading_trailing(self):
        assert slugify("  Hello   World  ") == "hello_world"

    def test_slugify_collapses_underscores(self):
        assert slugify("a---b___c") == "a_b_c"

    def test_slugify_special_characters(self):
        assert slugify("hello@world#test!") == "hello_world_test"

    def test_slugify_unicode(self):
        assert slugify("café résumé") == "cafe_resume"

    def test_slugify_single_word(self):
        assert slugify("spring") == "spring"

    def test_slugify_spring_hill(self):
        """Key test case for kurokku integration."""
        assert slugify("Spring Hill") == "spring_hill"

    def test_slugify_empty_after_processing(self):
        assert slugify("!!!") == ""

    def test_slugify_already_slug(self):
        assert slugify("already_a_slug") == "already_a_slug"

    def test_slugify_mixed_case(self):
        assert slugify("CamelCase") == "camelcase"

    def test_slugify_dots_and_slashes(self):
        assert slugify("path/to.file") == "path_to_file"
