from agent_learning.core.models import Chunk


# 类职责：按自然边界与字符预算先切父块、再切子块，并保留重叠内容和原文偏移。
# 父块与子块切分集中在一个类中。
class DocumentChunker:
    # 方法功能：检查并保存子块大小、重叠长度和父块大小。
    # 输入：三个字符长度参数；输出：完成初始化的切分器。
    # 参数以字符为单位。
    def __init__(self, chunk_size=400, overlap=80, parent_size=1200):
        # 确保循环前进。
        if not 0 <= overlap < chunk_size <= parent_size:
            # 提示切分约束。
            raise ValueError("要求 0 <= overlap < chunk_size <= parent_size")
        # 保存参数。
        self.chunk_size, self.overlap, self.parent_size = chunk_size, overlap, parent_size

    # 方法功能：按预算寻找断句位置，把每块的起止位置放进列表。
    # 输入：文本、块大小和重叠长度；输出：字符区间列表。
    # 优先在句末或换行处分界。
    def _spans(self, text, size, overlap):
        # 用普通列表保存所有区间。
        spans = []
        # 从原文第一个字符开始。
        start = 0
        # 覆盖全文。
        while start < len(text):
            # 设置硬上限。
            end = min(start + size, len(text))
            # 仅在非末尾块寻找自然边界。
            if end < len(text):
                # 避免重叠大于当前块。
                lower = start + max(size // 2, overlap + 1)
                # 查找断句符。
                boundaries = [text.rfind(separator, lower, end) for separator in ["\n", "。", "！", "？", ";", "；"]]
                # 选择靠后的断点。
                boundary = max(boundaries)
                # 找不到时按字符切。
                end = boundary + 1 if boundary >= lower else end
            # 把当前区间加入列表。
            spans.append((start, end))
            # 最后一块无需继续。
            if end == len(text):
                # 结束切分。
                break
            # 保留相邻块重叠。
            start = end - overlap
        # 一次返回区间列表。
        return spans

    # 方法功能：执行两层切分，把子块位置转换回原文偏移。
    # 输入：非空文档正文；输出：父块列表和子块列表组成的二元组。
    # 返回父块和检索子块。
    def split(self, text: str) -> tuple[list[Chunk], list[Chunk]]:
        # 空白页不能参与向量化。
        if not text.strip():
            # 显式指出空内容。
            raise ValueError("文档为空；扫描 PDF 需要先做 OCR")
        # 分别收集两层块。
        parents, children = [], []
        # 父块也保留边界重叠。
        for parent_index, (start, end) in enumerate(self._spans(text, self.parent_size, self.overlap)):
            # 保存父块原文。
            parents.append(Chunk(parent_index, parent_index, text[start:end], start, end))
            # 切分父块内子块。
            for left, right in self._spans(text[start:end], self.chunk_size, self.overlap):
                # 偏移转换到原文。
                children.append(Chunk(len(children), parent_index, text[start + left:start + right], start + left, start + right))
        # 后续仅对子块生成向量。
        return parents, children
