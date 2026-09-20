import psycopg2


def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="ragdb",
        user="rag",
        password="rag123456"
    )