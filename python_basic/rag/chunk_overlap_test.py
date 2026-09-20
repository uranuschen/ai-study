from langchain_text_splitters import RecursiveCharacterTextSplitter


text = """
退款失败可能是由于支付渠道异常导致用户提交退款申请以后系统会检查订单状态和支付状态然后调用支付平台执行退款支付平台返回结果以后系统会更新退款状态并通知用户如果长时间没有返回结果需要联系客服进行人工处理
"""

# LangChain 切分工具
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=30,
    chunk_overlap=10,

    # 不提供句号、逗号等自然分隔符
    # 最终会按照字符长度切分
    separators=[""]
)


chunks = text_splitter.split_text(text)


print("Chunk 数量:", len(chunks))

for index, chunk in enumerate(chunks, start=1):
    print(f"\nChunk {index}")
    print(chunk)