# ============================================================
# Monitor de Temperaturas - Motores Industriales
# ============================================================
# Dependencias: pip install streamlit pandas plotly openpyxl
# Ejecución:    streamlit run app.py
# Credenciales iniciales: admin / admin123
# ============================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sqlite3
import hashlib
import re
import os
from datetime import datetime, date
from io import BytesIO

# --- Ruta de la base de datos ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temperaturas.db")

# --- Configuración de página ---
st.set_page_config(
    page_title="Monitor de Temperaturas",
    page_icon="🌡️",
    layout="wide",
)

# --- Estilos ---
st.markdown("""
<style>
    .main-header { font-size: 1.8rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.2rem; }
    .sub-header  { font-size: 1rem; color: #555; margin-bottom: 1.5rem; }
    div[data-testid="stMetric"] {
        background: #f8f9fa; border-radius: 8px;
        padding: 12px 16px; border-left: 4px solid #0d6efd;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# UTILIDADES
# ============================================================

def hash_password(password: str) -> str:
    """Genera hash SHA-256 de la contraseña."""
    return hashlib.sha256(password.encode()).hexdigest()


# ============================================================
# CAPA DE BASE DE DATOS
# ============================================================

def get_conn():
    """Retorna una conexión a SQLite."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Crea las tablas y carga datos iniciales si es la primera vez."""
    conn = get_conn()

    # Tabla de registros
    conn.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            temp_motor_1 REAL NOT NULL,
            temp_motor_2 REAL NOT NULL,
            temp_motor_3 REAL NOT NULL,
            temp_motor_4 REAL NOT NULL
        )
    """)

    # Tabla de administrador (usuario único)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            usuario TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    # Insertar admin por defecto si no existe
    existe = conn.execute("SELECT COUNT(*) FROM admin").fetchone()[0]
    if existe == 0:
        conn.execute(
            "INSERT INTO admin (id, usuario, password_hash) VALUES (1, ?, ?)",
            ("admin", hash_password("admin123")),
        )

    # Cargar datos iniciales del Excel si la tabla está vacía
    registros_count = conn.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    if registros_count == 0:
        datos_iniciales = [
            ("2026-06-13", "20:32", 48.0, 46.0, 38.0, 38.0),
            ("2026-06-13", "20:53", 68.0, 61.0, 62.0, 62.0),
            ("2026-06-13", "21:13", 73.8, 68.4, 76.0, 73.0),
            ("2026-06-13", "21:35", 76.6, 68.3, 75.6, 77.0),
            ("2026-06-14", "21:53", 75.6, 67.3, 73.2, 70.5),
            ("2026-06-14", "03:18", 77.8, 81.2, 80.1, 72.7),
            ("2026-06-14", "10:14", 77.8, 81.2, 80.1, 72.7),
            ("2026-06-13", "22:46", 77.0, 80.0, 78.0, 80.0),
        ]
        conn.executemany(
            "INSERT INTO registros (fecha, hora, temp_motor_1, temp_motor_2, temp_motor_3, temp_motor_4) VALUES (?, ?, ?, ?, ?, ?)",
            datos_iniciales,
        )

    conn.commit()
    conn.close()


# --- CRUD Registros ---

def insertar_registro(fecha: str, hora: str, t1: float, t2: float, t3: float, t4: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO registros (fecha, hora, temp_motor_1, temp_motor_2, temp_motor_3, temp_motor_4) VALUES (?, ?, ?, ?, ?, ?)",
        (fecha, hora, t1, t2, t3, t4),
    )
    conn.commit()
    conn.close()


def obtener_registros() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT id, fecha AS Fecha, hora AS Hora, "
        "temp_motor_1 AS 'Temp Motor 1', temp_motor_2 AS 'Temp Motor 2', "
        "temp_motor_3 AS 'Temp Motor 3', temp_motor_4 AS 'Temp Motor 4' "
        "FROM registros ORDER BY id ASC",
        conn,
    )
    conn.close()
    return df


def actualizar_registro(reg_id: int, fecha: str, hora: str, t1: float, t2: float, t3: float, t4: float) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE registros SET fecha=?, hora=?, temp_motor_1=?, temp_motor_2=?, temp_motor_3=?, temp_motor_4=? WHERE id=?",
        (fecha, hora, t1, t2, t3, t4, reg_id),
    )
    conn.commit()
    conn.close()


def eliminar_registro(reg_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM registros WHERE id = ?", (reg_id,))
    conn.commit()
    conn.close()


def eliminar_todos() -> None:
    conn = get_conn()
    conn.execute("DELETE FROM registros")
    conn.commit()
    conn.close()


# --- Admin ---

def verificar_login(usuario: str, password: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT password_hash FROM admin WHERE usuario = ?", (usuario,)
    ).fetchone()
    conn.close()
    if row and row[0] == hash_password(password):
        return True
    return False


def cambiar_credenciales(nuevo_usuario: str, nueva_password: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE admin SET usuario = ?, password_hash = ? WHERE id = 1",
        (nuevo_usuario, hash_password(nueva_password)),
    )
    conn.commit()
    conn.close()


def obtener_usuario_admin() -> str:
    conn = get_conn()
    row = conn.execute("SELECT usuario FROM admin WHERE id = 1").fetchone()
    conn.close()
    return row[0] if row else "admin"


# --- Excel ---

def generar_excel(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    # Excluir columna id si existe
    df_export = df.drop(columns=["id"], errors="ignore")
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Temperaturas")
        hoja = writer.sheets["Temperaturas"]
        for i, col in enumerate(df_export.columns, start=1):
            ancho = max(len(str(col)) + 4, 14)
            hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = ancho
    return buffer.getvalue()


# ============================================================
# INICIALIZACIÓN
# ============================================================
init_db()

# Estado de sesión
if "admin_logueado" not in st.session_state:
    st.session_state.admin_logueado = False
if "vista" not in st.session_state:
    st.session_state.vista = "principal"
if "editar_id" not in st.session_state:
    st.session_state.editar_id = None
if "confirmar_borrado_id" not in st.session_state:
    st.session_state.confirmar_borrado_id = None
if "confirmar_borrado_todo" not in st.session_state:
    st.session_state.confirmar_borrado_todo = False


# ============================================================
# BARRA SUPERIOR — LOGIN / ADMIN
# ============================================================

col_titulo, col_boton = st.columns([5, 1])
with col_titulo:
    st.markdown('<p class="main-header">🌡️ Monitor de Temperaturas — Motores</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Registro y seguimiento de temperaturas operativas</p>', unsafe_allow_html=True)

with col_boton:
    if st.session_state.admin_logueado:
        # Mostrar menú admin
        if st.session_state.vista == "admin":
            if st.button("📊 Vista principal", use_container_width=True):
                st.session_state.vista = "principal"
                st.session_state.editar_id = None
                st.rerun()
        else:
            if st.button("⚙️ Panel Admin", use_container_width=True):
                st.session_state.vista = "admin"
                st.rerun()
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            st.session_state.admin_logueado = False
            st.session_state.vista = "principal"
            st.session_state.editar_id = None
            st.rerun()
    else:
        if st.button("🔐 Admin", use_container_width=True):
            st.session_state.vista = "login"
            st.rerun()


# ============================================================
# VISTA: LOGIN
# ============================================================

if st.session_state.vista == "login" and not st.session_state.admin_logueado:
    st.divider()
    st.subheader("🔐 Iniciar sesión — Administrador")

    col_login, _, _ = st.columns([1, 1, 1])
    with col_login:
        usuario_input = st.text_input("Usuario", key="login_user")
        password_input = st.text_input("Contraseña", type="password", key="login_pass")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Ingresar", type="primary", use_container_width=True):
                if verificar_login(usuario_input, password_input):
                    st.session_state.admin_logueado = True
                    st.session_state.vista = "admin"
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
        with c2:
            if st.button("Cancelar", use_container_width=True):
                st.session_state.vista = "principal"
                st.rerun()

    st.stop()


# ============================================================
# VISTA: PANEL ADMIN (CRUD completo)
# ============================================================

if st.session_state.vista == "admin" and st.session_state.admin_logueado:
    st.divider()

    # --- Tabs del panel admin ---
    tab_datos, tab_crear, tab_config = st.tabs(["📋 Gestionar registros", "➕ Crear registro", "⚙️ Configuración"])

    # --- TAB 1: Gestionar registros (Read, Update, Delete) ---
    with tab_datos:
        st.subheader("Registros en base de datos")
        df_admin = obtener_registros()

        if df_admin.empty:
            st.info("No hay registros en la base de datos.")
        else:
            # Mostrar tabla
            st.dataframe(
                df_admin.drop(columns=["id"]),
                use_container_width=True,
                hide_index=False,
            )

            st.divider()

            # --- Editar registro individual ---
            st.markdown("##### ✏️ Editar registro")
            opciones = {f"#{row['id']} — {row['Fecha']} {row['Hora']}": row["id"] for _, row in df_admin.iterrows()}
            seleccion_editar = st.selectbox("Selecciona un registro para editar", options=list(opciones.keys()), key="sel_editar")
            id_seleccionado = opciones[seleccion_editar]

            # Obtener datos actuales del registro
            reg_actual = df_admin[df_admin["id"] == id_seleccionado].iloc[0]

            # Resumen visual del registro seleccionado
            st.info(
                f"📌 **Registro #{id_seleccionado}** — "
                f"Fecha: {reg_actual['Fecha']} | Hora: {reg_actual['Hora']} | "
                f"M1: {reg_actual['Temp Motor 1']:.1f}°C | "
                f"M2: {reg_actual['Temp Motor 2']:.1f}°C | "
                f"M3: {reg_actual['Temp Motor 3']:.1f}°C | "
                f"M4: {reg_actual['Temp Motor 4']:.1f}°C"
            )

            # Claves dinámicas para que los campos se actualicen al cambiar de registro
            k = f"_{id_seleccionado}"

            col_ef, col_eh = st.columns(2)
            with col_ef:
                try:
                    fecha_edit = st.date_input("Fecha", value=datetime.strptime(reg_actual["Fecha"], "%Y-%m-%d").date(), key=f"edit_fecha{k}")
                except Exception:
                    fecha_edit = st.date_input("Fecha", value=date.today(), key=f"edit_fecha{k}")
            with col_eh:
                hora_edit = st.text_input("Hora (HH:MM)", value=reg_actual["Hora"], max_chars=5, key=f"edit_hora{k}")

            ce1, ce2, ce3, ce4 = st.columns(4)
            with ce1:
                t1_edit = st.number_input("Motor 1", value=float(reg_actual["Temp Motor 1"]), step=0.1, format="%.1f", key=f"edit_t1{k}")
            with ce2:
                t2_edit = st.number_input("Motor 2", value=float(reg_actual["Temp Motor 2"]), step=0.1, format="%.1f", key=f"edit_t2{k}")
            with ce3:
                t3_edit = st.number_input("Motor 3", value=float(reg_actual["Temp Motor 3"]), step=0.1, format="%.1f", key=f"edit_t3{k}")
            with ce4:
                t4_edit = st.number_input("Motor 4", value=float(reg_actual["Temp Motor 4"]), step=0.1, format="%.1f", key=f"edit_t4{k}")

            col_guardar, col_eliminar = st.columns(2)
            with col_guardar:
                if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
                    if not re.match(r"^\d{1,2}:\d{2}$", hora_edit):
                        st.error("❌ Formato de hora inválido.")
                    else:
                        h, m = int(hora_edit.split(":")[0]), int(hora_edit.split(":")[1])
                        if h > 23 or m > 59:
                            st.error("❌ Hora fuera de rango.")
                        else:
                            actualizar_registro(id_seleccionado, fecha_edit.strftime("%Y-%m-%d"), f"{h:02d}:{m:02d}", t1_edit, t2_edit, t3_edit, t4_edit)
                            st.success("✅ Registro actualizado.")
                            st.rerun()

            with col_eliminar:
                if st.button("🗑️ Eliminar este registro", type="secondary", use_container_width=True):
                    st.session_state.confirmar_borrado_id = id_seleccionado

            if st.session_state.confirmar_borrado_id == id_seleccionado:
                st.warning(f"¿Eliminar registro #{id_seleccionado}? Esta acción no se puede deshacer.")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Sí, eliminar", key="confirm_del"):
                        eliminar_registro(id_seleccionado)
                        st.session_state.confirmar_borrado_id = None
                        st.success("Registro eliminado.")
                        st.rerun()
                with cc2:
                    if st.button("❌ Cancelar", key="cancel_del"):
                        st.session_state.confirmar_borrado_id = None
                        st.rerun()

            st.divider()

            # --- Eliminar todos ---
            st.markdown("##### 🗑️ Eliminar todos los registros")
            if st.button("Eliminar TODO", type="secondary"):
                st.session_state.confirmar_borrado_todo = True

            if st.session_state.confirmar_borrado_todo:
                st.error("⚠️ ¿Estás seguro? Se eliminarán TODOS los registros permanentemente.")
                cd1, cd2 = st.columns(2)
                with cd1:
                    if st.button("✅ Confirmar eliminación total", key="confirm_all"):
                        eliminar_todos()
                        st.session_state.confirmar_borrado_todo = False
                        st.success("Todos los registros eliminados.")
                        st.rerun()
                with cd2:
                    if st.button("❌ Cancelar", key="cancel_all"):
                        st.session_state.confirmar_borrado_todo = False
                        st.rerun()

    # --- TAB 2: Crear registro ---
    with tab_crear:
        st.subheader("Crear nuevo registro")

        col_nf, col_nh = st.columns(2)
        with col_nf:
            nueva_fecha = st.date_input("Fecha", value=date.today(), key="new_fecha")
        with col_nh:
            nueva_hora = st.text_input("Hora (HH:MM)", value=datetime.now().strftime("%H:%M"), max_chars=5, key="new_hora")

        cn1, cn2, cn3, cn4 = st.columns(4)
        with cn1:
            nt1 = st.number_input("Motor 1 (°C)", value=0.0, step=0.1, format="%.1f", key="new_t1")
        with cn2:
            nt2 = st.number_input("Motor 2 (°C)", value=0.0, step=0.1, format="%.1f", key="new_t2")
        with cn3:
            nt3 = st.number_input("Motor 3 (°C)", value=0.0, step=0.1, format="%.1f", key="new_t3")
        with cn4:
            nt4 = st.number_input("Motor 4 (°C)", value=0.0, step=0.1, format="%.1f", key="new_t4")

        if st.button("📥 Crear registro", type="primary", use_container_width=True, key="btn_crear_admin"):
            if not re.match(r"^\d{1,2}:\d{2}$", nueva_hora):
                st.error("❌ Formato de hora inválido.")
            else:
                h, m = int(nueva_hora.split(":")[0]), int(nueva_hora.split(":")[1])
                if h > 23 or m > 59:
                    st.error("❌ Hora fuera de rango.")
                else:
                    insertar_registro(nueva_fecha.strftime("%Y-%m-%d"), f"{h:02d}:{m:02d}", nt1, nt2, nt3, nt4)
                    st.success("✅ Registro creado exitosamente.")

                    alertas = []
                    for nombre, valor in [("Motor 1", nt1), ("Motor 2", nt2), ("Motor 3", nt3), ("Motor 4", nt4)]:
                        if valor > 100:
                            alertas.append(f"**{nombre}**: {valor:.1f} °C")
                    if alertas:
                        st.warning(f"⚠️ Temperatura crítica: {', '.join(alertas)}")

    # --- TAB 3: Configuración (cambiar credenciales) ---
    with tab_config:
        st.subheader("Cambiar credenciales de administrador")

        usuario_actual = obtener_usuario_admin()
        st.info(f"Usuario actual: **{usuario_actual}**")

        nuevo_usuario = st.text_input("Nuevo usuario", value=usuario_actual, key="cfg_user")
        nueva_pass = st.text_input("Nueva contraseña", type="password", key="cfg_pass1")
        confirmar_pass = st.text_input("Confirmar contraseña", type="password", key="cfg_pass2")

        if st.button("💾 Guardar credenciales", type="primary", key="btn_save_creds"):
            if not nuevo_usuario.strip():
                st.error("❌ El usuario no puede estar vacío.")
            elif not nueva_pass:
                st.error("❌ La contraseña no puede estar vacía.")
            elif len(nueva_pass) < 4:
                st.error("❌ La contraseña debe tener al menos 4 caracteres.")
            elif nueva_pass != confirmar_pass:
                st.error("❌ Las contraseñas no coinciden.")
            else:
                cambiar_credenciales(nuevo_usuario.strip(), nueva_pass)
                st.success("✅ Credenciales actualizadas correctamente.")

    st.stop()


# ============================================================
# VISTA PRINCIPAL (usuarios normales)
# ============================================================

# --- Formulario de captura ---
with st.container():
    st.subheader("Registrar lecturas")

    col_fecha, col_hora = st.columns(2)
    with col_fecha:
        fecha_sel = st.date_input("📅 Fecha", value=date.today())
    with col_hora:
        hora_sel = st.text_input("🕐 Hora (HH:MM)", value=datetime.now().strftime("%H:%M"), max_chars=5)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        temp1 = st.number_input("Temperatura Motor 1 (°C)", min_value=-50.0, max_value=500.0, value=0.0, step=0.1, format="%.1f")
    with col2:
        temp2 = st.number_input("Temperatura Motor 2 (°C)", min_value=-50.0, max_value=500.0, value=0.0, step=0.1, format="%.1f")
    with col3:
        temp3 = st.number_input("Temperatura Motor 3 (°C)", min_value=-50.0, max_value=500.0, value=0.0, step=0.1, format="%.1f")
    with col4:
        temp4 = st.number_input("Temperatura Motor 4 (°C)", min_value=-50.0, max_value=500.0, value=0.0, step=0.1, format="%.1f")

    if st.button("📥 Registrar", type="primary", use_container_width=True):
        if not re.match(r"^\d{1,2}:\d{2}$", hora_sel):
            st.error("❌ Formato de hora inválido. Usa HH:MM (ejemplo: 08:30)")
        else:
            h, m = int(hora_sel.split(":")[0]), int(hora_sel.split(":")[1])
            if h > 23 or m > 59:
                st.error("❌ Hora fuera de rango. Horas: 0-23, Minutos: 0-59")
            else:
                hora_formateada = f"{h:02d}:{m:02d}"
                insertar_registro(fecha_sel.strftime("%Y-%m-%d"), hora_formateada, temp1, temp2, temp3, temp4)
                st.success("✅ Lectura registrada y guardada.")

                alertas = []
                for nombre, valor in [("Motor 1", temp1), ("Motor 2", temp2), ("Motor 3", temp3), ("Motor 4", temp4)]:
                    if valor > 100:
                        alertas.append(f"**{nombre}**: {valor:.1f} °C")
                if alertas:
                    st.warning(f"⚠️ Temperatura crítica detectada en: {', '.join(alertas)}")

st.divider()

# --- Datos ---
df = obtener_registros()

if df.empty:
    st.info("Aún no hay registros. Ingresa las temperaturas y presiona **Registrar**.")
else:
    # Métricas del último registro
    ultimo = df.iloc[-1]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Motor 1", f"{ultimo['Temp Motor 1']:.1f} °C")
    m2.metric("Motor 2", f"{ultimo['Temp Motor 2']:.1f} °C")
    m3.metric("Motor 3", f"{ultimo['Temp Motor 3']:.1f} °C")
    m4.metric("Motor 4", f"{ultimo['Temp Motor 4']:.1f} °C")

    st.divider()

    # --- Tabla ---
    st.subheader("Historial de registros")
    st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)

    st.divider()

    # --- Gráfica ---
    st.subheader("Gráfica de temperaturas")

    columnas_motor = ["Temp Motor 1", "Temp Motor 2", "Temp Motor 3", "Temp Motor 4"]
    colores = {
        "Temp Motor 1": "#0d6efd", "Temp Motor 2": "#e63946",
        "Temp Motor 3": "#2a9d8f", "Temp Motor 4": "#f4a261",
    }

    seleccion = st.multiselect(
        "Motores a visualizar", options=columnas_motor,
        default=columnas_motor, help="Selecciona uno o más motores.",
    )

    if seleccion:
        fig = go.Figure()
        etiquetas_x = df["Fecha"] + " " + df["Hora"]
        for motor in seleccion:
            fig.add_trace(go.Scatter(
                x=etiquetas_x, y=df[motor],
                mode="lines+markers",
                name=motor.replace("Temp ", ""),
                line=dict(color=colores[motor], width=2),
                marker=dict(size=6),
            ))
        fig.update_layout(
            xaxis_title="Fecha y hora", yaxis_title="Temperatura (°C)",
            legend_title="Motor", template="plotly_white",
            height=420, margin=dict(l=40, r=20, t=30, b=40),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Selecciona al menos un motor para ver la gráfica.")

    st.divider()

    # --- Exportar ---
    st.subheader("Exportar datos")
    archivo_xlsx = generar_excel(df)
    nombre_archivo = f"temperaturas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    st.download_button(
        label="📊 Descargar Excel", data=archivo_xlsx,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.spreadsheet",
        type="primary",
    )