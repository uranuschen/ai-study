from pathlib import Path
from pypdf import PdfReader


# 每个 chunk 最大字符数
CHUNK_SIZE = 30


# 简单切分文本
def split_text(text: str, chunk_size: int):
    chunks = []

    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)

    return chunks


# 当前 Python 文件所在目录
BASE_DIR = Path(__file__).parent
pdf_path = BASE_DIR / "data" / "refund_test.pdf"

# 打开 PDF
reader = PdfReader(pdf_path)

documents = []

print("PDF总页数:", len(reader.pages))

# 先读取每一页
for page_number, page in enumerate(reader.pages, start=1):
    try:
        text = page.extract_text()

        # 空白页或扫描图片页跳过
        if not text or not text.strip():
            print(f"第 {page_number} 页没有可提取文字，已跳过")
            continue

        document = {
            "content": text.strip(),
            "metadata": {
                "source": pdf_path.name,
                "page": page_number,
                "suffix": pdf_path.suffix
            }
        }

        documents.append(document)

    except Exception as e:
        # 单页异常不影响后续页面
        print(f"第 {page_number} 页读取失败，已跳过: {e}")


# 保存切分后的所有 chunk
chunks = []

for document in documents:

    content = document["content"]
    metadata = document["metadata"]

    # 对当前页内容进行切分
    text_chunks = split_text(content, CHUNK_SIZE)

    for chunk_index, chunk_text in enumerate(text_chunks, start=1):

        chunk = {
            "content": chunk_text,
            "metadata": {
                "source": metadata["source"],
                "page": metadata["page"],
                "suffix": metadata["suffix"],
                "chunk": chunk_index
            }
        }

        chunks.append(chunk)


print("\n成功生成 Chunk 数:", len(chunks))

# 查看所有 chunk
for chunk in chunks:
    print("\ncontent:")
    print(chunk["content"])

    print("metadata:")
    print(chunk["metadata"])