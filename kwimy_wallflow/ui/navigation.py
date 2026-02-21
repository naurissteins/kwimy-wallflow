from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk


class NavigationMixin:
    def _attach_navigation(self, flowbox: Gtk.FlowBox) -> None:
        flowbox.set_focusable(True)
        flowbox.connect("child-activated", self._on_child_activated)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        flowbox.add_controller(key_controller)

    def _on_child_activated(self, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
        self._set_selected_child(child)
        self._activate_selected()

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if not self._selected_child:
                self._select_first()
            self._activate_selected()
            return True
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_Down):
            self._move_selection(keyval)
            return True
        if keyval == Gdk.KEY_Home:
            self._select_index(0)
            return True
        if keyval == Gdk.KEY_End:
            self._select_index(-1)
            return True
        return False

    def _activate_selected(self) -> None:
        if not self._selected_child:
            return
        path_value = getattr(self._selected_child, "wallpaper_path", None)
        if not path_value:
            return
        self._run_matugen(Path(str(path_value)))

    def _select_first(self) -> None:
        children = self._flowbox_children()
        if not children:
            return
        self._set_selected_child(children[0], 0)

    def _select_index(self, index: int) -> None:
        children = self._flowbox_children()
        if not children:
            return
        if index < 0:
            index = len(children) - 1
        if index >= len(children):
            index = len(children) - 1
        self._set_selected_child(children[index], index)

    def _move_selection(self, keyval: int) -> None:
        children = self._flowbox_children()
        if not children:
            return
        if self._selected_child not in children:
            self._set_selected_child(children[0], 0)
            return

        index = self._selected_index
        stride = self._stride_for_navigation()
        if keyval == Gdk.KEY_Right:
            if self._scroll_direction == "horizontal":
                index += stride
            else:
                index += 1
        elif keyval == Gdk.KEY_Left:
            if self._scroll_direction == "horizontal":
                index -= stride
            else:
                index -= 1
        elif keyval == Gdk.KEY_Down:
            if self._scroll_direction == "horizontal":
                index += 1
            else:
                index += stride
        elif keyval == Gdk.KEY_Up:
            if self._scroll_direction == "horizontal":
                index -= 1
            else:
                index -= stride

        index = max(0, min(index, len(children) - 1))
        self._set_selected_child(children[index], index)

    def _set_selected_child(
        self, child: Gtk.FlowBoxChild, index: int | None = None
    ) -> None:
        if self._selected_child is child:
            return
        if self._selected_child:
            prev_box = self._selected_child.get_child()
            if prev_box:
                prev_box.remove_css_class("wallflow-selected")

        self._selected_child = child
        if index is None:
            children = self._flowbox_children()
            self._selected_index = children.index(child) if child in children else -1
        else:
            self._selected_index = index

        box = child.get_child()
        if box:
            box.add_css_class("wallflow-selected")
            if hasattr(box, "grab_focus"):
                box.grab_focus()
        self._scroll_to_child(child)

    def _flowbox_children(self) -> list[Gtk.FlowBoxChild]:
        if not self._flowbox:
            return []
        children: list[Gtk.FlowBoxChild] = []
        child = self._flowbox.get_first_child()
        while child:
            if isinstance(child, Gtk.FlowBoxChild):
                children.append(child)
            child = child.get_next_sibling()
        return children

    def _stride_for_navigation(self) -> int:
        if not self._flowbox:
            return 1
        try:
            max_line = int(self._flowbox.get_max_children_per_line())
        except Exception:
            max_line = 1

        if self._scroll_direction == "horizontal":
            spacing = self._flowbox.get_row_spacing()
            _thumb_width, thumb_height = self._thumbnail_dimensions()
            available = self._flowbox.get_allocated_height()
        else:
            spacing = self._flowbox.get_column_spacing()
            thumb_width, _thumb_height = self._thumbnail_dimensions()
            available = self._flowbox.get_allocated_width()

        if available <= 0:
            return max_line if max_line > 0 else 1

        if self._scroll_direction == "horizontal":
            calc = max(1, int((available + spacing) // (thumb_height + spacing)))
        else:
            calc = max(1, int((available + spacing) // (thumb_width + spacing)))

        if max_line > 0:
            return max(1, min(max_line, calc))
        return calc

    def _scroll_to_child(self, child: Gtk.FlowBoxChild) -> None:
        if not self._scroller:
            return
        adjustment = (
            self._scroller.get_hadjustment()
            if self._scroll_direction == "horizontal"
            else self._scroller.get_vadjustment()
        )
        if not adjustment:
            return

        alloc = self._get_allocation(child)
        if alloc is None:
            return
        x, y, width, height = alloc

        value = adjustment.get_value()
        page = adjustment.get_page_size()
        upper = adjustment.get_upper()
        padding = 12

        if self._scroll_direction == "horizontal":
            start = x
            end = x + width
        else:
            start = y
            end = y + height

        if start < value + padding:
            adjustment.set_value(max(0, start - padding))
        elif end > value + page - padding:
            target = end - page + padding
            adjustment.set_value(min(upper - page, max(0, target)))

    @staticmethod
    def _get_allocation(widget: Gtk.Widget) -> tuple[int, int, int, int] | None:
        try:
            alloc = widget.get_allocation()
            return (alloc.x, alloc.y, alloc.width, alloc.height)
        except Exception:
            return None
