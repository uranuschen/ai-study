from pathlib import Path
from pypdf import PdfReader


# 当前 Python 文件所在目录
BASE_DIR = Path(__file__).parent
pdf_path = BASE_DIR / "data" / "refund_test.pdf"

# 打开 PDF
reader = PdfReader(pdf_path)

documents = []

print("PDF总页数:", len(reader.pages))

# 一页一页读取 PDF
for page_number, page in enumerate(reader.pages, start=1):
    try:
        # 提取当前页文字
        text = page.extract_text()

        # 空白页、扫描图片页通常提取不到文字
        if not text or not text.strip():
            print(f"第 {page_number} 页没有可提取文字，已跳过")
            continue

        # 保存正文和元数据
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
        # 单页异常时跳过，不影响后面的页面
        print(f"第 {page_number} 页读取失败，已跳过: {e}")


print("\n成功加载文档数:", len(documents))

# 查看成功读取的数据
for document in documents:
    print("\ncontent:")
    print(document["content"])

    print("metadata:")
    print(document["metadata"])