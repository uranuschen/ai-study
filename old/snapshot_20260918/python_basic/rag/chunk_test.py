text = """
退款失败可能是由于支付渠道异常导致。
订单取消成功后，系统会自动触发退款流程。
如果退款状态为处理中，需要等待支付平台返回结果。
如果银行卡已经扣款但退款未到账，需要联系支付渠道确认。
退款完成后，金额通常会原路返回。
"""


def split_text(text, chunk_size, overlap):
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size

        chunk = text[start:end]

        chunks.append(chunk)

        start = end - overlap

    return chunks


# 三组实验参数
experiments = [
    (30, 0),
    (30, 5),
    (50, 10)
]


for chunk_size, overlap in experiments:

    print()
    print("=" * 50)
    print(
        f"chunk_size={chunk_size}, overlap={overlap}"
    )
    print("=" * 50)

    chunks = split_text(
        text=text,
        chunk_size=chunk_size,
        overlap=overlap
    )

    for i, chunk in enumerate(chunks):
        print(f"Chunk {i + 1}:")
        print(chunk)
        print("--------------------")