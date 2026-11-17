import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI")
AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
DATABASE = os.getenv("NEO4J_DATABASE")

driver = GraphDatabase.driver(URI, auth=AUTH)


# --- OPERACIONES CRUD ---
def listar_inventario():
    query = """
    MATCH (n)
    WHERE n:Camara OR n:Lente OR n:Mochila OR n:Impresion
    RETURN labels(n)[0] AS categoria,
           n.id AS id,
           coalesce(n.modelo, n.tipo_papel) AS nombre,
           coalesce(n.precio_renta, n.precio_venta, n.precio) AS precio
    ORDER BY categoria, id
    """
    with driver.session(database=DATABASE) as session:
        print("\n--- INVENTARIO DEL ESTUDIO ---")
        for r in session.run(query):
            print(f"[{r['categoria']}] {r['id']} - {r['nombre']} (${r['precio']})")


def crear_equipo():
    tipo = input("Tipo (Camara / Lente / Mochila / Impresion): ").strip().capitalize()
    id_eq = input("ID (ej. CAM-04, LEN-06, IMP-02): ").strip().upper()
    modelo = input("Modelo o descripción: ").strip()
    precio = float(input("Precio de renta o venta: "))

    query = f"""
    CREATE (n:{tipo} {{id: $id, modelo: $modelo, precio: $precio}})
    RETURN n.id AS id, labels(n)[0] AS tipo
    """
    with driver.session(database=DATABASE) as session:
        res = session.run(query, id=id_eq, modelo=modelo, precio=precio).single()
        print(f"Creado: [{res['tipo']}] con ID {res['id']}")


def actualizar_precio():
    id_eq = input("ID del equipo a actualizar (ej. CAM-01): ").strip().upper()
    nuevo_precio = float(input("Nuevo precio: "))

    query = """
    MATCH (n {id: $id})
    SET n.precio = $precio,
        n.precio_renta = CASE WHEN n.precio_renta IS NOT NULL THEN $precio ELSE null END,
        n.precio_venta = CASE WHEN n.precio_venta IS NOT NULL THEN $precio ELSE null END
    RETURN n.id AS id, coalesce(n.modelo, n.tipo_papel, n.nombre) AS nombre
    """
    with driver.session(database=DATABASE) as session:
        res = session.run(query, id=id_eq, precio=nuevo_precio).single()
        if res:
            print(f"Precio actualizado para {res['nombre']} ({res['id']}).")
        else:
            print("No se encontró ese ID.")


def eliminar_equipo():
    id_eq = input("ID del equipo a eliminar: ").strip().upper()
    query = "MATCH (n {id: $id}) DETACH DELETE n RETURN count(n) AS eliminados"
    with driver.session(database=DATABASE) as session:
        res = session.run(query, id=id_eq).single()
        print(f"Registros eliminados: {res['eliminados']}")


# --- CONSULTAS DE GRAFO Y RELACIONES ---
def recomendar_kit_camara():
    id_cam = input("ID de la cámara (ej. CAM-01): ").strip().upper()
    query = """
    MATCH (c:Camara {id: $id})
    OPTIONAL MATCH (c)-[:COMPATIBLE_CON]->(l:Lente)
    OPTIONAL MATCH (c)-[:CABE_EN]->(m:Mochila)
    RETURN coalesce(c.modelo, c.id) AS camara,
           collect(DISTINCT l.modelo) AS lentes_compatibles,
           collect(DISTINCT m.modelo) AS mochilas_compatibles
    """
    with driver.session(database=DATABASE) as session:
        res = session.run(query, id=id_cam).single()
        if res and res["camara"]:
            print(f"\nKit compatible para {res['camara']}:")
            print(f"  * Lentes: {', '.join(res['lentes_compatibles']) or 'Ninguno'}")
            print(f"  * Mochilas: {', '.join(res['mochilas_compatibles']) or 'Ninguna'}")
        else:
            print("Cámara no encontrada.")


def ver_paquetes():
    query = """
    MATCH (p:Paquete)-[rel:INCLUYE]->(item)
    RETURN p.nombre AS paquete,
           p.precio_total AS total,
           collect(toString(coalesce(rel.cantidad, 1)) + 'x ' + coalesce(item.modelo, item.tipo_papel)) AS contenido
    """
    with driver.session(database=DATABASE) as session:
        print("\n--- PAQUETES FOTOGRÁFICOS ---")
        for r in session.run(query):
            print(f"{r['paquete']} (${r['total']}): {', '.join(r['contenido'])}")


def conectar_equipos():
    id_origen = input("ID origen (ej. CAM-01 o PAQ-01): ").strip().upper()
    id_destino = input("ID destino (ej. LEN-02, MOC-01 o IMP-01): ").strip().upper()
    print("Tipos de relación: 1. COMPATIBLE_CON | 2. CABE_EN | 3. INCLUYE")
    tipo_op = input("Elige relación (1-3): ").strip()

    relaciones = {
        "1": "COMPATIBLE_CON",
        "2": "CABE_EN",
        "3": "INCLUYE"
    }
    rel = relaciones.get(tipo_op, "COMPATIBLE_CON")

    query = f"""
    MATCH (a {{id: $origen}}), (b {{id: $destino}})
    MERGE (a)-[r:{rel}]->(b)
    ON CREATE SET r.cantidad = CASE WHEN '{rel}' = 'INCLUYE' THEN 1 ELSE null END
    RETURN a.id AS origen, type(r) AS relacion, b.id AS destino
    """
    with driver.session(database=DATABASE) as session:
        res = session.run(query, origen=id_origen, destino=id_destino).single()
        if res:
            print(f"Conexión creada: ({res['origen']})-[:{res['relacion']}]->({res['destino']})")
        else:
            print("Verifica que ambos IDs existan en la base de datos.")


def menu():
    driver.verify_connectivity()
    while True:
        print("\n=== ESTUDIO FOTOGRÁFICO (NEO4J CLOUD) ===")
        print("1. Listar inventario (Read)")
        print("2. Agregar equipo/impresión (Create)")
        print("3. Actualizar precio (Update)")
        print("4. Eliminar equipo (Delete)")
        print("5. [Grafo] Recomendar lentes y mochilas por cámara (Traversal)")
        print("6. [Grafo] Ver contenido de paquetes (Caminos)")
        print("7. [Grafo] Conectar equipos o armar paquete (Relación)")
        print("0. Salir")
        op = input("Elige una opción: ").strip()

        if op == "1":
            listar_inventario()
        elif op == "2":
            crear_equipo()
        elif op == "3":
            actualizar_precio()
        elif op == "4":
            eliminar_equipo()
        elif op == "5":
            recomendar_kit_camara()
        elif op == "6":
            ver_paquetes()
        elif op == "7":
            conectar_equipos()
        elif op == "0":
            break
        else:
            print("Opción no válida.")

    driver.close()


if __name__ == "__main__":
    menu()