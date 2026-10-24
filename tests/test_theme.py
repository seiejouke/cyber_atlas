"""Focus handling that does not require a graphical desktop."""
import tkinter as tk
import unittest

from atlas.theme import has_focus


class _FakeTk:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def call(self, command):
        if self.error is not None:
            raise self.error
        return self.result


class _FakeWidget:
    def __init__(self, path, interpreter):
        self.path, self.tk = path, interpreter

    def __str__(self):
        return self.path


class ThemeTests(unittest.TestCase):
    def test_raw_focus_path_tolerates_combobox_popdown_and_destroyed_window(self):
        slider = _FakeWidget(".!slider", _FakeTk(".!slider"))
        popdown = _FakeWidget(".!slider", _FakeTk(".!combobox.popdown.f.l"))
        destroyed = _FakeWidget(".!slider", _FakeTk(error=tk.TclError("window was deleted")))
        self.assertTrue(has_focus(slider))
        self.assertFalse(has_focus(popdown))
        self.assertFalse(has_focus(destroyed))


if __name__ == "__main__":
    unittest.main()
