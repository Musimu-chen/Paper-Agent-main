"""报告组装 Chain - 直接拼接章节内容，保存为 Markdown 文件"""

import os
import logging
from datetime import datetime
from pathlib import Path

from paper_agent.models import WritingResult, BackToFrontData, StepName

logger = logging.getLogger(__name__)


class ReportChain:
    """报告组装链：直接拼接章节内容并保存为 Markdown 文件"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(__file__).parent.parent.parent / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        writing_result: WritingResult,
        state_queue=None,
    ) -> str:
        """
        组装报告：直接拼接章节内容，保存为 Markdown 文件

        Args:
            writing_result: 写作结果
            state_queue: SSE 状态队列
        """
        if state_queue:
            await state_queue.put(BackToFrontData(step="reporting", state="initializing", data=None))

        try:
            # 直接拼接章节内容（不再调用 LLM 摘要）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_lines = [
                "# 论文调研报告",
                "",
                f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "---",
                "",
            ]

            for s in writing_result.sections:
                if s.content:
                    report_lines.append(s.content)
                else:
                    report_lines.append(f"## {s.title}\n\n（无内容）")
                report_lines.append("")
                report_lines.append("---")
                report_lines.append("")

            full_report = "\n".join(report_lines)

            # 保存到文件
            filename = f"report_{timestamp}.md"
            filepath = self.output_dir / filename
            filepath.write_text(full_report, encoding="utf-8")
            logger.info(f"报告已保存到: {filepath}")

            # 通知前端
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="reporting", state="generating",
                    data=f"报告已保存到 output/{filename}",
                ))
                await state_queue.put(BackToFrontData(step="reporting", state="completed", data=None))

            return full_report

        except Exception as e:
            err_msg = f"报告生成失败: {str(e)}"
            logger.error(err_msg)
            if state_queue:
                await state_queue.put(BackToFrontData(
                    step="reporting", state="error", data=err_msg,
                ))
            # 回退：直接拼接章节
            fallback = "# 调研报告\n\n"
            for s in writing_result.sections:
                fallback += f"## {s.title}\n\n{s.content or '（无内容）'}\n\n"
            return fallback
