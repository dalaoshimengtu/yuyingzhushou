"""
AI指令理解模块
将用户非标准语音指令转换为标准化绘图指令
使用本地 Ollama + Qwen3.5 LLM 理解指令，规则引擎作为回退
支持多种非标准说法和复杂指令
支持按图形编号操作
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple


class AIUnderstander:
    """AI指令理解器 - 将自然语言转为标准绘图指令"""

    # LLM 配置
    OLLAMA_URL = "http://localhost:11434/api/generate"
    OLLAMA_MODEL = "qwen3.5:0.8b"
    OLLAMA_TIMEOUT = 8  # 秒

    # LLM 系统提示词
    SYSTEM_PROMPT = """你是一个语音绘图指令解析器。将用户的语音指令解析为JSON格式。

支持的命令类型及JSON格式：
1. 绘制图形(draw): {"type":"draw","shape":"circle|rect|ellipse|triangle|line|arrow|star|polygon","radius":数字或"width":数字,"height":数字,"side":数字,"size":数字,"side_count":数字,"color":"颜色名","fill":null或颜色名,"coords":null或{"x":数字,"y":数字}}
2. 删除(delete): {"type":"delete","action":"delete_shape|delete_last","shape_type":"rect|circle|ellipse|triangle|line|arrow|star|polygon"}
3. 修改(modify): {"type":"modify","action":"change_color|fill|clear_fill|thicken|thin|duplicate|remove_top_border|remove_bottom_border|remove_left_border|remove_right_border|change_outline","color":"颜色名","shape_type":"rect|circle|..."}
4. 操作(operation): {"type":"operation","action":"move|rotate|scale|flip","direction":"up|down|left|right|center","angle":数字,"factor":数字,"mode":"horizontal|vertical","shape_type":"rect|circle|..."}
5. 撤销(undo): {"type":"undo"}
6. 重做(redo): {"type":"redo"}
7. 清空(clear): {"type":"clear"}
8. 保存(save): {"type":"save"}
9. 退出(exit): {"type":"exit"}
10. 隐藏编号(hide_labels): {"type":"hide_labels"}
11. 显示编号(show_labels): {"type":"show_labels"}
12. 按编号删除(delete_by_id): {"type":"delete_by_id","shape_id":数字}
13. 按编号修改(modify_by_id): {"type":"modify_by_id","shape_id":数字,"mod_action":"change_color|fill|move|rotate|change_property","color":"颜色名","direction":"up|down|left|right","distance":数字,"angle":数字,"radius":数字,"width":数字,"height":数字}

颜色可用：red, blue, green, yellow, black, white, orange, purple, gray, pink, brown
如果没有指定颜色，默认为black。
如果无法识别指令，返回null。
只返回JSON，不要返回其他内容。"""

    COLOR_MAP: Dict[str, str] = {
        "红": "red", "红色": "red",
        "蓝": "blue", "蓝色": "blue",
        "绿": "green", "绿色": "green",
        "黄": "yellow", "黄色": "yellow",
        "黑": "black", "黑色": "black",
        "白": "white", "白色": "white",
        "橙": "orange", "橙色": "orange",
        "紫": "purple", "紫色": "purple",
        "灰": "gray", "灰色": "gray",
        "粉": "pink", "粉色": "pink",
        "棕": "brown", "棕色": "brown",
    }

    # 图形名称映射
    SHAPE_KEYWORDS: Dict[str, List[str]] = {
        "rect": ["矩形", "长方形", "正方形", "方块", "方形", "长方块"],
        "circle": ["圆形", "圆", "球", "球形", "环", "环形"],
        "ellipse": ["椭圆", "扁圆", "椭圆形"],
        "triangle": ["三角形", "三角"],
        "line": ["线", "直线", "线条", "横线", "竖线", "斜线"],
        "arrow": ["箭头"],
    }

    MM_TO_PX = 3.78

    def _call_ollama(self, text: str) -> Optional[Dict]:
        """调用 Ollama API 解析指令"""
        prompt = f"解析以下语音指令：{text}"
        payload = json.dumps({
            "model": self.OLLAMA_MODEL,
            "prompt": prompt,
            "system": self.SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 256,
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            self.OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.OLLAMA_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        response_text = result.get("response", "").strip()
        if not response_text:
            return None

        # 尝试从响应中提取 JSON
        return self._extract_json_from_response(response_text)

    def _extract_json_from_response(self, text: str) -> Optional[Dict]:
        """从 LLM 响应中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        m = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _validate_llm_result(self, result: Optional[Dict]) -> bool:
        """验证 LLM 返回结果是否有效"""
        if result is None or not isinstance(result, dict):
            return False
        cmd_type = result.get("type")
        valid_types = {
            "draw", "delete", "modify", "operation",
            "undo", "redo", "clear", "save", "exit",
            "hide_labels", "show_labels",
            "delete_by_id", "modify_by_id",
        }
        return cmd_type in valid_types

    def understand(self, text: str) -> Optional[Dict]:
        """理解用户指令，返回标准化命令
        优先使用 Ollama LLM 解析，失败时回退到规则引擎
        """
        # 尝试 LLM 解析
        try:
            llm_result = self._call_ollama(text)
            if self._validate_llm_result(llm_result):
                return llm_result
        except (urllib.error.URLError, ConnectionRefusedError, OSError, TimeoutError, Exception):
            # Ollama 不可用，回退到规则引擎
            pass

        # 回退到规则引擎
        return self._rule_based_understand(text)

    def understand_compound(self, text: str) -> List[Dict]:
        """
        理解用户指令，支持组合命令，返回命令列表
        例如 "画一个圆和一个三角形" → [{"type":"draw","shape":"circle",...}, {"type":"draw","shape":"triangle",...}]
        """
        # 先尝试 LLM 解析
        try:
            llm_result = self._call_ollama(text)
            if self._validate_llm_result(llm_result):
                return [llm_result]
        except (urllib.error.URLError, ConnectionRefusedError, OSError, TimeoutError, Exception):
            pass

        # 回退到规则引擎
        return self._rule_based_compound_understand(text)

    def _rule_based_compound_understand(self, text: str) -> List[Dict]:
        """
        规则引擎解析组合命令
        支持: "画一个圆和一个三角形" "画一个圆 再画一个矩形" "画一个圆，再画一个三角形，再画一个矩形"
        """
        t = text.strip()
        t = self._normalize_text(t)

        # 分割组合命令
        # 使用 "和"、"再"、"然后"、"接着" 等连接词分割
        parts = self._split_compound(t)

        if len(parts) <= 1:
            # 不是组合命令，返回单个结果
            result = self._rule_based_understand(t)
            return [result] if result else []

        results = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            cmd = self._rule_based_understand(part)
            if cmd:
                results.append(cmd)

        return results

    def _split_compound(self, text: str) -> List[str]:
        """
        分割组合命令文本
        支持: "画一个圆和一个三角形" → ["画一个圆", "一个三角形"]
              "画一个圆，再画一个矩形" → ["画一个圆", "画一个矩形"]
              "画一个圆和三角形以及长方形" → ["画一个圆", "三角形", "长方形"]
        """
        # 先按常见连接词分割: "和"、"再"、"然后"、"接着"、"以及"、"，再"、"。再"
        import re

        # 标准化: 去掉句号
        text = text.replace('。', '，').replace('.', '，')

        # 按连接词分割
        split_pattern = r'[，,]\s*(?:再|然后|接着)\s*|和\s*|以及\s*|再\s*|然后\s*|接着\s*'
        parts = re.split(split_pattern, text)

        # 清理空字符串
        parts = [p.strip() for p in parts if p.strip()]

        # 如果分割后每个部分都不包含绘制关键词，说明分割过度，返回原文本
        has_draw = lambda p: self._match_any(p, ["画", "绘制", "圆", "矩形", "长方", "正方", "方块", "三角", "椭圆", "线", "箭头", "星", "多边形"])
        if parts and not any(has_draw(p) for p in parts):
            return [text]

        # 为缺少动词的部分补上"画"
        fixed_parts = []
        for p in parts:
            if has_draw(p) and not self._match_any(p, ["画", "绘制"]):
                # 缺少动词，补上
                fixed_parts.append("画" + p)
            else:
                fixed_parts.append(p)

        return fixed_parts if fixed_parts else [text]

    def _rule_based_understand(self, text: str) -> Optional[Dict]:
        """规则引擎解析（回退方法）"""
        t = text.strip()
        t = self._normalize_text(t)

        # ===== 0. 编号操作优先级最高 =====
        id_cmd = self._try_parse_by_id(t)
        if id_cmd:
            return id_cmd

        # ===== 1. 系统控制命令 =====
        if self._match_any(t, ["退出", "结束", "退出程序", "关闭程序", "关掉", "关闭"]):
            return {"type": "exit"}
        if self._match_any(t, ["保存", "另存为", "存一下", "保存图片"]):
            return {"type": "save"}

        # ===== 2. 撤销/清空/重做 =====
        if self._match_any(t, ["撤销", "撤回", "后悔", "取消上一步", "返回上一步"]):
            return {"type": "undo"}
        if self._match_any(t, ["重做", "恢复"]):
            return {"type": "redo"}
        if self._match_any(t, ["清空", "清除全部", "全部删除", "清空画布", "清屏"]):
            return {"type": "clear"}

        # ===== 2b. 编号标签控制 =====
        if self._match_any(t, ["隐藏编号", "隐藏标签", "去掉编号", "删掉编号", "删除编号", "去掉标签", "清除编号", "清除标签"]):
            return {"type": "hide_labels"}
        if self._match_any(t, ["显示编号", "显示标签", "打开编号", "展示编号", "展示标签"]):
            return {"type": "show_labels"}

        # ===== 3. 删除指定图形（排除边框去除操作） =====
        delete = self._try_parse_delete(t)
        if delete:
            # 二次检查：如果包含边框关键词，跳过删除解析
            if not self._match_any(t, ["上边", "下边", "左边", "右边", "上框", "下框", "左框", "右框", "顶部", "底部", "左侧", "右侧"]):
                return delete

        # ===== 3b. 修改线段长度指令（长N/长度N/线长N）
        # 放在绘制之前，避免"线长N"被误识别为绘制命令
        length_cmd = self._try_parse_modify_length(t)
        if length_cmd:
            return length_cmd

        # ===== 4. 绘制基础图形 =====
        shape = self._try_parse_draw(t)
        if shape:
            return shape

        # ===== 5. 图形修改指令 =====
        modify = self._try_parse_modify(t)
        if modify:
            return modify

        # ===== 6. 图形操作 (移动/旋转/缩放) =====
        op = self._try_parse_operation(t)
        if op:
            return op

        # ===== 7. 选择图形 =====
        select = self._try_parse_select(t)
        if select:
            return select

        return None

    # ---- 工具方法 ----

    # 中文数字到阿拉伯数字映射
    CHINESE_NUM_MAP: Dict[str, str] = {
        "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
        "两": "2", "十": "10", "百": "100", "千": "1000", "万": "10000",
    }

    # 语音识别常见同音词纠正
    HOMOPHONE_CORRECT: Dict[str, str] = {
        "人": "圆", "仁": "圆", "忍": "圆", "认": "圆",
        "长方形的": "长方形",
        "商": "上", "尚": "上", "伤": "上",
        "下变": "下边", "下遍": "下边",
        "上变": "上边", "上遍": "上边",
        "做变": "左边", "做遍": "左边",
        "右变": "右边", "右遍": "右边",
        "向做": "向左", "向右": "向右",
        "向有": "向右", "想右": "向右",
        "向坐": "向左", "想左": "向左",
        "项上": "向上", "想上": "向上",
        "项下": "向下", "想下": "向下",
        "项左": "向左", "想左": "向左",
        "项右": "向右", "想右": "向右",
        "颜色": "颜色", "彦色": "颜色",
        "填色": "填色", "田色": "填色",
        "半斤": "半径", "半经": "半径", "半镜": "半径",
        "直径": "直径", "质径": "直径",
        "矩形": "矩形", "巨形": "矩形", "具形": "矩形", "菊形": "矩形",
        "三角形": "三角形", "三角行": "三角形", "三脚形": "三角形",
        "椭圆形": "椭圆形", "驼圆形": "椭圆形",
        "多边形": "多边形", "多边形": "多边形",
        "五角星": "五角星", "五脚星": "五角星", "五角心": "五角星",
        "箭头": "箭头", "见头": "箭头", "剑头": "箭头",
        "移动": "移动", "一动": "移动",
        "旋转": "旋转", "选转": "旋转", "悬转": "旋转",
        "缩放": "缩放", "所放": "缩放",
        "放大": "放大", "方大": "放大",
        "缩小": "缩小", "索小": "缩小",
        "翻转": "翻转", "翻砖": "翻转",
        "镜像": "镜像", "境像": "镜像", "镜象": "镜像",
        "复制": "复制", "复制": "复制", "复职": "复制",
        "加粗": "加粗", "家粗": "加粗",
        "撤销": "撤销", "撤销": "撤销", "撤销": "撤销",
        "保存": "保存", "宝存": "保存", "宝纯": "保存",
        "清空": "清空", "清控": "清空",
        "隐藏": "隐藏", "引藏": "隐藏",
        "显示": "显示", "显式": "显示",
        "绘制": "绘制", "慧制": "绘制", "惠制": "绘制",
        "画一个": "画一个", "化一个": "画一个",
    }

    def _normalize_text(self, text: str) -> str:
        """
        规范化语音识别文本：
        1. 纠正同音词
        2. 中文数字转阿拉伯数字
        3. 清理多余空格
        """
        result = text

        # 1. 同音词纠正（按长度降序，优先匹配长词）
        for wrong, right in sorted(self.HOMOPHONE_CORRECT.items(), key=lambda x: -len(x[0])):
            result = result.replace(wrong, right)

        # 2. 中文数字转阿拉伯数字（在清理空格之前处理，支持空格分隔的中文数字）
        result = self._chinese_num_to_arabic(result)

        # 3. 清理多余空格
        result = re.sub(r'\s+', ' ', result).strip()

        return result

    def _chinese_num_to_arabic(self, text: str) -> str:
        """
        将文本中与数值相关的中文数字转换为阿拉伯数字
        支持空格分隔: "半径 一 百" -> "半径100"
        例如: "半径五十" -> "半径50"
              "半径为两百" -> "半径200"
              "宽为八十" -> "宽80"
        """
        # 匹配: 尺寸关键词 + 可选连接词(为/是/的/了) + 可选空格 + 中文数字（允许字符间有空格）
        # 中文数字模式：每个数字字符之间可以有任意空格
        chinese_digit = r'[零一二三四五六七八九十百千万两]'
        chinese_num_pattern = f'(?:{chinese_digit}\\s*)*{chinese_digit}'
        full_pattern = rf'(半径|直径|宽|高|边长|大小|距离|移动|旋转|角度|坐标|位置|长|短)(?:\s*[为是的了]\s*)?({chinese_num_pattern})'

        def replace_match(m):
            keyword = m.group(1)
            chinese_num = m.group(2)
            # 移除中文数字之间的空格
            chinese_num_clean = chinese_num.replace(' ', '')
            arabic = self._convert_chinese_num(chinese_num_clean)
            return keyword + arabic

        return re.sub(full_pattern, replace_match, text)

    def _convert_chinese_num(self, chinese_num: str) -> str:
        """将中文数字字符串转为阿拉伯数字"""
        if not chinese_num:
            return ""

        # 简单情况：单个数字
        if len(chinese_num) == 1 and chinese_num in self.CHINESE_NUM_MAP:
            mapped = self.CHINESE_NUM_MAP[chinese_num]
            # "十" "百" "千" "万" 本身是单位
            if mapped in ("10", "100", "1000", "10000"):
                return mapped
            return mapped

        # 组合数字：如 "五十" "三十二" "一百二十"
        result = 0
        temp = 0
        for char in chinese_num:
            if char in self.CHINESE_NUM_MAP:
                val = int(self.CHINESE_NUM_MAP[char])
                if val >= 10:  # 单位（十、百、千、万）
                    if temp == 0:
                        temp = 1
                    result += temp * val
                    temp = 0
                else:
                    temp = temp * 10 + val if temp > 0 else val
            else:
                temp = 0

        result += temp
        return str(result)

    def _match_any(self, text: str, keywords: List[str]) -> bool:
        return any(k in text for k in keywords)

    def _extract_color(self, text: str) -> str:
        for keyword, color in self.COLOR_MAP.items():
            if keyword in text:
                return color
        return "black"

    def _extract_numbers(self, text: str) -> List[float]:
        matches = re.findall(r'(\d+(?:\.\d+)?)', text)
        return [float(m) for m in matches]

    def _extract_shape_id(self, text: str) -> Optional[int]:
        """从文本中提取图形编号，支持: "图形3" / "图形一" / "第3个图形" / "3号图形" / "#3" """
        # 先尝试匹配阿拉伯数字
        m = re.search(r'图形\s*(\d+)', text)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*号', text)
        if m:
            return int(m.group(1))
        m = re.search(r'#(\d+)', text)
        if m:
            return int(m.group(1))
        m = re.search(r'第\s*(\d+)\s*个', text)
        if m:
            return int(m.group(1))
        # 匹配中文数字：图形一、图形二 等
        m = re.search(r'图形\s*([一二两三四五六七八九零])\s*(?:号)?', text)
        if m:
            ch = m.group(1)
            return int(self.CHINESE_NUM_MAP.get(ch, '0'))
        return None

    def _extract_coords(self, text: str) -> Optional[Tuple[float, float]]:
        """从文本中提取坐标，支持格式: "坐标50,100" / "位置(50,100)" / "50,100" / "x=50,y=100" / "50 100" """
        m = re.search(r'坐标[\s:]*(\d+(?:\.\d+)?)\s*[,，\s]\s*(\d+(?:\.\d+)?)', text)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        m = re.search(r'位置[\s:]*(?:\()?\s*(\d+(?:\.\d+)?)\s*[,，\s]\s*(\d+(?:\.\d+)?)\s*(?:\))?', text)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        m = re.search(r'x[\s:=]*(\d+(?:\.\d+)?)\s*[,，\s]*y[\s:=]*(\d+(?:\.\d+)?)', text)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        return None

    def _mm_to_px(self, mm: float) -> float:
        return mm * self.MM_TO_PX

    def _detect_shape_type(self, text: str) -> Optional[str]:
        """从文本中检测提到的图形类型"""
        for shape_type, keywords in self.SHAPE_KEYWORDS.items():
            if self._match_any(text, keywords):
                return shape_type
        return None

    def _detect_fill_color(self, text: str) -> Optional[str]:
        """检测是否有填充指令"""
        if self._match_any(text, ["填充", "填色", "上色", "涂上"]):
            return self._extract_color(text)
        return None

    # ---- 解析器 ----

    def _try_parse_by_id(self, text: str) -> Optional[Dict]:
        """
        尝试解析按编号操作的指令
        支持: "删除图形3", "图形3改为红色", "把3号图形向右移动50", "图形3旋转90度"
        支持属性修改: "把图形1半径改为100", "图形2宽改为80高改为50"
        """
        shape_id = self._extract_shape_id(text)
        if not shape_id:
            return None

        # 删除
        if self._match_any(text, ["删除", "删掉", "删去", "去掉", "移除"]):
            return {"type": "delete_by_id", "shape_id": shape_id}

        # 属性修改（半径、宽、高、边长、大小等）
        prop_cmd = self._try_parse_property_by_id(text, shape_id)
        if prop_cmd:
            return prop_cmd

        # 变色
        if self._match_any(text, ["变色", "改为", "变成", "换成", "改成", "颜色变成"]):
            return {"type": "modify_by_id", "shape_id": shape_id, "mod_action": "change_color", "color": self._extract_color(text)}

        # 填充
        if self._match_any(text, ["填充", "填色", "上色", "涂上"]):
            return {"type": "modify_by_id", "shape_id": shape_id, "mod_action": "fill", "color": self._extract_color(text)}

        # 移动
        if self._match_any(text, ["移动", "移到", "挪"]):
            direction = "right"
            if self._match_any(text, ["上", "上方", "上面"]):
                direction = "up"
            elif self._match_any(text, ["下", "下方", "下面"]):
                direction = "down"
            elif self._match_any(text, ["左", "左侧"]):
                direction = "left"
            elif self._match_any(text, ["右", "右侧"]):
                direction = "right"
            nums = self._extract_numbers(text)
            # 过滤掉 shape_id 本身，避免取到图形编号作为距离
            nums = [n for n in nums if int(n) != shape_id]
            distance = nums[0] if nums else 30
            return {"type": "modify_by_id", "shape_id": shape_id, "mod_action": "move", "direction": direction, "distance": distance}

        # 旋转
        if self._match_any(text, ["旋转", "转动"]):
            nums = self._extract_numbers(text)
            angle = nums[0] if nums else 90
            return {"type": "modify_by_id", "shape_id": shape_id, "mod_action": "rotate", "angle": angle}

        # 缩放（放大/缩小）
        if self._match_any(text, ["缩小", "放大", "缩放"]):
            factor = 0.5
            if self._match_any(text, ["放大"]):
                factor = 2.0
            # 尝试提取比例，如"缩小百分之五十" → 0.5
            m = re.search(r'百分之\s*(\d+\.?\d*)', text)
            if m:
                factor = float(m.group(1)) / 100.0
            else:
                m = re.search(r'(\d+\.?\d*)\s*[%倍]', text)
                if m:
                    val = float(m.group(1))
                    factor = val if '倍' in text else val / 100.0
            return {"type": "modify_by_id", "shape_id": shape_id, "mod_action": "scale", "factor": factor}

        return None

    def _try_parse_property_by_id(self, text: str, shape_id: int) -> Optional[Dict]:
        """
        尝试解析按编号修改属性的指令
        支持: "把图形1半径改为100", "图形2宽改为80", "3号高改为60", "图形1改为宽100高50"
        """
        # 检测是否有属性修改关键词
        if not self._match_any(text, ["半径", "直径", "宽", "高", "边长", "大小", "长度", "改为", "改成", "变成", "换成"]):
            return None

        # 提取数值（排除已识别的 shape_id 数字）
        all_nums = self._extract_numbers(text)
        # 过滤掉 shape_id 本身
        prop_values = [n for n in all_nums if int(n) != shape_id]

        if not prop_values:
            return None

        result = {"type": "modify_by_id", "shape_id": shape_id, "mod_action": "change_property"}

        # 检测多个属性修改
        has_width = self._match_any(text, ["宽"])
        has_height = self._match_any(text, ["高"])
        has_radius = self._match_any(text, ["半径", "直径"])
        has_side = self._match_any(text, ["边长"])
        has_size = self._match_any(text, ["大小"])
        has_length = self._match_any(text, ["长度", "长"])

        if has_width and has_height and len(prop_values) >= 2:
            result["width"] = prop_values[0]
            result["height"] = prop_values[1]
            return result
        elif has_width and not has_height:
            result["width"] = prop_values[0]
            return result
        elif has_height and not has_width:
            result["height"] = prop_values[0]
            return result
        elif has_radius or self._match_any(text, ["直径"]):
            result["radius"] = prop_values[0]
            return result
        elif has_side:
            result["side"] = prop_values[0]
            return result
        elif has_size:
            result["size"] = prop_values[0]
            return result
        elif has_length:
            result["length"] = prop_values[0]
            return result

        return None

    def _try_parse_delete(self, text: str) -> Optional[Dict]:
        """
        尝试解析删除命令
        支持: "删除长方形", "去掉画布上的圆形", "把矩形删掉", "删掉最后一个方块"
        """
        has_delete = self._match_any(text, [
            "删除", "删掉", "删去", "去掉", "移除", "不要",
            "干掉", "抹掉", "消除", "清掉", "拿掉", "丢掉",
            "删", "除", "去"
        ])
        if not has_delete:
            return None

        shape_type = self._detect_shape_type(text)
        if shape_type is None:
            return {"type": "delete", "action": "delete_last"}

        return {"type": "delete", "action": "delete_shape", "shape_type": shape_type}

    def _try_parse_draw(self, text: str) -> Optional[Dict]:
        """尝试解析绘制命令"""
        # 如果文本包含操作关键词，不解析为绘制
        if self._match_any(text, ["移动", "移到", "挪", "旋转", "转动", "翻转", "翻", "缩放", "放大", "缩小", "镜像", "对称"]):
            return None

        color = self._extract_color(text)
        fill_color = self._detect_fill_color(text)
        nums = self._extract_numbers(text)
        coords = self._extract_coords(text)
        has_pixel = self._match_any(text, ["像素", "px", "PX"])

        # 绘制圆形
        if self._match_any(text, ["圆", "球", "环"]):
            is_ellipse = self._match_any(text, ["椭圆", "扁圆", "椭圆"])
            has_circle_word = self._match_any(text, ["圆形", "圆球", "圆圈"])
            has_delete_word = self._match_any(text, ["删除", "删掉", "去掉"])

            if has_delete_word:
                return None

            if is_ellipse and len(nums) >= 2:
                rx = nums[0] if has_pixel else self._mm_to_px(nums[0])
                ry = nums[1] if has_pixel else self._mm_to_px(nums[1])
                return {"type": "draw", "shape": "ellipse", "rx": rx, "ry": ry, "color": color, "fill": fill_color, "coords": coords}
            elif is_ellipse and len(nums) == 1:
                radius = nums[0] if has_pixel else self._mm_to_px(nums[0])
                return {"type": "draw", "shape": "ellipse", "rx": radius, "ry": radius * 0.6, "color": color, "fill": fill_color, "coords": coords}

            if not is_ellipse or has_circle_word:
                if nums:
                    radius = nums[0] if has_pixel else self._mm_to_px(nums[0])
                else:
                    radius = self._mm_to_px(50)  # 默认 50mm
                return {"type": "draw", "shape": "circle", "radius": radius, "color": color, "fill": fill_color, "coords": coords}

        # 绘制矩形/长方形/正方形
        if self._match_any(text, ["矩形", "长方形", "正方形", "方块", "方形", "长方块"]):
            has_delete = self._match_any(text, ["删除", "删掉", "去掉", "移除"])
            if has_delete:
                return None

            is_square = self._match_any(text, ["正方形", "方块"]) and not self._match_any(text, ["长方形", "矩形"])
            if is_square and nums:
                side = nums[0] if has_pixel else self._mm_to_px(nums[0])
                return {"type": "draw", "shape": "rect", "width": side, "height": side, "color": color, "fill": fill_color, "coords": coords}
            elif len(nums) >= 2 and coords is None:
                w = nums[0] if has_pixel else self._mm_to_px(nums[0])
                h = nums[1] if has_pixel else self._mm_to_px(nums[1])
            elif coords:
                w = nums[0] if has_pixel and nums else self._mm_to_px(100)
                h = nums[0] if has_pixel and nums else self._mm_to_px(60)
            else:
                w = self._mm_to_px(100)
                h = self._mm_to_px(60)
            return {"type": "draw", "shape": "rect", "width": w, "height": h, "color": color, "fill": fill_color, "coords": coords}

        # 绘制线/直线
        if self._match_any(text, ["线", "直线", "线条", "划线", "画线"]):
            has_delete = self._match_any(text, ["删除", "删掉", "去掉", "移除"])
            if has_delete:
                return None
            return {"type": "draw", "shape": "line", "params": nums, "color": color, "coords": coords}

        # 绘制三角形
        if self._match_any(text, ["三角形", "三角"]):
            has_delete = self._match_any(text, ["删除", "删掉", "去掉", "移除"])
            if has_delete:
                return None
            side = nums[0] if has_pixel else self._mm_to_px(nums[0] if nums else 100)
            return {"type": "draw", "shape": "triangle", "side": side, "color": color, "fill": fill_color, "coords": coords}

        # 绘制箭头
        if self._match_any(text, ["箭头"]):
            has_delete = self._match_any(text, ["删除", "删掉", "去掉", "移除"])
            if has_delete:
                return None
            return {"type": "draw", "shape": "arrow", "color": color, "coords": coords}

        # 绘制多边形/星形
        if self._match_any(text, ["多边形", "五角星", "星星"]):
            has_delete = self._match_any(text, ["删除", "删掉", "去掉", "移除"])
            if has_delete:
                return None
            side = nums[0] if has_pixel else self._mm_to_px(nums[0] if nums else 100)
            if self._match_any(text, ["五角星", "星星"]):
                return {"type": "draw", "shape": "star", "size": side, "color": color, "fill": fill_color, "coords": coords}
            else:
                return {"type": "draw", "shape": "polygon", "side_count": int(nums[0]) if nums else 6, "size": side, "color": color, "coords": coords}

        return None

    def _try_parse_modify_length(self, text: str) -> Optional[Dict]:
        """
        尝试解析修改线段长度的指令
        如: "长300", "长度300", "线长300", "线段长度300"
        返回 modify_by_id 命令, shape_id=-1 表示最后一个图形
        """
        nums = self._extract_numbers(text)
        if not nums:
            return None

        # 包含"画"/"绘制"/"添加"等绘制关键词时，说明是画图而非修改，交给绘制解析器
        draw_keywords = ["画", "绘制", "添加", "增加", "新建", "生成", "创建"]
        if self._match_any(text, draw_keywords):
            return None

        # 匹配明确的长度关键词 + 数字: "长度300", "线长300", "线段长度300" 等
        if self._match_any(text, ["线段长度", "线段长", "线长度", "线长", "长度"]):
            return {"type": "modify_by_id", "shape_id": -1, "mod_action": "change_property", "length": nums[0]}

        # 匹配 "长" + 数字 (如 "长300")
        # 排除包含"长方形"、"矩形"、"三角"等形状关键词的情况
        if re.search(r'长\s*\d+', text):
            if not self._match_any(text, ["方形", "矩形", "三角", "圆"]):
                return {"type": "modify_by_id", "shape_id": -1, "mod_action": "change_property", "length": nums[0]}

        return None

    def _try_parse_modify(self, text: str) -> Optional[Dict]:
        """尝试解析图形修改命令"""
        shape_type = self._detect_shape_type(text)
        color = self._extract_color(text)

        # 去除边框操作
        border_remove_keywords = ["去除", "去掉", "移除", "删除边", "不要", "干掉", "删掉边"]
        if self._match_any(text, border_remove_keywords):
            if self._match_any(text, ["上边", "上框", "顶部", "上面"]):
                return {"type": "modify", "action": "remove_top_border", "shape_type": shape_type}
            if self._match_any(text, ["下边", "下框", "底部", "下面"]):
                return {"type": "modify", "action": "remove_bottom_border", "shape_type": shape_type}
            if self._match_any(text, ["左边", "左框", "左侧"]):
                return {"type": "modify", "action": "remove_left_border", "shape_type": shape_type}
            if self._match_any(text, ["右边", "右框", "右侧"]):
                return {"type": "modify", "action": "remove_right_border", "shape_type": shape_type}
            return None

        # 变色操作
        if self._match_any(text, ["变色", "改为", "变成", "换成", "改成", "颜色变成"]):
            return {"type": "modify", "action": "change_color", "color": color, "shape_type": shape_type}

        # 描边/轮廓颜色
        if self._match_any(text, ["描边", "轮廓", "边框颜色"]):
            return {"type": "modify", "action": "change_outline", "color": color, "shape_type": shape_type}

        # 填充操作
        if self._match_any(text, ["填充", "填色", "上色", "涂上", "填满"]):
            return {"type": "modify", "action": "fill", "color": color, "shape_type": shape_type}

        # 取消填充/透明
        if self._match_any(text, ["取消填充", "透明", "去掉填充", "清除填充", "无填充"]):
            return {"type": "modify", "action": "clear_fill", "shape_type": shape_type}

        # 加粗/变细线条
        if self._match_any(text, ["加粗", "变粗", "粗一点", "粗一些"]):
            return {"type": "modify", "action": "thicken", "shape_type": shape_type}
        if self._match_any(text, ["变细", "细一点", "细一些", "减细"]):
            return {"type": "modify", "action": "thin", "shape_type": shape_type}

        # 复制图形
        if self._match_any(text, ["复制", "拷贝", "clone"]):
            return {"type": "modify", "action": "duplicate", "shape_type": shape_type}

        return None

    def _try_parse_operation(self, text: str) -> Optional[Dict]:
        """尝试解析图形操作命令"""
        shape_type = self._detect_shape_type(text)
        color = self._extract_color(text)
        nums = self._extract_numbers(text)

        # 移动操作
        if self._match_any(text, ["移动", "移到", "挪", "移到", "挪到"]):
            has_distance = any(k in text for k in ["移动.*像素", "移动.*px", "移.*像素", "移.*px", "移动.*毫米", "移.*毫米"])
            distance = None
            if has_distance:
                distance = nums[0] if nums else None

            direction = None
            if self._match_any(text, ["上", "上方", "上面", "往上"]):
                direction = "up"
            elif self._match_any(text, ["下", "下方", "下面", "往下"]):
                direction = "down"
            elif self._match_any(text, ["左", "左侧", "往左"]):
                direction = "left"
            elif self._match_any(text, ["右", "右侧", "往右"]):
                direction = "right"
            elif self._match_any(text, ["中间", "中心", "正中间", "中央"]):
                direction = "center"

            if direction:
                result = {"type": "operation", "action": "move", "direction": direction, "shape_type": shape_type}
                if color != "black":
                    result["color"] = color
                if distance:
                    result["distance"] = distance
                return result

        # 旋转操作
        if self._match_any(text, ["旋转", "转动", "转一下", "旋转一下"]):
            angle = nums[0] if nums else 90
            return {"type": "operation", "action": "rotate", "angle": angle, "shape_type": shape_type, "color": color}

        # 翻转操作
        if self._match_any(text, ["翻转", "翻"]):
            if self._match_any(text, ["水平", "左右", "横向"]):
                return {"type": "operation", "action": "flip", "mode": "horizontal", "shape_type": shape_type, "color": color}
            elif self._match_any(text, ["垂直", "上下", "纵向"]):
                return {"type": "operation", "action": "flip", "mode": "vertical", "shape_type": shape_type, "color": color}
            return {"type": "operation", "action": "flip", "mode": "horizontal", "shape_type": shape_type, "color": color}

        # 缩放操作
        if self._match_any(text, ["放大", "缩小", "缩放"]):
            if self._match_any(text, ["放大", "大", "放大"]):
                factor = nums[0] / 100.0 if nums and nums[0] > 1 else (nums[0] if nums else 1.5)
                return {"type": "operation", "action": "scale", "factor": factor, "shape_type": shape_type, "color": color}
            elif self._match_any(text, ["缩小", "小", "缩小"]):
                factor = nums[0] / 100.0 if nums and nums[0] > 1 else (nums[0] if nums else 0.5)
                return {"type": "operation", "action": "scale", "factor": factor, "shape_type": shape_type, "color": color}

        # 镜像
        if self._match_any(text, ["镜像", "对称"]):
            return {"type": "operation", "action": "mirror", "shape_type": shape_type, "color": color}

        return None

    def _try_parse_select(self, text: str) -> Optional[Dict]:
        """尝试解析选择命令"""
        if self._match_any(text, ["选中", "选择", "选取", "选定"]):
            shape_type = self._detect_shape_type(text)
            return {"type": "select", "shape_type": shape_type}
        return None
