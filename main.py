"""
语音控制绘图工具 - 主入口
通过 main.py 启动运行
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_drawing.voice_recognizer import VoiceRecognizer
from voice_drawing.ai_understanding import AIUnderstander
from voice_drawing.command_parser import CommandParser
from voice_drawing.thought_chain import ThoughtChain
from voice_drawing.drawing_engine import DrawingEngine


class VoiceDrawingApp:
    """语音绘图应用主类"""

    def __init__(self):
        self.voice_recognizer = VoiceRecognizer(status_callback=self._on_voice_status)
        self.ai_understander = AIUnderstander()
        self.command_parser = CommandParser()
        self.thought_chain = ThoughtChain()
        self.drawing_engine = DrawingEngine()

    def _on_voice_status(self, msg: str) -> None:
        """语音识别状态更新到窗口标题栏"""
        if hasattr(self.drawing_engine, "root") and self.drawing_engine.root:
            self.drawing_engine.root.title(f"语音控制绘图工具 - {msg}")

    def _restore_title(self) -> None:
        """恢复默认窗口标题"""
        if hasattr(self.drawing_engine, "root") and self.drawing_engine.root:
            self.drawing_engine.root.title("语音控制绘图工具")

    def process_voice(self, text: str) -> None:
        """
        处理一条语音指令
        流程: 语音文本 -> AI理解 -> 命令解析 -> 绘图执行
        """
        self.thought_chain.clear()

        # 步骤1: 语音识别
        self.thought_chain.add_step("语音识别", f"接收到语音: '{text}'")

        # 步骤2: AI理解 - 使用组合命令解析
        commands = self.ai_understander.understand_compound(text)
        if not commands:
            self.thought_chain.add_step("AI理解", f"无法理解指令 '{text}'，请换一种说法")
            self.thought_chain.display()
            self.drawing_engine.set_status(f"无法理解: {text}")
            return

        if len(commands) > 1:
            self.thought_chain.add_step("AI理解", f"识别为组合命令，共 {len(commands)} 个指令: {commands}")
        else:
            self.thought_chain.add_step("AI理解", f"标准化指令: {commands[0]}")

        # 步骤3 & 4: 依次解析并执行每个命令
        for i, cmd in enumerate(commands):
            if len(commands) > 1:
                self.thought_chain.add_step(f"命令 {i+1}/{len(commands)}", f"解析: {cmd}")

            actions = self.command_parser.parse(cmd)
            for action in actions:
                self.drawing_engine.execute_action(action)
                if len(commands) <= 1:
                    self.thought_chain.add_step("执行结果", f"完成: {action}")

        # 显示思维链
        self.thought_chain.display()

    def run(self) -> None:
        """启动应用"""
        print("=" * 60)
        print("  语音控制绘图工具")
        print("  请通过语音指令进行绘图操作")
        print("  输入 'q' 或 '退出' 可以退出程序")
        print("=" * 60)

        # 初始化绘图窗口
        self.drawing_engine.init_window()

        print("FunASR 模型已加载，开始监听语音...")
        self.drawing_engine.set_status("就绪 - 请说出您的指令")

        # 主循环: 持续监听语音
        running = True
        while running:
            # 先处理UI事件
            try:
                self.drawing_engine.update()
            except Exception:
                break

            # 监听语音
            text = self.voice_recognizer.listen()

            if text is None:
                continue

            if text.strip().lower() in ("q", "退出", "结束", "退出程序", "关闭"):
                self.drawing_engine.set_status("正在退出...")
                running = False
                continue

            self.process_voice(text)
            self._restore_title()

        # 关闭窗口
        if self.drawing_engine.root:
            self.drawing_engine.root.quit()
            self.drawing_engine.root.destroy()


if __name__ == "__main__":
    app = VoiceDrawingApp()
    app.run()
