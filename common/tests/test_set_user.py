"""Smoke tests for the set_user / set_tenant / add_attributes_to_current_span
helpers in `common`. We don't depend on a real OTel pipeline here — a plain
mock with a `set_attribute` method is sufficient to verify the contract:

  - the right keys land on the active span
  - None / missing fields are skipped
  - calling outside a request context (no active span) is a silent no-op
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import (  # noqa: E402
    add_attributes_to_current_span,
    set_user,
    set_tenant,
    set_session,
    apply_session_from_baggage,
    _current_span_var,
)


class SetUserTenantTests(unittest.TestCase):
    def setUp(self):
        self.span = MagicMock()
        self.token = _current_span_var.set(self.span)

    def tearDown(self):
        _current_span_var.reset(self.token)

    def _attrs(self):
        return dict(call.args for call in self.span.set_attribute.call_args_list)

    def test_set_user_full(self):
        set_user({"id": "u1", "email": "a@b.com", "name": "Alice"})
        self.assertEqual(
            self._attrs(),
            {"user.id": "u1", "user.email": "a@b.com", "user.full_name": "Alice"},
        )

    def test_set_user_partial_skips_missing_fields(self):
        set_user({"id": "u1"})
        self.assertEqual(self._attrs(), {"user.id": "u1"})

    def test_set_tenant_full(self):
        set_tenant({"id": "t1", "name": "Acme"})
        self.assertEqual(self._attrs(), {"tenant.id": "t1", "tenant.name": "Acme"})

    def test_add_attributes_skips_none(self):
        add_attributes_to_current_span({"a": "x", "b": None, "c": 0})
        self.assertEqual(self._attrs(), {"a": "x", "c": 0})

    def test_set_session(self):
        set_session("sess-1")
        self.assertEqual(self._attrs(), {"session.id": "sess-1"})


class ApplySessionFromBaggageTests(unittest.TestCase):
    """`apply_session_from_baggage` reads from OTel baggage on the active
    context; here we stub the lookup so we don't need a real OTel pipeline."""

    def test_tags_span_when_baggage_present(self):
        span = MagicMock()
        import common as common_mod
        original = common_mod.get_baggage
        common_mod.get_baggage = lambda key: "sess-from-bag" if key == "session.id" else None
        try:
            apply_session_from_baggage(span)
        finally:
            common_mod.get_baggage = original
        span.set_attribute.assert_called_once_with("session.id", "sess-from-bag")

    def test_noop_when_baggage_absent(self):
        span = MagicMock()
        import common as common_mod
        original = common_mod.get_baggage
        common_mod.get_baggage = lambda key: None
        try:
            apply_session_from_baggage(span)
        finally:
            common_mod.get_baggage = original
        span.set_attribute.assert_not_called()


class NoActiveSpanTests(unittest.TestCase):
    """When called outside a Monoscope-handled request, helpers should no-op."""

    def test_no_op_when_no_active_span(self):
        # _current_span_var defaults to None outside any set scope
        set_user({"id": "u1", "email": "a@b.com"})
        set_tenant({"id": "t1"})
        set_session("sess-1")
        # Nothing to assert beyond "no exception raised".


if __name__ == "__main__":
    unittest.main()
