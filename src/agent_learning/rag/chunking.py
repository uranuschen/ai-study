from agent_learning.core.models import Chunk


# 类职责：按段落、句子和结构化字段边界切父子块，保留安全重叠与原文偏移。
# 父块与子块切分集中在一个类中。
class DocumentChunker:
    # 切分逻辑变化时同步更新入库指纹，避免把旧向量当作新块。
    algorithm_version = "structure-v2"

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

    # 方法功能：识别同一条结构化记录，避免把一行的相关字段拆开。
    # 输入：一行正文；输出：字段组名称或 None。
    def _field_group(self, line):
        # 普通文本没有字段名和值的分隔符。
        if ":" not in line:
            # 不把文件名或缩写当作结构化字段。
            return None
        # 字段路径位于冒号之前。
        path = line.partition(":")[0].strip()
        # 只有带层级的字段路径需要分组。
        if "." not in path or " " in path:
            # 普通句子和标题不属于结构化字段组。
            return None
        # 保留前两级，数组下标用于区分不同行。
        return ".".join(path.split(".")[:2])

    # 方法功能：找出可以安全结束或重新开始一个块的位置。
    # 输入：原文；输出：行或字段组边界，以及句子边界。
    def _boundaries(self, text):
        # 分别保存结构边界和句子边界。
        structural, sentences = set(), set()
        # 保留换行，位置才能对应原文。
        lines = text.splitlines(keepends=True)
        # 记录当前原文位置和代码块状态。
        position, in_code = 0, False
        # 逐行识别标题、字段组与代码围栏。
        for index, line in enumerate(lines):
            # 当前行结束位置。
            line_start = position
            # 累加真实字符长度。
            position += len(line)
            # 读取当前行和下一行。
            current = line.strip()
            # 最后一行没有后继。
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            # 识别 Markdown 代码围栏。
            is_fence = current.startswith(("```", "~~~"))
            # 围栏内的换行不能当作普通段落边界。
            if is_fence:
                # 开始或结束代码块。
                in_code = not in_code
                # 结束代码块后才允许切分。
                if not in_code:
                    # 完整代码块作为一个结构单位。
                    structural.add(position)
                # 围栏行不参与普通断句。
                continue
            # 代码块内部保持连续。
            if in_code:
                # 下一行继续读取代码块。
                continue
            # 当前结构化字段归属的记录。
            group = self._field_group(current)
            # 普通段落中可以在完整句末切分。
            if group is None and not current.startswith("|"):
                # 查找句号、问号和分号。
                for offset, char in enumerate(line):
                    # 标点后的原文位置可作为句子边界。
                    if char in "。！？；!?;":
                        # 保留原文中的绝对字符位置。
                        sentences.add(line_start + offset + 1)
            # 同一条 JSON 记录的后续字段必须留在一起。
            if group is not None and group == self._field_group(next_line.strip()):
                # 暂不在字段组中间切分。
                continue
            # Markdown 标题应尽量和后续正文放在一起。
            if current.startswith("#") and next_line.strip():
                # 不在标题后立即切分。
                continue
            # 缩进的下一行属于当前列表项或段落。
            if current and next_line.startswith((" ", "\t")) and next_line.strip():
                # 不拆开列表项及其续行。
                continue
            # 行、段落或完整字段组结束。
            structural.add(position)
        # 文本末尾始终是合法边界。
        structural.add(len(text))
        # 排序后供切分与重叠复用。
        return sorted(structural), sorted(sentences)

    # 方法功能：优先在结构边界切块，并从完整句或字段组开始重叠。
    # 输入：文本、块大小和重叠长度；输出：原文字符区间列表。
    def _spans(self, text, size, overlap):
        # 用普通列表保存所有区间。
        spans = []
        # 只需扫描一次原文边界。
        structural, sentences = self._boundaries(text)
        # 从原文第一个字符开始。
        start = 0
        # 覆盖全文。
        while start < len(text):
            # 设置硬上限。
            end = min(start + size, len(text))
            # 仅在非末尾块寻找自然边界。
            if end < len(text):
                # 避免块太短或切分后无法前进。
                lower = start + max(size // 2, overlap + 1)
                # 找出预算内所有完整行、段落和字段组的末尾。
                structural_choices = [point for point in structural if start < point <= end]
                # 优先选择不会使当前块太短的结构边界。
                near_choices = [point for point in structural_choices if point >= lower]
                # 有合适结构边界时，保留尽可能多的完整内容。
                if near_choices:
                    # 取最靠后的结构边界。
                    end = near_choices[-1]
                # 结构边界较早时，判断下一整个单位能否放进下一块。
                elif structural_choices:
                    # 当前预算内最后一个完整单位。
                    boundary = structural_choices[-1]
                    # 没找到下一单位时默认到全文末尾。
                    following = len(text)
                    # 顺序寻找当前预算之后的第一个结构边界。
                    for point in structural:
                        # 第一个更远的边界就是下一单位的结束位置。
                        if point > end:
                            # 保存下一单位的结束位置。
                            following = point
                            # 不需要继续扫描更远的边界。
                            break
                    # 下一单位本身放得下，就提前结束，避免切半行。
                    if following - boundary <= size:
                        # 当前块可以短一些，下一块保留完整单位。
                        end = boundary
                    # 单个单位过长时，才在完整句子处拆分。
                    else:
                        # 查找预算内的句子结束位置。
                        sentence_choices = [point for point in sentences if lower <= point <= end]
                        # 没有句子边界则保留硬上限。
                        if sentence_choices:
                            # 尽量避免切半句话。
                            end = sentence_choices[-1]
                # 没有结构边界时，尝试在句末切分。
                else:
                    # 查找预算内的句子结束位置。
                    sentence_choices = [point for point in sentences if lower <= point <= end]
                    # 没有句子边界才按字符长度硬切。
                    if sentence_choices:
                        # 选择最后一个完整句末。
                        end = sentence_choices[-1]
            # 把当前区间加入列表。
            spans.append((start, end))
            # 最后一块无需继续。
            if end == len(text):
                # 结束切分。
                break
            # 零重叠直接从前块末尾继续。
            if overlap == 0:
                # 不重复上一块的任何字符。
                start = end
                # 继续处理剩余原文。
                continue
            # 目标位置靠近配置的重叠长度。
            target = end - overlap
            # 允许多取一小句，但不能倒退到上一块起点。
            earliest = max(start + 1, end - min(size // 2, overlap * 2))
            # 安全起点必须是完整句或结构单位的起点。
            safe_starts = [point for point in structural + sentences if earliest <= point < end]
            # 没有安全起点时宁可不重叠，也不从字段中间开始。
            start = min(safe_starts, key=lambda point: (abs(point - target), point)) if safe_starts else end
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
