"""
思维链输出模块
在控制台输出系统处理语音指令的完整思维过程
"""

import time
from typing import List


class ThoughtChain:
    """思维链追踪器"""

    def __init__(self):
        self.steps: List[str] = []

    def add_step(self, title: str, detail: str) -> None:
        """添加一个思维链步骤"""
        self.steps.append(f"[步骤 {len(self.steps) + 1}] {title}: {detail}")

    def display(self) -> None:
        """在控制台打印完整思维链"""
        print("\n" + "=" * 60)
        print(" 思维链 (Chain of Thought)")
        print("=" * 60)
        for step in self.steps:
            print(f"  {step}")
        print("=" * 60 + "\n")

    def clear(self) -> None:
        """清空思维链"""
        self.steps.clear()
