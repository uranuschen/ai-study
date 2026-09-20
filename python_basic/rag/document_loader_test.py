from pathlib import Path


# 读取 TXT / Markdown 文件
def load_text_file(file_path):

    path = Path(file_path)

    # 读取正文内容
    content = path.read_text(
        encoding="utf-8"
    )

    # 保存文件相关的元数据
    metadata = {
        "source": path.name,
        "suffix": path.suffix
    }

    return {
        "content": content,
        "metadata": metadata
    }


# 把整个文档切成多个 Chunk
def split_document(document, chunk_size=30, overlap=5):

    text = document["content"]
    metadata = document["metadata"]

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        # 当前 Chunk 的正文
        chunk_text = text[start:end]

        # 每个 Chunk 都保留原文件的 metadata
        chunk = {
            "content": chunk_text,
            "metadata": metadata
        }

        chunks.append(chunk)

        # overlap 表示下一段往前重复多少字符
        start = end - overlap

    return chunks


# 当前 Python 文件所在目录
current_dir = Path(__file__).parent


# 加载 refund.md
document = load_text_file(
    current_dir / "refund.md"
)


# 对文档进行切分
chunks = split_document(
    document,
    chunk_size=30,
    overlap=5
)


# 查看切分结果
for i, chunk in enumerate(chunks):

    print(f"Chunk {i + 1}")

    print("content:")
    print(chunk["content"])

    print("metadata:")
    print(chunk["metadata"])