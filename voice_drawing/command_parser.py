"""
命令解析模块
将标准化指令拆解为具体的绘图动作
"""

from typing import Dict, List


class CommandParser:
    """命令解析器"""

    def parse(self, cmd: Dict) -> List[Dict]:
        """将标准化指令拆解为可执行的绘图动作列表"""
        cmd_type = cmd.get("type")

        if cmd_type == "draw":
            return self._parse_draw(cmd)
        elif cmd_type == "modify":
            return self._parse_modify(cmd)
        elif cmd_type == "operation":
            return self._parse_operation(cmd)
        elif cmd_type == "delete":
            return self._parse_delete(cmd)
        elif cmd_type in ("exit", "save", "undo", "redo", "clear"):
            return [{"action": cmd_type}]
        elif cmd_type == "hide_labels":
            return [{"action": "hide_labels"}]
        elif cmd_type == "show_labels":
            return [{"action": "show_labels"}]
        elif cmd_type == "delete_by_id":
            return [{"action": "delete_by_id", "shape_id": cmd.get("shape_id")}]
        elif cmd_type == "modify_by_id":
            return self._parse_modify_by_id(cmd)
        elif cmd_type == "select":
            return self._parse_select(cmd)
        else:
            return [{"action": "unknown"}]

    def _parse_draw(self, cmd: Dict) -> List[Dict]:
        """解析绘制命令"""
        shape = cmd.get("shape")
        color = cmd.get("color", "black")
        fill = cmd.get("fill")

        if shape == "circle":
            return [{
                "action": "draw_circle",
                "radius": cmd.get("radius", 50),
                "color": color,
                "fill": fill,
                "coords": cmd.get("coords"),
            }]
        elif shape == "ellipse":
            return [{
                "action": "draw_ellipse",
                "rx": cmd.get("rx", 50),
                "ry": cmd.get("ry", 50),
                "color": color,
                "fill": fill,
                "coords": cmd.get("coords"),
            }]
        elif shape == "rect":
            return [{
                "action": "draw_rect",
                "width": cmd.get("width", 100),
                "height": cmd.get("height", 60),
                "color": color,
                "fill": fill,
                "coords": cmd.get("coords"),
            }]
        elif shape == "line":
            return [{
                "action": "draw_line",
                "params": cmd.get("params", []),
                "color": color,
                "coords": cmd.get("coords"),
            }]
        elif shape == "triangle":
            return [{
                "action": "draw_triangle",
                "side": cmd.get("side", 100),
                "color": color,
                "fill": fill,
                "coords": cmd.get("coords"),
            }]
        elif shape == "arrow":
            return [{"action": "draw_arrow", "color": color, "coords": cmd.get("coords")}]
        elif shape == "star":
            return [{
                "action": "draw_star",
                "size": cmd.get("size", 100),
                "color": color,
                "fill": fill,
                "coords": cmd.get("coords"),
            }]
        elif shape == "polygon":
            return [{
                "action": "draw_polygon",
                "side_count": cmd.get("side_count", 6),
                "size": cmd.get("size", 100),
                "color": color,
                "coords": cmd.get("coords"),
            }]
        else:
            return [{"action": "unknown"}]

    def _parse_modify(self, cmd: Dict) -> List[Dict]:
        """解析修改命令"""
        action = cmd.get("action", "")
        result = [{"action": f"modify_{action}"}]
        if "color" in cmd:
            result[0]["color"] = cmd["color"]
        if "shape_type" in cmd:
            result[0]["shape_type"] = cmd["shape_type"]
        return result

    def _parse_operation(self, cmd: Dict) -> List[Dict]:
        """解析操作命令"""
        action = cmd.get("action", "")
        result = [{"action": f"op_{action}"}]
        if "direction" in cmd:
            result[0]["direction"] = cmd["direction"]
        if "angle" in cmd:
            result[0]["angle"] = cmd["angle"]
        if "factor" in cmd:
            result[0]["factor"] = cmd["factor"]
        if "mode" in cmd:
            result[0]["mode"] = cmd["mode"]
        if "shape_type" in cmd:
            result[0]["shape_type"] = cmd["shape_type"]
        if "color" in cmd:
            result[0]["color"] = cmd["color"]
        if "distance" in cmd:
            result[0]["distance"] = cmd["distance"]
        return result

    def _parse_delete(self, cmd: Dict) -> List[Dict]:
        """解析删除命令"""
        action = cmd.get("action", "")
        # 避免重复添加 "delete_" 前缀
        if action.startswith("delete_"):
            result = [{"action": action}]
        else:
            result = [{"action": f"delete_{action}"}]
        if "shape_type" in cmd:
            result[0]["shape_type"] = cmd["shape_type"]
        return result

    def _parse_select(self, cmd: Dict) -> List[Dict]:
        """解析选择命令"""
        result = [{"action": "select"}]
        if cmd.get("shape_type"):
            result[0]["shape_type"] = cmd["shape_type"]
        return result

    def _parse_modify_by_id(self, cmd: Dict) -> List[Dict]:
        """解析按编号修改命令"""
        result = [{"action": "modify_by_id", "shape_id": cmd.get("shape_id"), "mod_action": cmd.get("mod_action")}]
        if "color" in cmd:
            result[0]["color"] = cmd["color"]
        if "direction" in cmd:
            result[0]["direction"] = cmd["direction"]
        if "distance" in cmd:
            result[0]["distance"] = cmd["distance"]
        if "angle" in cmd:
            result[0]["angle"] = cmd["angle"]
        if "width" in cmd:
            result[0]["width"] = cmd["width"]
        if "height" in cmd:
            result[0]["height"] = cmd["height"]
        if "radius" in cmd:
            result[0]["radius"] = cmd["radius"]
        if "side" in cmd:
            result[0]["side"] = cmd["side"]
        if "size" in cmd:
            result[0]["size"] = cmd["size"]
        if "length" in cmd:
            result[0]["length"] = cmd["length"]
        return result
