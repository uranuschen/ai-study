import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="ragdb",
    user="rag",
    password="rag123456"
)

cursor = conn.cursor()

query_vector = "[0.85,0.15,0.25]"

cursor.execute("""
    SELECT
        id,
        content,
        1 - (embedding <=> %s::vector) AS similarity
    FROM rag_documents
    ORDER BY embedding <=> %s::vector
    LIMIT 2
""", (query_vector, query_vector))

rows = cursor.fetchall()

for row in rows:
    print(row)

cursor.close()
conn.close()