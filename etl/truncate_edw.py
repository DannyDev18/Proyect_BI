import psycopg2
conn=psycopg2.connect('dbname=edw user=etl_user password=CHANGE_ME host=127.0.0.1 port=5433')
cursor=conn.cursor()
cursor.execute("DELETE FROM edw.etl_control WHERE tabla_destino IN ('fact_ventas_detalle', 'fact_devoluciones');")
cursor.execute("TRUNCATE TABLE edw.fact_ventas_detalle RESTART IDENTITY CASCADE;")
cursor.execute("TRUNCATE TABLE edw.fact_devoluciones RESTART IDENTITY CASCADE;")
conn.commit()
conn.close()
print('Truncated EDW tables successfully.')
