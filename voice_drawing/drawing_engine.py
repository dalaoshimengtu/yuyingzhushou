"""
绘图引擎模块
使用 Tkinter 创建绘图窗口，支持多种图形的绘制和修改
"""

import tkinter as tk
from tkinter import filedialog
from typing import List, Dict, Optional, Tuple
import math


class ShapeLayer:
    """
    图形层：每个绘制的图形对应一个层，只保留当前最终状态。
    即使图形被删除或隐藏，层仍保留在 memory 中，支持后续按编号修改。
    """

    def __init__(self, shape_id: int, shape_type: str, canvas_ids: List[int], props: Dict):
        self.shape_id = shape_id
        self.shape_type = shape_type
        self.props = props       # 当前完整参数状态
        self.visible = True      # 是否在画布上可见
        self.canvas_ids = canvas_ids  # 当前画布对象 ID 列表

    def to_dict(self) -> Dict:
        """序列化用于撤销/重做"""
        return {
            "shape_id": self.shape_id,
            "shape_type": self.shape_type,
            "canvas_ids": list(self.canvas_ids),
            "props": dict(self.props),
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ShapeLayer":
        """从序列化数据恢复"""
        layer = cls(
            shape_id=data["shape_id"],
            shape_type=data["shape_type"],
            canvas_ids=list(data["canvas_ids"]),
            props=dict(data["props"]),
        )
        layer.visible = data.get("visible", True)
        return layer


class DrawingShape:
    """画布上的一个可见图形对象（从 ShapeLayer 派生，保持向后兼容）"""

    def __init__(self, shape_type: str, canvas_ids: List[int], props: Dict):
        self.shape_type = shape_type
        self.canvas_ids = canvas_ids
        self.props = props
        self.shape_id: int = props.get("shape_id", 0)
        self.label_id: Optional[int] = None

    def bbox(self, canvas: tk.Canvas) -> Tuple[float, float, float, float]:
        """获取图形的边界框"""
        if not self.canvas_ids:
            return (0, 0, 0, 0)
        all_coords = []
        for cid in self.canvas_ids:
            coords = canvas.coords(cid)
            all_coords.extend(coords)
        if not all_coords:
            return (0, 0, 0, 0)
        xs = all_coords[0::2]
        ys = all_coords[1::2]
        return (min(xs), min(ys), max(xs), max(ys))


class DrawingEngine:
    """绘图引擎"""

    MM_TO_PX = 3.78  # 1mm = 3.78px

    def __init__(self):
        self.root: Optional[tk.Tk] = None
        self.canvas: Optional[tk.Canvas] = None
        self.shapes: List[DrawingShape] = []  # 当前可见图形（向后兼容）
        self.layers: List[ShapeLayer] = []    # 图形层记忆（永不删除，只标记可见性）
        self.history: List[List] = []
        self.redo_stack: List[List] = []
        self.window_width = 900
        self.window_height = 700
        self._next_shape_id: int = 1
        self._labels_visible: bool = True

    def init_window(self) -> None:
        """初始化绘图窗口"""
        self.root = tk.Tk()
        self.root.title("语音控制绘图工具")
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.resizable(True, True)

        # 工具栏
        toolbar = tk.Frame(self.root, bg="#f0f0f0", height=40)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(toolbar, text="语音控制绘图工具", bg="#f0f0f0",
                 font=("微软雅黑", 12, "bold")).pack(side=tk.LEFT, padx=10, pady=5)

        self.status_var = tk.StringVar(value="就绪 - 请说出您的指令")
        tk.Label(toolbar, textvariable=self.status_var, bg="#f0f0f0",
                 font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=10)

        tk.Button(toolbar, text="保存", command=self.save_canvas).pack(side=tk.RIGHT, padx=5)
        tk.Button(toolbar, text="清空", command=self.clear_canvas).pack(side=tk.RIGHT, padx=5)
        tk.Button(toolbar, text="撤销", command=self.undo).pack(side=tk.RIGHT, padx=5)

        # 画布
        self.canvas = tk.Canvas(self.root, bg="white", highlightthickness=1,
                                highlightbackground="#ccc")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def set_status(self, text: str) -> None:
        if self.status_var:
            self.status_var.set(text)

    def _get_label_position(self, shape: DrawingShape) -> Tuple[float, float]:
        """获取编号标签的显示位置（图形上方居中）"""
        bx0, by0, bx1, by1 = shape.bbox(self.canvas)
        return ((bx0 + bx1) / 2, by0 - 8)

    def _add_label(self, shape: DrawingShape) -> None:
        """为图形添加编号标签"""
        if not self.canvas or shape.label_id:
            return
        label_x, label_y = self._get_label_position(shape)
        tag_text = f"[{shape.shape_id}]"
        shape.label_id = self.canvas.create_text(
            label_x, label_y, text=tag_text, fill="red",
            font=("Arial", 10, "bold"))

    def _remove_label(self, shape: DrawingShape) -> None:
        """移除图形的编号标签"""
        if shape.label_id and self.canvas:
            self.canvas.delete(shape.label_id)
            shape.label_id = None

    def _update_all_labels(self) -> None:
        """重新渲染所有可见的编号标签"""
        if not self.canvas:
            return
        for shape in self.shapes:
            self._remove_label(shape)
        if self._labels_visible:
            for shape in self.shapes:
                self._add_label(shape)

    def hide_labels(self) -> None:
        """隐藏所有编号标签（保留图形）"""
        self._labels_visible = False
        for shape in self.shapes:
            self._remove_label(shape)
        self.set_status("已隐藏所有编号标签")

    def show_labels(self) -> None:
        """显示所有编号标签"""
        self._labels_visible = True
        for shape in self.shapes:
            self._add_label(shape)
        self.set_status("已显示所有编号标签")

    def _assign_shape_id(self, shape: DrawingShape) -> None:
        """为图形分配编号"""
        shape.shape_id = self._next_shape_id
        shape.props["shape_id"] = self._next_shape_id
        self._next_shape_id += 1

    def execute_action(self, action: Dict) -> None:
        """执行一个绘图动作"""
        act = action.get("action", "")

        # 绘制
        if act == "draw_circle":
            self._draw_circle(action)
        elif act == "draw_ellipse":
            self._draw_ellipse(action)
        elif act == "draw_rect":
            self._draw_rect(action)
        elif act == "draw_line":
            self._draw_line(action)
        elif act == "draw_triangle":
            self._draw_triangle(action)
        elif act == "draw_arrow":
            self._draw_arrow(action)
        elif act == "draw_star":
            self._draw_star(action)
        elif act == "draw_polygon":
            self._draw_polygon(action)
        # 删除
        elif act == "delete_last":
            self._delete_last_shape()
        elif act == "delete_shape":
            self._delete_shape_by_type(action.get("shape_type"))
        # 修改
        elif act == "modify_remove_top_border":
            self._remove_rect_border("top", action.get("shape_type"), action.get("color"))
        elif act == "modify_remove_bottom_border":
            self._remove_rect_border("bottom", action.get("shape_type"), action.get("color"))
        elif act == "modify_remove_left_border":
            self._remove_rect_border("left", action.get("shape_type"), action.get("color"))
        elif act == "modify_remove_right_border":
            self._remove_rect_border("right", action.get("shape_type"), action.get("color"))
        elif act == "modify_change_color":
            self._change_shape_color(action.get("color", "black"), action.get("shape_type"))
        elif act == "modify_change_outline":
            self._change_shape_outline(action.get("color", "black"), action.get("shape_type"))
        elif act == "modify_fill":
            self._fill_shape(action.get("color", "gray"), action.get("shape_type"))
        elif act == "modify_clear_fill":
            self._clear_fill(action.get("shape_type"))
        elif act == "modify_thicken":
            self._thicken_lines(action.get("shape_type"))
        elif act == "modify_thin":
            self._thin_lines(action.get("shape_type"))
        elif act == "modify_duplicate":
            self._duplicate_shape(action.get("shape_type"))
        # 操作
        elif act == "op_move":
            self._move_shapes(
                action.get("direction", "center"),
                action.get("shape_type"),
                action.get("color"),
                action.get("distance"))
        elif act == "op_rotate":
            self._rotate_shapes(action.get("angle", 90), action.get("shape_type"), action.get("color"))
        elif act == "op_scale":
            self._scale_shapes(action.get("factor", 1.5), action.get("shape_type"), action.get("color"))
        elif act == "op_flip":
            self._flip_shapes(action.get("mode", "horizontal"), action.get("shape_type"), action.get("color"))
        elif act == "op_mirror":
            self._flip_shapes("horizontal", action.get("shape_type"), action.get("color"))
        # 系统
        elif act == "clear":
            self.clear_canvas()
        elif act == "undo":
            self.undo()
        elif act == "redo":
            self.redo()
        elif act == "save":
            self.save_canvas()
        elif act == "exit":
            if self.root:
                self.root.quit()
        elif act == "select":
            self._select_shape(action.get("shape_type"), action.get("shape_id"))
        elif act == "hide_labels":
            self.hide_labels()
        elif act == "show_labels":
            self.show_labels()
        elif act == "delete_by_id":
            self._delete_shape_by_id(action.get("shape_id"))
        elif act == "modify_by_id":
            self._modify_by_id(action)
        else:
            self.set_status(f"未知动作: {act}")

    # ---- 状态管理 ----

    def _save_state(self) -> None:
        self.redo_stack.clear()
        state = [layer.to_dict() for layer in self.layers]
        self.history.append(state)

    def _rebuild_canvas(self) -> None:
        """从 history 重建画布"""
        if self.canvas:
            self.canvas.delete("all")
        self.shapes.clear()
        self.layers.clear()

        if self.history:
            prev_state = self.history[-1]
            for item in prev_state:
                layer = ShapeLayer.from_dict(item)
                self.layers.append(layer)
                if layer.visible and layer.canvas_ids:
                    ids = self._recreate_shape(item)
                    layer.canvas_ids = ids or []
                    ds = DrawingShape(layer.shape_type, layer.canvas_ids, layer.props)
                    ds.shape_id = layer.shape_id
                    self.shapes.append(ds)
                    if self._labels_visible:
                        self._add_label(ds)
            # 恢复 _next_shape_id，避免 undo 后绘制新图形时 ID 冲突
            if self.layers:
                self._next_shape_id = max(layer.shape_id for layer in self.layers) + 1
            else:
                self._next_shape_id = 1

    def undo(self) -> None:
        if not self.history:
            self.set_status("没有可撤销的操作")
            return

        # 将当前 layers 完整状态压入 redo_stack，格式与 history 一致
        current_state = [layer.to_dict() for layer in self.layers]
        self.redo_stack.append(current_state)

        self.history.pop()
        self._rebuild_canvas()
        self.set_status("已撤销")

    def redo(self) -> None:
        if not self.redo_stack:
            self.set_status("没有可重做的操作")
            return

        self.history.append(self.redo_stack.pop())
        self._rebuild_canvas()
        self.set_status("已重做")

    # ---- 查找图形 ----

    def _find_shapes_by_type(self, shape_type: Optional[str], color: Optional[str] = None) -> List[DrawingShape]:
        """按类型和/或颜色查找图形，如果都为 None 则返回最后一个"""
        if shape_type is None and color is None:
            return self.shapes[-1:] if self.shapes else []
        result = self.shapes
        if shape_type:
            result = [s for s in result if s.shape_type == shape_type]
        if color:
            result = [s for s in result if s.props.get("color") == color]
        return result

    # ---- 绘制方法 ----

    def _draw_circle(self, action: Dict) -> None:
        radius = action.get("radius", 50)
        color = action.get("color", "black")
        fill = action.get("fill") or ""
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        cid = self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                       outline=color, fill=fill, width=2)
        props = {"color": color, "cx": cx, "cy": cy, "radius": radius, "fill": fill}
        ds = DrawingShape("circle", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        # 注册到层记忆
        layer = ShapeLayer(ds.shape_id, "circle", [cid], dict(props))
        self.layers.append(layer)
        mm = radius / self.MM_TO_PX
        if coords:
            self.set_status(f"已绘制圆形 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f}, 半径: {mm:.1f}mm)")
        else:
            self.set_status(f"已绘制圆形 #{ds.shape_id} (半径: {mm:.1f}mm)")

    def _draw_ellipse(self, action: Dict) -> None:
        rx = action.get("rx", 50)
        ry = action.get("ry", 50)
        color = action.get("color", "black")
        fill = action.get("fill") or ""
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        cid = self.canvas.create_oval(cx - rx, cy - ry, cx + rx, cy + ry,
                                      outline=color, fill=fill, width=2)
        props = {"color": color, "cx": cx, "cy": cy, "rx": rx, "ry": ry, "fill": fill}
        ds = DrawingShape("ellipse", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "ellipse", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制椭圆 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f}, rx: {rx / self.MM_TO_PX:.1f}mm, ry: {ry / self.MM_TO_PX:.1f}mm)")
        else:
            self.set_status(f"已绘制椭圆 #{ds.shape_id} (rx: {rx / self.MM_TO_PX:.1f}mm, ry: {ry / self.MM_TO_PX:.1f}mm)")

    def _draw_rect(self, action: Dict) -> None:
        w = action.get("width", 100)
        h = action.get("height", 60)
        color = action.get("color", "black")
        fill = action.get("fill") or ""
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        x0, y0 = cx - w / 2, cy - h / 2
        x1, y1 = cx + w / 2, cy + h / 2
        cid = self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, fill=fill, width=2)
        props = {"color": color, "cx": cx, "cy": cy, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "w": w, "h": h, "fill": fill}
        ds = DrawingShape("rect", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "rect", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制矩形 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f}, 宽: {w / self.MM_TO_PX:.1f}mm, 高: {h / self.MM_TO_PX:.1f}mm)")
        else:
            self.set_status(f"已绘制矩形 #{ds.shape_id} (宽: {w / self.MM_TO_PX:.1f}mm, 高: {h / self.MM_TO_PX:.1f}mm)")

    def _draw_line(self, action: Dict) -> None:
        params = action.get("params", [])
        color = action.get("color", "black")
        coords = action.get("coords")
        if len(params) >= 4:
            x1 = params[0] * self.MM_TO_PX
            y1 = params[1] * self.MM_TO_PX
            x2 = params[2] * self.MM_TO_PX
            y2 = params[3] * self.MM_TO_PX
        elif coords:
            x1, y1 = coords[0], coords[1]
            x2, y2 = x1 + 100, y1
        else:
            x1, y1 = 100, self.window_height // 2
            x2, y2 = self.window_width - 100, self.window_height // 2
        cid = self.canvas.create_line(x1, y1, x2, y2, fill=color, width=2)
        props = {"color": color, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        ds = DrawingShape("line", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "line", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制线段 #{ds.shape_id} (起点: {coords[0]:.0f},{coords[1]:.0f})")
        else:
            self.set_status(f"已绘制线段 #{ds.shape_id}")

    def _draw_triangle(self, action: Dict) -> None:
        side = action.get("side", 100)
        color = action.get("color", "black")
        fill = action.get("fill") or ""
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        half = side / 2
        height = side * 0.866
        pts = [cx, cy - height / 2, cx - half, cy + height / 2, cx + half, cy + height / 2]
        cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
        props = {"color": color, "cx": cx, "cy": cy, "side": side, "fill": fill}
        ds = DrawingShape("triangle", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "triangle", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制三角形 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f}, 边长: {side / self.MM_TO_PX:.1f}mm)")
        else:
            self.set_status(f"已绘制三角形 #{ds.shape_id} (边长: {side / self.MM_TO_PX:.1f}mm)")

    def _draw_arrow(self, action: Dict) -> None:
        color = action.get("color", "black")
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        pts = [cx - 60, cy, cx + 40, cy, cx + 20, cy - 20, cx + 60, cy, cx + 20, cy + 20]
        cid = self.canvas.create_polygon(pts, fill=color)
        props = {"color": color, "cx": cx, "cy": cy}
        ds = DrawingShape("arrow", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "arrow", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制箭头 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f})")
        else:
            self.set_status(f"已绘制箭头 #{ds.shape_id}")

    def _draw_star(self, action: Dict) -> None:
        size = action.get("size", 100)
        color = action.get("color", "black")
        fill = action.get("fill") or ""
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        pts = []
        for i in range(10):
            angle = math.pi * i / 5 - math.pi / 2
            r = size if i % 2 == 0 else size * 0.4
            pts.append(cx + r * math.cos(angle))
            pts.append(cy + r * math.sin(angle))
        cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
        props = {"color": color, "cx": cx, "cy": cy, "size": size, "fill": fill}
        ds = DrawingShape("star", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "star", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制五角星 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f}, 大小: {size / self.MM_TO_PX:.1f}mm)")
        else:
            self.set_status(f"已绘制五角星 #{ds.shape_id} (大小: {size / self.MM_TO_PX:.1f}mm)")

    def _draw_polygon(self, action: Dict) -> None:
        side_count = action.get("side_count", 6)
        size = action.get("size", 100)
        color = action.get("color", "black")
        fill = action.get("fill") or ""
        coords = action.get("coords")
        if coords:
            cx, cy = coords[0], coords[1]
        else:
            cx = self.window_width // 2
            cy = self.window_height // 2
        pts = []
        for i in range(side_count):
            angle = 2 * math.pi * i / side_count - math.pi / 2
            pts.append(cx + size * math.cos(angle))
            pts.append(cy + size * math.sin(angle))
        cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
        props = {"color": color, "cx": cx, "cy": cy, "side_count": side_count, "size": size, "fill": fill}
        ds = DrawingShape("polygon", [cid], dict(props))
        self._save_state()
        self._assign_shape_id(ds)
        self.shapes.append(ds)
        self._add_label(ds)
        layer = ShapeLayer(ds.shape_id, "polygon", [cid], dict(props))
        self.layers.append(layer)
        if coords:
            self.set_status(f"已绘制{side_count}边形 #{ds.shape_id} (坐标: {coords[0]:.0f},{coords[1]:.0f})")
        else:
            self.set_status(f"已绘制{side_count}边形 #{ds.shape_id}")

    # ---- 删除方法 ----

    def _delete_last_shape(self) -> None:
        """删除最后一个图形（隐藏层，不从 memory 移除）"""
        if not self.shapes:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        shape = self.shapes.pop()
        for cid in shape.canvas_ids:
            self.canvas.delete(cid)
        # 隐藏层
        for layer in self.layers:
            if layer.shape_id == shape.shape_id:
                layer.visible = False
                layer.canvas_ids = []
                break
        self.canvas.update()
        self.set_status(f"已删除最后一个图形 ({shape.shape_type})")

    def _delete_shape_by_type(self, shape_type: Optional[str]) -> None:
        """按类型删除图形（隐藏层，不从 memory 移除）"""
        targets = self._find_shapes_by_type(shape_type)
        if not targets:
            name = shape_type if shape_type else "图形"
            self.set_status(f"画布上没有{ name }")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                self.canvas.delete(cid)
            self.shapes.remove(shape)
            # 隐藏层
            for layer in self.layers:
                if layer.shape_id == shape.shape_id:
                    layer.visible = False
                    layer.canvas_ids = []
                    break
        self.canvas.update()
        name = shape_type if shape_type else "图形"
        self.set_status(f"已删除 {len(targets)} 个{name}")

    # ---- 修改方法 ----

    def _remove_rect_border(self, side: str, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        rects = [s for s in targets if s.shape_type == "rect"]
        if not rects:
            self.set_status("画布上没有矩形，无法去除边框")
            return
        self._save_state()
        for shape in rects:
            props = shape.props
            for cid in shape.canvas_ids:
                self.canvas.delete(cid)
            shape.canvas_ids.clear()

            x0, y0, x1, y1 = props["x0"], props["y0"], props["x1"], props["y1"]
            color = props.get("color", "black")
            lines = []
            if side != "top":
                lines.append(self.canvas.create_line(x0, y0, x1, y0, fill=color, width=2))
            if side != "bottom":
                lines.append(self.canvas.create_line(x0, y1, x1, y1, fill=color, width=2))
            if side != "left":
                lines.append(self.canvas.create_line(x0, y0, x0, y1, fill=color, width=2))
            if side != "right":
                lines.append(self.canvas.create_line(x1, y0, x1, y1, fill=color, width=2))
            shape.canvas_ids = lines
            props["removed_border"] = side
        self.set_status(f"已去除矩形{side}边框")

    def _change_shape_color(self, color: str, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                try:
                    self.canvas.itemconfig(cid, outline=color)
                except tk.TclError:
                    self.canvas.itemconfig(cid, fill=color)
            shape.props["color"] = color
        self.set_status(f"颜色已更改为 {color}")

    def _change_shape_outline(self, color: str, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                self.canvas.itemconfig(cid, outline=color)
            shape.props["color"] = color
        self.set_status(f"轮廓颜色已更改为 {color}")

    def _fill_shape(self, color: str, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                self.canvas.itemconfig(cid, fill=color)
            shape.props["fill"] = color
        self.set_status(f"已填充颜色 {color}")

    def _clear_fill(self, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                self.canvas.itemconfig(cid, fill="")
            shape.props["fill"] = ""
        self.set_status("已取消填充")

    def _thicken_lines(self, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                try:
                    cur = self.canvas.itemcget(cid, "width")
                    new_w = max(1, int(float(cur or 2)) + 1)
                    self.canvas.itemconfig(cid, width=new_w)
                except tk.TclError:
                    pass
        self.set_status("线条已加粗")

    def _thin_lines(self, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            for cid in shape.canvas_ids:
                try:
                    cur = self.canvas.itemcget(cid, "width")
                    new_w = max(1, int(float(cur or 2)) - 1)
                    self.canvas.itemconfig(cid, width=new_w)
                except tk.TclError:
                    pass
        self.set_status("线条已变细")

    def _duplicate_shape(self, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        for shape in targets:
            new_ids = []
            for cid in shape.canvas_ids:
                new_cid = self.canvas.clone(cid)
                self.canvas.move(new_cid, 20, 20)
                new_ids.append(new_cid)
            new_props = dict(shape.props)
            self.shapes.append(DrawingShape(shape.shape_type, new_ids, new_props))
        self.set_status("已复制图形")

    # ---- 操作方法 ----

    def _move_shapes(self, direction: str, shape_type: Optional[str] = None, color: Optional[str] = None, distance: Optional[float] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, color)
        if not targets:
            name = shape_type if shape_type else "图形"
            if color:
                self.set_status(f"画布上没有{color}的{name}")
            else:
                self.set_status(f"画布上没有{name}")
            return
        self._save_state()
        offset = distance if distance else 30

        if direction == "center":
            for shape in targets:
                bx0, by0, bx1, by1 = shape.bbox(self.canvas)
                bw = bx1 - bx0
                bh = by1 - by0
                dx = (self.window_width // 2 - bw / 2) - bx0
                dy = (self.window_height // 2 - bh / 2) - by0
                for cid in shape.canvas_ids:
                    self.canvas.move(cid, dx, dy)
                # 编号标签跟着移动
                if shape.label_id:
                    self.canvas.move(shape.label_id, dx, dy)
            self.set_status("图形已移至中心")
            return

        if direction == "up":
            dx, dy = 0, -offset
        elif direction == "down":
            dx, dy = 0, offset
        elif direction == "left":
            dx, dy = -offset, 0
        elif direction == "right":
            dx, dy = offset, 0
        else:
            dx, dy = 0, 0

        for shape in targets:
            for cid in shape.canvas_ids:
                self.canvas.move(cid, dx, dy)
            # 编号标签跟着移动
            if shape.label_id:
                self.canvas.move(shape.label_id, dx, dy)
        desc = f"{color}的" if color else ""
        self.set_status(f"{desc}图形已向{direction}移动 {offset}px")

    def _rotate_shapes(self, angle: float, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        """以图形自身几何中心为原点，z轴为旋转轴旋转"""
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()

        rad = angle * math.pi / 180.0
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        def _rot_pt(x, y, cx, cy):
            return cx + (x - cx) * cos_a + (y - cy) * sin_a, \
                   cy - (x - cx) * sin_a + (y - cy) * cos_a

        for shape in targets:
            if shape.shape_type == "circle":
                # 圆形绕中心旋转视觉不变
                continue
            elif shape.shape_type == "rect":
                props = shape.props
                cx = props.get("cx", 0)
                cy = props.get("cy", 0)
                x0, y0 = props.get("x0", 0), props.get("y0", 0)
                x1, y1 = props.get("x1", 0), props.get("y1", 0)
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                pts = []
                for x, y in corners:
                    nx, ny = _rot_pt(x, y, cx, cy)
                    pts.extend([nx, ny])
                color = props.get("color", "black")
                fill = props.get("fill", "")
                for cid in shape.canvas_ids:
                    self.canvas.delete(cid)
                new_cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
                shape.canvas_ids = [new_cid]
                shape.props["rotated_pts"] = pts
            elif shape.shape_type == "triangle":
                props = shape.props
                cx = props.get("cx", 0)
                cy = props.get("cy", 0)
                side = props.get("side", 100)
                half = side / 2
                height = side * 0.866
                orig = [(cx, cy - height/2), (cx - half, cy + height/2), (cx + half, cy + height/2)]
                pts = []
                for x, y in orig:
                    nx, ny = _rot_pt(x, y, cx, cy)
                    pts.extend([nx, ny])
                color = props.get("color", "black")
                fill = props.get("fill", "")
                for cid in shape.canvas_ids:
                    self.canvas.delete(cid)
                new_cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
                shape.canvas_ids = [new_cid]
                shape.props["rotated_pts"] = pts
            elif shape.shape_type in ("star", "polygon"):
                props = shape.props
                cx = props.get("cx", 0)
                cy = props.get("cy", 0)
                size = props.get("size", 100)
                if shape.shape_type == "star":
                    orig = []
                    for i in range(10):
                        a = math.pi * i / 5 - math.pi / 2
                        r = size if i % 2 == 0 else size * 0.4
                        orig.append((cx + r * math.cos(a), cy + r * math.sin(a)))
                else:
                    side_count = props.get("side_count", 6)
                    orig = []
                    for i in range(side_count):
                        a = 2 * math.pi * i / side_count - math.pi / 2
                        orig.append((cx + size * math.cos(a), cy + size * math.sin(a)))
                pts = []
                for x, y in orig:
                    nx, ny = _rot_pt(x, y, cx, cy)
                    pts.extend([nx, ny])
                color = props.get("color", "black")
                fill = props.get("fill", "")
                for cid in shape.canvas_ids:
                    self.canvas.delete(cid)
                new_cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
                shape.canvas_ids = [new_cid]
                shape.props["rotated_pts"] = pts
            else:
                # 通用：对现有画布坐标点旋转
                all_coords = []
                for cid in shape.canvas_ids:
                    all_coords.extend(self.canvas.coords(cid))
                if not all_coords:
                    continue
                cx = sum(all_coords[::2]) / (len(all_coords) // 2)
                cy = sum(all_coords[1::2]) / (len(all_coords) // 2)
                for cid in shape.canvas_ids:
                    coords = self.canvas.coords(cid)
                    new_coords = []
                    for i in range(0, len(coords), 2):
                        nx, ny = _rot_pt(coords[i], coords[i+1], cx, cy)
                        new_coords.append(nx)
                        new_coords.append(ny)
                    self.canvas.coords(cid, *new_coords)

        self.set_status(f"图形已旋转 {angle} 度")

    def _scale_shapes(self, factor: float, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        cx = self.window_width // 2
        cy = self.window_height // 2

        for shape in targets:
            for cid in shape.canvas_ids:
                coords = self.canvas.coords(cid)
                new_coords = []
                for i in range(0, len(coords), 2):
                    nx = cx + (coords[i] - cx) * factor
                    ny = cy + (coords[i + 1] - cy) * factor
                    new_coords.append(nx)
                    new_coords.append(ny)
                self.canvas.coords(cid, *new_coords)
        self.set_status(f"图形已缩放 ({factor}x)")

    def _flip_shapes(self, mode: str, shape_type: Optional[str] = None, filter_color: Optional[str] = None) -> None:
        targets = self._find_shapes_by_type(shape_type, filter_color)
        if not targets:
            self.set_status("画布上没有图形")
            return
        self._save_state()
        cx = self.window_width // 2
        cy = self.window_height // 2

        for shape in targets:
            for cid in shape.canvas_ids:
                coords = self.canvas.coords(cid)
                new_coords = []
                for i in range(0, len(coords), 2):
                    if mode == "horizontal":
                        nx = 2 * cx - coords[i]
                        ny = coords[i + 1]
                    else:
                        nx = coords[i]
                        ny = 2 * cy - coords[i + 1]
                    new_coords.append(nx)
                    new_coords.append(ny)
                self.canvas.coords(cid, *new_coords)
        self.set_status(f"图形已{mode}翻转")

    def _select_shape(self, shape_type: Optional[str] = None, shape_id: Optional[int] = None) -> None:
        if shape_id:
            targets = self._find_shape_by_id(shape_id)
        else:
            targets = self._find_shapes_by_type(shape_type)
        if not targets:
            self.set_status("画布上没有图形")
            return
        name = f"图形 #{shape_id}" if shape_id else (shape_type if shape_type else "图形")
        self.set_status(f"已选中 {len(targets)} 个{name}")

    def _find_shape_by_id(self, shape_id: int) -> Optional[DrawingShape]:
        """按编号查找可见图形"""
        for shape in self.shapes:
            if shape.shape_id == shape_id:
                return shape
        return None

    def _find_layer_by_id(self, shape_id: int) -> Optional[ShapeLayer]:
        """按编号查找层（即使已删除也能找到）"""
        for layer in self.layers:
            if layer.shape_id == shape_id:
                return layer
        return None

    def _delete_shape_by_id(self, shape_id: int) -> None:
        """按编号删除图形（隐藏层，不从 memory 移除）"""
        shape = self._find_shape_by_id(shape_id)
        if not shape:
            self.set_status(f"不存在编号为 {shape_id} 的图形")
            return
        self._save_state()
        self._remove_label(shape)
        for cid in shape.canvas_ids:
            self.canvas.delete(cid)
        self.shapes.remove(shape)
        # 隐藏层
        layer = self._find_layer_by_id(shape_id)
        if layer:
            layer.visible = False
            layer.canvas_ids = []
        self.canvas.update()
        self.set_status(f"已删除图形 #{shape_id}")

    def _modify_by_id(self, action: Dict) -> None:
        """按编号修改图形（支持已删除的图形，通过层重建）"""
        shape_id = action.get("shape_id")
        if not shape_id:
            self.set_status("请指定图形编号")
            return

        # shape_id=-1 表示默认修改最后一个线段
        if shape_id == -1:
            last_line = None
            for shape in reversed(self.shapes):
                if shape.shape_type == "line":
                    last_line = shape
                    break
            if not last_line:
                self.set_status("画布上没有线段")
                return
            shape_id = last_line.shape_id
            action["shape_id"] = shape_id  # 更新 action 供后续使用

        # 先查可见图形，找不到则查层记忆
        shape = self._find_shape_by_id(shape_id)
        layer = self._find_layer_by_id(shape_id)
        if not layer:
            self.set_status(f"不存在编号为 {shape_id} 的图形")
            return
        # 如果图形不可见，先重建到画布
        if not shape:
            self._restore_layer_to_canvas(layer)
            shape = self._find_shape_by_id(shape_id)
            if not shape:
                return

        self._save_state()
        mod_action = action.get("mod_action")
        if mod_action == "change_color":
            color = action.get("color", "black")
            for cid in shape.canvas_ids:
                try:
                    self.canvas.itemconfig(cid, outline=color)
                except tk.TclError:
                    self.canvas.itemconfig(cid, fill=color)
            shape.props["color"] = color
            layer.props["color"] = color
            self.set_status(f"图形 #{shape_id} 颜色已更改为 {color}")
        elif mod_action == "move":
            direction = action.get("direction", "right")
            distance = action.get("distance", 30)
            if direction == "up":
                dx, dy = 0, -distance
            elif direction == "down":
                dx, dy = 0, distance
            elif direction == "left":
                dx, dy = -distance, 0
            else:
                dx, dy = distance, 0
            for cid in shape.canvas_ids:
                self.canvas.move(cid, dx, dy)
            self._remove_label(shape)
            self._add_label(shape)
            # 更新层中的位置参数
            self._sync_layer_props(layer, shape)
            self.set_status(f"图形 #{shape_id} 已向{direction}移动 {distance}px")
        elif mod_action == "rotate":
            angle = action.get("angle", 90)
            shape_type = layer.shape_type

            # 圆形绕中心旋转视觉不变，直接跳过
            if shape_type == "circle":
                self.set_status(f"图形 #{shape_id} 已旋转 {angle} 度")
                return

            # 获取图形中心
            props = layer.props
            if shape_type == "rect":
                cx = props.get("cx", self.window_width // 2)
                cy = props.get("cy", self.window_height // 2)
            else:
                all_coords = []
                for cid in shape.canvas_ids:
                    all_coords.extend(self.canvas.coords(cid))
                if all_coords:
                    cx = sum(all_coords[::2]) / (len(all_coords) // 2)
                    cy = sum(all_coords[1::2]) / (len(all_coords) // 2)
                else:
                    cx = layer.props.get("cx", self.window_width // 2)
                    cy = layer.props.get("cy", self.window_height // 2)

            rad = angle * math.pi / 180.0
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            def _rot_pt(x, y):
                """旋转单个点"""
                dx = x - cx
                dy = y - cy
                nx = cx + dx * cos_a + dy * sin_a
                ny = cy - dx * sin_a + dy * cos_a
                return nx, ny

            color = layer.props.get("color", "black")
            fill = layer.props.get("fill", "")

            if shape_type == "rect":
                # 矩形：用4个角点旋转后重新绘制为多边形
                x0, y0 = layer.props.get("x0", 0), layer.props.get("y0", 0)
                x1, y1 = layer.props.get("x1", 0), layer.props.get("y1", 0)
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                rotated = [_rot_pt(x, y) for x, y in corners]
                pts = [coord for x, y in rotated for coord in (x, y)]
                for cid in shape.canvas_ids:
                    self.canvas.delete(cid)
                new_cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
                shape.canvas_ids = [new_cid]
                shape.props["rotated"] = True
                shape.props["rotated_pts"] = pts
            elif shape_type == "triangle":
                side = layer.props.get("side", 100)
                half = side / 2
                height = side * 0.866
                orig = [
                    (cx, cy - height / 2),
                    (cx - half, cy + height / 2),
                    (cx + half, cy + height / 2),
                ]
                rotated = [_rot_pt(x, y) for x, y in orig]
                pts = [coord for x, y in rotated for coord in (x, y)]
                for cid in shape.canvas_ids:
                    self.canvas.delete(cid)
                new_cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
                shape.canvas_ids = [new_cid]
                shape.props["rotated_pts"] = pts
            elif shape_type in ("star", "polygon"):
                size = layer.props.get("size", 100)
                if shape_type == "star":
                    orig = []
                    for i in range(10):
                        a = math.pi * i / 5 - math.pi / 2
                        r = size if i % 2 == 0 else size * 0.4
                        orig.append((cx + r * math.cos(a), cy + r * math.sin(a)))
                else:
                    side_count = layer.props.get("side_count", 6)
                    orig = []
                    for i in range(side_count):
                        a = 2 * math.pi * i / side_count - math.pi / 2
                        orig.append((cx + size * math.cos(a), cy + size * math.sin(a)))
                rotated = [_rot_pt(x, y) for x, y in orig]
                pts = [coord for x, y in rotated for coord in (x, y)]
                for cid in shape.canvas_ids:
                    self.canvas.delete(cid)
                new_cid = self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)
                shape.canvas_ids = [new_cid]
                shape.props["rotated_pts"] = pts
            else:
                # 通用：对现有画布坐标点进行旋转
                for cid in shape.canvas_ids:
                    coords = self.canvas.coords(cid)
                    new_coords = []
                    for i in range(0, len(coords), 2):
                        x = coords[i]
                        y = coords[i + 1]
                        nx = cx + (x - cx) * cos_a + (y - cy) * sin_a
                        ny = cy - (x - cx) * sin_a + (y - cy) * cos_a
                        new_coords.append(nx)
                        new_coords.append(ny)
                    self.canvas.coords(cid, *new_coords)

            self._remove_label(shape)
            self._add_label(shape)
            self._sync_layer_props(layer, shape)
            self.set_status(f"图形 #{shape_id} 已旋转 {angle} 度")
        elif mod_action == "delete":
            self._delete_shape_by_id(shape_id)
        elif mod_action == "fill":
            color = action.get("color", "gray")
            for cid in shape.canvas_ids:
                self.canvas.itemconfig(cid, fill=color)
            shape.props["fill"] = color
            layer.props["fill"] = color
            self.set_status(f"图形 #{shape_id} 已填充颜色 {color}")
        elif mod_action == "scale":
            factor = action.get("factor", 0.5)
            # 获取图形中心
            all_coords = []
            for cid in shape.canvas_ids:
                all_coords.extend(self.canvas.coords(cid))
            if all_coords:
                cx = sum(all_coords[::2]) / (len(all_coords) // 2)
                cy = sum(all_coords[1::2]) / (len(all_coords) // 2)
            else:
                cx = shape.props.get("cx", self.window_width // 2)
                cy = shape.props.get("cy", self.window_height // 2)
            # 对每个 canvas 对象进行缩放
            for cid in shape.canvas_ids:
                coords = self.canvas.coords(cid)
                new_coords = []
                for i in range(0, len(coords), 2):
                    x = coords[i]
                    y = coords[i + 1]
                    nx = cx + (x - cx) * factor
                    ny = cy + (y - cy) * factor
                    new_coords.append(nx)
                    new_coords.append(ny)
                self.canvas.coords(cid, *new_coords)
            self._remove_label(shape)
            self._add_label(shape)
            self._sync_layer_props(layer, shape)
            self.set_status(f"图形 #{shape_id} 已缩放为 {factor * 100:.0f}%")
        elif mod_action == "change_property":
            self._change_shape_property(shape, layer, action)
        else:
            self.set_status(f"未知修改动作: {mod_action}")

    def _restore_layer_to_canvas(self, layer: ShapeLayer) -> None:
        """将隐藏/删除的层重新绘制到画布上"""
        if layer.visible and layer.canvas_ids:
            return  # 已经可见
        self._save_state()
        ids = self._recreate_shape(layer.to_dict())
        if ids:
            layer.canvas_ids = ids
            layer.visible = True
            ds = DrawingShape(layer.shape_type, list(ids), dict(layer.props))
            ds.shape_id = layer.shape_id
            self.shapes.append(ds)
            self._add_label(ds)
            self.set_status(f"已恢复图形 #{layer.shape_id}")
        else:
            self.set_status(f"无法恢复图形 #{layer.shape_id}")

    def _sync_layer_props(self, layer: ShapeLayer, shape: DrawingShape) -> None:
        """将 DrawingShape 的当前状态同步到层"""
        layer.props.update(shape.props)
        layer.canvas_ids = list(shape.canvas_ids)
        layer.visible = True

    def _change_shape_property(self, shape: DrawingShape, layer: ShapeLayer, action: Dict) -> None:
        """
        按编号修改图形属性，在原位置重新绘制
        支持修改: radius, width, height, side, size
        """
        shape_id = shape.shape_id
        shape_type = shape.shape_type
        props = dict(shape.props)
        color = props.get("color", "black")
        fill = props.get("fill", "")

        # 根据图形类型修改对应属性
        if shape_type == "circle":
            if "radius" not in action:
                self.set_status(f"图形 #{shape_id} 是圆形，请使用'半径'参数修改")
                return
            new_radius = float(action["radius"])
            props["radius"] = new_radius
            props["cx"] = props.get("cx", self.window_width // 2)
            props["cy"] = props.get("cy", self.window_height // 2)
            cx, cy = props["cx"], props["cy"]
            self._redraw_shape(shape, layer, shape_type, color, fill, props,
                self.canvas.create_oval(cx - new_radius, cy - new_radius, cx + new_radius, cy + new_radius,
                                        outline=color, fill=fill, width=2))

        elif shape_type == "ellipse":
            if "width" in action and "height" in action:
                props["rx"] = float(action["width"])
                props["ry"] = float(action["height"])
            elif "width" in action:
                props["rx"] = float(action["width"])
            elif "height" in action:
                props["ry"] = float(action["height"])
            else:
                self.set_status(f"图形 #{shape_id} 是椭圆，请使用'宽'和'高'参数修改")
                return
            props["cx"] = props.get("cx", self.window_width // 2)
            props["cy"] = props.get("cy", self.window_height // 2)
            cx, cy = props["cx"], props["cy"]
            self._redraw_shape(shape, layer, shape_type, color, fill, props,
                self.canvas.create_oval(cx - props["rx"], cy - props["ry"], cx + props["rx"], cy + props["ry"],
                                        outline=color, fill=fill, width=2))

        elif shape_type == "rect":
            if "width" in action and "height" in action:
                props["w"] = float(action["width"])
                props["h"] = float(action["height"])
            elif "width" in action:
                props["w"] = float(action["width"])
                if "h" not in props:
                    props["h"] = 60
            elif "height" in action:
                props["h"] = float(action["height"])
                if "w" not in props:
                    props["w"] = 100
            else:
                self.set_status(f"图形 #{shape_id} 是矩形，请使用'宽'和'高'参数修改")
                return
            # 重新计算位置（保持中心不变）
            cx = props.get("cx", self.window_width // 2)
            cy = props.get("cy", self.window_height // 2)
            if "cx" not in props:
                cx = (props["x0"] + props["x1"]) / 2
            if "cy" not in props:
                cy = (props["y0"] + props["y1"]) / 2
            props["cx"] = cx
            props["cy"] = cy
            w, h = props["w"], props["h"]
            x0, y0 = cx - w / 2, cy - h / 2
            x1, y1 = cx + w / 2, cy + h / 2
            props["x0"], props["y0"], props["x1"], props["y1"] = x0, y0, x1, y1
            self._redraw_shape(shape, layer, shape_type, color, fill, props,
                self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, fill=fill, width=2))

        elif shape_type == "triangle":
            if "side" not in action:
                self.set_status(f"图形 #{shape_id} 是三角形，请使用'边长'参数修改")
                return
            new_side = float(action["side"])
            props["side"] = new_side
            cx = props.get("cx", self.window_width // 2)
            cy = props.get("cy", self.window_height // 2)
            half = new_side / 2
            height = new_side * 0.866
            pts = [cx, cy - height / 2, cx - half, cy + height / 2, cx + half, cy + height / 2]
            self._redraw_shape(shape, layer, shape_type, color, fill, props,
                self.canvas.create_polygon(pts, outline=color, fill=fill, width=2))

        elif shape_type == "line":
            if "length" not in action:
                self.set_status(f"图形 #{shape_id} 是线段，请使用'长度'参数修改")
                return
            new_length = float(action["length"])
            props["length"] = new_length
            # 计算线段中心（优先从已有端点坐标计算，保持线段在原位置）
            if "cx" in props:
                cx = props["cx"]
                cy = props["cy"]
            elif "x1" in props and "x2" in props:
                cx = (props["x1"] + props["x2"]) / 2
                cy = (props["y1"] + props["y2"]) / 2
                props["cx"] = cx
                props["cy"] = cy
            else:
                cx = self.window_width // 2
                cy = self.window_height // 2
            half = new_length / 2
            x0, y0 = cx - half, cy
            x1, y1 = cx + half, cy
            props["x0"], props["y0"], props["x1"], props["y1"] = x0, y0, x1, y1
            self._redraw_shape(shape, layer, shape_type, color, fill, props,
                self.canvas.create_line(x0, y0, x1, y1, fill=color, width=2))

        elif shape_type in ("star", "polygon"):
            if "size" not in action:
                self.set_status(f"图形 #{shape_id} 请使用'大小'参数修改")
                return
            new_size = float(action["size"])
            props["size"] = new_size
            cx = props.get("cx", self.window_width // 2)
            cy = props.get("cy", self.window_height // 2)
            pts = []
            if shape_type == "star":
                for i in range(10):
                    angle = math.pi * i / 5 - math.pi / 2
                    r = new_size if i % 2 == 0 else new_size * 0.4
                    pts.append(cx + r * math.cos(angle))
                    pts.append(cy + r * math.sin(angle))
            else:
                side_count = props.get("side_count", 6)
                for i in range(side_count):
                    angle = 2 * math.pi * i / side_count - math.pi / 2
                    pts.append(cx + new_size * math.cos(angle))
                    pts.append(cy + new_size * math.sin(angle))
            self._redraw_shape(shape, layer, shape_type, color, fill, props,
                self.canvas.create_polygon(pts, outline=color, fill=fill, width=2))

        else:
            self.set_status(f"图形 #{shape_id} 类型({shape_type})不支持属性修改")

    def _redraw_shape(self, shape: DrawingShape, layer: ShapeLayer, shape_type: str, color: str, fill: str,
                      new_props: Dict, new_cid: int) -> None:
        """删除旧图形并重新绘制新图形，同步更新层"""
        # 删除旧的 canvas 对象
        for cid in shape.canvas_ids:
            self.canvas.delete(cid)
        # 更新形状
        shape.canvas_ids = [new_cid]
        shape.props = new_props
        # 同步层
        layer.props = new_props
        layer.canvas_ids = [new_cid]
        layer.visible = True
        # 更新标签位置
        self._remove_label(shape)
        self._add_label(shape)
        self.set_status(f"图形 #{shape.shape_id} 属性已更新")

    # ---- 通用方法 ----

    def clear_canvas(self) -> None:
        if self.canvas:
            self.canvas.delete("all")
            self.shapes.clear()
            self.layers.clear()
            self._save_state()
            self.set_status("画布已清空")

    def _recreate_shape(self, item: Dict) -> Optional[List[int]]:
        shape_type = item["shape_type"]
        props = item["props"]
        color = props.get("color", "black")
        fill = props.get("fill", "")

        if shape_type == "circle":
            r = props["radius"]
            return [self.canvas.create_oval(
                props["cx"] - r, props["cy"] - r,
                props["cx"] + r, props["cy"] + r,
                outline=color, fill=fill, width=2)]
        elif shape_type == "ellipse":
            return [self.canvas.create_oval(
                props["cx"] - props["rx"], props["cy"] - props["ry"],
                props["cx"] + props["rx"], props["cy"] + props["ry"],
                outline=color, fill=fill, width=2)]
        elif shape_type == "rect":
            if props.get("removed_border"):
                x0, y0, x1, y1 = props["x0"], props["y0"], props["x1"], props["y1"]
                removed = props["removed_border"]
                lines = []
                if removed != "top":
                    lines.append(self.canvas.create_line(x0, y0, x1, y0, fill=color, width=2))
                if removed != "bottom":
                    lines.append(self.canvas.create_line(x0, y1, x1, y1, fill=color, width=2))
                if removed != "left":
                    lines.append(self.canvas.create_line(x0, y0, x0, y1, fill=color, width=2))
                if removed != "right":
                    lines.append(self.canvas.create_line(x1, y0, x1, y1, fill=color, width=2))
                return lines
            return [self.canvas.create_rectangle(
                props["x0"], props["y0"], props["x1"], props["y1"],
                outline=color, fill=fill, width=2)]
        elif shape_type == "line":
            return [self.canvas.create_line(
                props["x1"], props["y1"], props["x2"], props["y2"],
                fill=color, width=2)]
        elif shape_type == "triangle":
            side = props["side"]
            half = side / 2
            height = side * 0.866
            return [self.canvas.create_polygon([
                props["cx"], props["cy"] - height / 2,
                props["cx"] - half, props["cy"] + height / 2,
                props["cx"] + half, props["cy"] + height / 2,
            ], outline=color, fill=fill, width=2)]
        elif shape_type == "arrow":
            cx, cy = props["cx"], props["cy"]
            pts = [cx - 60, cy, cx + 40, cy, cx + 20, cy - 20, cx + 60, cy, cx + 20, cy + 20]
            return [self.canvas.create_polygon(pts, fill=color)]
        elif shape_type in ("star", "polygon"):
            size = props.get("size", 100)
            cx, cy = props["cx"], props["cy"]
            if shape_type == "star":
                pts = []
                for i in range(10):
                    angle = math.pi * i / 5 - math.pi / 2
                    r = size if i % 2 == 0 else size * 0.4
                    pts.append(cx + r * math.cos(angle))
                    pts.append(cy + r * math.sin(angle))
            else:
                side_count = props.get("side_count", 6)
                pts = []
                for i in range(side_count):
                    angle = 2 * math.pi * i / side_count - math.pi / 2
                    pts.append(cx + size * math.cos(angle))
                    pts.append(cy + size * math.sin(angle))
            return [self.canvas.create_polygon(pts, outline=color, fill=fill, width=2)]
        return None

    def save_canvas(self) -> None:
        if not self.canvas:
            return
        try:
            from PIL import ImageGrab
            x = self.root.winfo_rootx() + self.canvas.winfo_x()
            y = self.root.winfo_rooty() + self.canvas.winfo_y()
            x1 = x + self.canvas.winfo_width()
            y1 = y + self.canvas.winfo_height()
            img = ImageGrab.grab(bbox=(x, y, x1, y1))
            path = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG", "*.png")])
            if path:
                img.save(path)
                self.set_status(f"已保存到: {path}")
        except Exception as e:
            self.set_status(f"保存失败: {e}")

    def run(self) -> None:
        if self.root:
            self.root.mainloop()

    def update(self) -> None:
        if self.root:
            self.root.update()
