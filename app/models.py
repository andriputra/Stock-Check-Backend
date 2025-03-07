from app.extensions import mysql

class Customer:
    @staticmethod
    def get_customers(name_query):
        conn = mysql.connection
        cursor = conn.cursor()
        query = "SELECT DISTINCT `nama` FROM customers WHERE `nama` LIKE %s LIMIT 10"
        cursor.execute(query, ('%' + name_query + '%',))
        results = cursor.fetchall()
        cursor.close()
        return [row['nama'] for row in results]

class PartNumber:
    @staticmethod
    def get_datapn(code_query):
        conn = mysql.connection
        cursor = conn.cursor()
        query = "SELECT DISTINCT `code` FROM datapn WHERE `code` LIKE %s LIMIT 10"
        cursor.execute(query, ('%' + code_query + '%',))
        results = cursor.fetchall()
        cursor.close()
        return [row['code'] for row in results]
