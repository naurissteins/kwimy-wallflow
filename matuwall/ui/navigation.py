from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk


class NavigationMixin:
    def _attach_navigation(self, grid_view: Gtk.GridView) -> None:
        grid_view.set_focusable(True)
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        grid_view.add_controller(key_controller)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._close_window()
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._activate_selected_item()
            return True

        return False

    def _close_window(self) -> None:
        window = getattr(self, "_window", None)
        if not window:
            return
        hide = getattr(self, "_hide_window", None)
        if callable(hide):
            hide()
        else:
            window.close()

    def _activate_selected_item(self) -> None:
        grid = getattr(self, "_grid_view", None)
        if not grid:
            return
        selection = grid.get_model()
        if not selection:
            return
        index = selection.get_selected()
        store = getattr(self, "_list_store", None)
        if store and index < store.get_n_items():
            item = store.get_item(index)
            if item:
                # Call _run_matugen from the app
                run_matugen = getattr(self, "_run_matugen", None)
                if callable(run_matugen):
                    from pathlib import Path
                    run_matugen(Path(item.path_str))
