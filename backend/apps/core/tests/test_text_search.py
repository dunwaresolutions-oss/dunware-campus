from __future__ import annotations

import pytest

from apps.core.text_search import multi_word_icontains
from apps.people.models import Student
from apps.people.tests.factories import make_student

pytestmark = pytest.mark.django_db


def test_multi_word_query_matches_across_fields():
    kid = make_student(first_name="Uriah", last_name="Oliver")
    make_student(first_name="Someone", last_name="Else")

    hits = list(kid.__class__.objects.filter(
        multi_word_icontains("Uriah Oliver", ["first_name", "last_name"])
    ))
    assert hits == [kid]


def test_single_word_query_behaves_like_the_old_or_pattern():
    kid = make_student(first_name="Uriah", last_name="Oliver")
    hits = list(kid.__class__.objects.filter(
        multi_word_icontains("uriah", ["first_name", "last_name"])
    ))
    assert hits == [kid]


def test_words_must_each_match_some_field_not_just_appear_somewhere():
    """"Uriah Oliver" must not match a student named "Uriah Adderley" and,
    separately, a student named "Marcus Oliver" - each word has to land on
    the SAME row."""
    make_student(first_name="Uriah", last_name="Adderley")
    make_student(first_name="Marcus", last_name="Oliver")

    hits = list(Student.objects.filter(
        multi_word_icontains("Uriah Oliver", ["first_name", "last_name"])
    ))
    assert hits == []


def test_empty_query_matches_everything():
    kid = make_student()
    hits = list(kid.__class__.objects.filter(multi_word_icontains("", ["first_name"])))
    assert kid in hits


def test_order_and_case_do_not_matter():
    kid = make_student(first_name="Uriah", last_name="Oliver")
    for q in ("oliver uriah", "URIAH OLIVER", "  Uriah   Oliver  "):
        hits = list(kid.__class__.objects.filter(
            multi_word_icontains(q, ["first_name", "last_name"])
        ))
        assert hits == [kid], q
