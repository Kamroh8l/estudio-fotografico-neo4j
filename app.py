import os
import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

def obtener_config(clave):
    try:
        if clave in st.secrets:
            return st.secrets[clave]
    except Exception:
        pass
    return os.getenv(clave)


URI = obtener_config("NEO4J_URI")
AUTH = (obtener_config("NEO4J_USERNAME"), obtener_config("NEO4J_PASSWORD"))
DATABASE = obtener_config("NEO4J_DATABASE")

@st.cache_resource
def get_driver():
    return GraphDatabase.driver(URI, auth=AUTH)


driver = get_driver()


def ejecutar_lectura(query, params=None):
    with driver.session(database=DATABASE) as session:
        return [record.data() for record in session.run(query, params or {})]


def ejecutar_escritura(query, params=None):
    with driver.session(database=DATABASE) as session:
        record = session.run(query, params or {}).single()
        return record.data() if record else None


# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Estudio Fotográfico - Neo4j", page_icon="📸", layout="wide")
st.title("📸 Estudio Fotográfico — Gestión de Inventario")
st.caption("Base de datos orientada a grafos alojada en Neo4j AuraDB Cloud")

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Inventario (CRUD)",
    "➕ Agregar Equipo",
    "🔍 Recomendador de Kits (Grafo)",
    "🔗 Paquetes y Conexiones"
])

# --- PESTAÑA 1: LEER, ACTUALIZAR Y ELIMINAR ---
with tab1:
    inventario = ejecutar_lectura("""
        MATCH (n)
        WHERE n:Camara OR n:Lente OR n:Mochila OR n:Impresion
        RETURN labels(n)[0] AS Categoria,
               n.id AS ID,
               coalesce(n.modelo, n.tipo_papel, n.id) AS Nombre,
               coalesce(n.precio_renta, n.precio_venta, n.precio, 0) AS Precio
        ORDER BY Categoria, ID
    """)

    if inventario:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total Artículos", len(inventario))
        col_m2.metric("Cámaras", sum(1 for x in inventario if x["Categoria"] == "Camara"))
        col_m3.metric("Lentes", sum(1 for x in inventario if x["Categoria"] == "Lente"))
        col_m4.metric("Mochilas / Impresiones", sum(1 for x in inventario if x["Categoria"] in ("Mochila", "Impresion")))

        st.dataframe(inventario, use_container_width=True, hide_index=True)

        st.divider()
        col_upd, col_del = st.columns(2)
        opciones_eq = [f"{item['ID']} - {item['Nombre']} ({item['Categoria']})" for item in inventario]

        with col_upd:
            st.subheader("✏️ Actualizar Precio")
            sel_upd = st.selectbox("Selecciona artículo", opciones_eq, key="upd_sel")
            nuevo_precio = st.number_input("Nuevo precio ($)", min_value=0.0, step=50.0)
            if st.button("Guardar nuevo precio", type="primary"):
                id_upd = sel_upd.split(" - ")[0]
                ejecutar_escritura("""
                    MATCH (n {id: $id})
                    SET n.precio = $precio,
                        n.precio_renta = CASE WHEN n.precio_renta IS NOT NULL THEN $precio ELSE null END,
                        n.precio_venta = CASE WHEN n.precio_venta IS NOT NULL THEN $precio ELSE null END
                    RETURN n.id AS id
                """, {"id": id_upd, "precio": nuevo_precio})
                st.success(f"Precio actualizado para {id_upd}.")
                st.rerun()

        with col_del:
            st.subheader("🗑️ Eliminar Artículo")
            sel_del = st.selectbox("Selecciona artículo a eliminar", opciones_eq, key="del_sel")
            if st.button("Eliminar del grafo"):
                id_del = sel_del.split(" - ")[0]
                ejecutar_escritura("MATCH (n {id: $id}) DETACH DELETE n RETURN count(n) AS total", {"id": id_del})
                st.warning(f"Artículo {id_del} eliminado junto con sus relaciones.")
                st.rerun()
    else:
        st.info("No hay artículos registrados en el inventario.")

# --- PESTAÑA 2: CREAR ---
with tab2:
    st.subheader("Registrar nuevo nodo en Neo4j")
    with st.form("form_crear", clear_on_submit=True):
        tipo = st.selectbox("Categoría", ["Camara", "Lente", "Mochila", "Impresion"])
        id_eq = st.text_input("ID único (ej. CAM-04, LEN-06, IMP-02)").strip().upper()
        modelo = st.text_input("Modelo o descripción (ej. Canon RF 85mm f/2)")
        precio = st.number_input("Precio de renta o venta ($)", min_value=0.0, step=50.0)
        enviado = st.form_submit_button("Crear en la nube", type="primary")

        if enviado:
            if id_eq and modelo:
                ejecutar_escritura(f"""
                    CREATE (n:{tipo} {{id: $id, modelo: $modelo, precio: $precio}})
                    RETURN n.id AS id
                """, {"id": id_eq, "modelo": modelo, "precio": precio})
                st.success(f"Nodo [{tipo}] {id_eq} creado exitosamente en Neo4j AuraDB.")
            else:
                st.error("Completa el ID y el modelo antes de guardar.")

# --- PESTAÑA 3: TRAVERSALS DE GRAFO ---
with tab3:
    st.subheader("Compatibilidad por Cámara (Recorrido de Vecindades)")
    camaras = ejecutar_lectura("MATCH (c:Camara) RETURN c.id AS id, coalesce(c.modelo, c.id) AS modelo ORDER BY c.id")

    if camaras:
        opciones_cam = [f"{c['id']} - {c['modelo']}" for c in camaras]
        cam_sel = st.selectbox("Elige una cámara para consultar sus conexiones:", opciones_cam)
        id_cam = cam_sel.split(" - ")[0]

        res_kit = ejecutar_lectura("""
            MATCH (c:Camara {id: $id})
            OPTIONAL MATCH (c)-[:COMPATIBLE_CON]->(l:Lente)
            OPTIONAL MATCH (c)-[:CABE_EN]->(m:Mochila)
            RETURN coalesce(c.modelo, c.id) AS camara,
                   collect(DISTINCT l.modelo) AS lentes,
                   collect(DISTINCT m.modelo) AS mochilas
        """, {"id": id_cam})[0]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🔭 Lentes Compatibles (`[:COMPATIBLE_CON]`)")
            if res_kit["lentes"]:
                for lente in res_kit["lentes"]:
                    st.success(lente)
            else:
                st.write("Sin lentes vinculados.")

        with c2:
            st.markdown("#### 🎒 Mochilas Compatibles (`[:CABE_EN]`)")
            if res_kit["mochilas"]:
                for mochila in res_kit["mochilas"]:
                    st.info(mochila)
            else:
                st.write("Sin mochilas vinculadas.")

# --- PESTAÑA 4: PAQUETES Y CONEXIONES ---
with tab4:
    col_paq, col_con = st.columns([3, 2])

    with col_paq:
        st.subheader("📦 Paquetes Fotográficos Activos")
        paquetes = ejecutar_lectura("""
            MATCH (p:Paquete)-[rel:INCLUYE]->(item)
            RETURN p.id AS ID,
                   p.nombre AS Paquete,
                   p.precio_total AS Precio,
                   collect(toString(coalesce(rel.cantidad, 1)) + 'x ' + coalesce(item.modelo, item.tipo_papel, item.id)) AS Contenido
        """)
        if paquetes:
            for p in paquetes:
                p["Contenido"] = ", ".join(p["Contenido"])
            st.dataframe(paquetes, use_container_width=True, hide_index=True)

    with col_con:
        st.subheader("🔗 Conectar Nodos")
        todos = ejecutar_lectura("""
            MATCH (n) WHERE n.id IS NOT NULL
            RETURN n.id AS id, labels(n)[0] AS tipo, coalesce(n.modelo, n.tipo_papel, n.nombre, n.id) AS nombre
            ORDER BY tipo, id
        """)
        if todos:
            lista_nodos = [f"{n['id']} - {n['nombre']} ({n['tipo']})" for n in todos]
            origen = st.selectbox("Nodo Origen", lista_nodos, key="orig")
            relacion = st.selectbox("Tipo de Relación", ["COMPATIBLE_CON", "CABE_EN", "INCLUYE"])
            destino = st.selectbox("Nodo Destino", lista_nodos, key="dest")

            if st.button("Crear Relación", type="primary"):
                id_o = origen.split(" - ")[0]
                id_d = destino.split(" - ")[0]
                ejecutar_escritura(f"""
                    MATCH (a {{id: $o}}), (b {{id: $d}})
                    MERGE (a)-[r:{relacion}]->(b)
                    ON CREATE SET r.cantidad = CASE WHEN '{relacion}' = 'INCLUYE' THEN 1 ELSE null END
                    RETURN a.id AS o
                """, {"o": id_o, "d": id_d})
                st.success(f"Relación ({id_o})-[:{relacion}]->({id_d}) creada.")
                st.rerun()