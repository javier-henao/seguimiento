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
import math
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# Zona horaria de Colombia (UTC-5)
TZ_COL = ZoneInfo("America/Bogota")


def ahora() -> datetime:
    """Retorna la fecha y hora actual en zona horaria de Colombia."""
    return datetime.now(TZ_COL)


# --- Ruta de la base de datos ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temperaturas.db")

# --- Configuración de página ---
st.set_page_config(
    page_title="Monitor de Temperaturas",
    page_icon="🌡️",
    layout="wide",
)

# --- Auto-refresco cada 10 minutos ---
st.markdown(
    '<script>setTimeout(function(){ window.location.reload(); }, 600000);</script>',
    unsafe_allow_html=True,
)

# --- Estilos + teclado numérico móvil con punto decimal ---
st.markdown("""
<style>
    .main-header { font-size: 1.8rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.2rem; }
    .sub-header  { font-size: 1rem; color: #555; margin-bottom: 1.5rem; }
    .fecha-ultimo { font-size: 1.05rem; color: #333; margin-bottom: 0.5rem; }
    div[data-testid="stMetric"] {
        background: #f8f9fa; border-radius: 8px;
        padding: 12px 16px; border-left: 4px solid #0d6efd;
    }
    .clock-badge {
        font-size: 0.85rem; color: #666; background: #f0f2f6;
        padding: 4px 12px; border-radius: 12px; display: inline-block;
    }
    .reg-deshabilitado { opacity: 0.45; }
</style>
<script>
// Teclado numérico con punto en móvil para campos de temperatura
const observer = new MutationObserver(() => {
    document.querySelectorAll('input[aria-label*="Motor"]').forEach(el => {
        el.setAttribute('inputmode', 'decimal');
        el.setAttribute('pattern', '[0-9]*[.]?[0-9]*');
    });
});
observer.observe(document.body, { childList: true, subtree: true });
</script>
""", unsafe_allow_html=True)


# ============================================================
# UTILIDADES
# ============================================================

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def parse_temp(valor: str) -> Optional[float]:
    """Convierte texto a float o None si está vacío/inválido/cero."""
    if valor is None:
        return None
    v = valor.strip().replace(",", ".")
    if v == "":
        return None
    try:
        f = float(v)
        return f if f != 0.0 else None
    except ValueError:
        return None


def format_temp(valor) -> str:
    """Formatea un valor de temperatura para mostrar."""
    if valor is None or (isinstance(valor, float) and (valor == 0.0 or math.isnan(valor))):
        return "—"
    return f"{valor:.1f} °C"


# ============================================================
# CAPA DE BASE DE DATOS
# ============================================================

def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            temp_motor_1 REAL,
            temp_motor_2 REAL,
            temp_motor_3 REAL,
            temp_motor_4 REAL,
            activo INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Agregar columna activo si no existe (migración)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(registros)").fetchall()]
    if "activo" not in cols:
        conn.execute("ALTER TABLE registros ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            usuario TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    existe = conn.execute("SELECT COUNT(*) FROM admin").fetchone()[0]
    if existe == 0:
        conn.execute(
            "INSERT INTO admin (id, usuario, password_hash) VALUES (1, ?, ?)",
            ("admin", hash_password("admin123")),
        )

    # Cargar datos iniciales si la tabla está vacía
    registros_count = conn.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    if registros_count == 0:
        datos = [
            ("2026-06-13","20:32",48.0,46.0,38.0,38.0),
            ("2026-06-13","20:53",68.0,61.0,62.0,62.0),
            ("2026-06-13","21:13",73.8,68.4,76.0,73.0),
            ("2026-06-13","21:35",76.6,68.3,75.6,77.0),
            ("2026-06-13","22:14",77.8,81.2,80.1,72.7),
            ("2026-06-13","22:46",77.0,80.0,78.0,80.0),
            ("2026-06-13","22:53",75.6,67.3,73.2,70.5),
            ("2026-06-13","23:18",77.8,81.2,80.1,72.7),
            ("2026-06-13","23:47",75.0,72.0,74.0,79.0),
            ("2026-06-14","00:07",74.0,70.0,73.0,79.0),
            ("2026-06-14","01:35",71.0,62.0,70.0,67.0),
            ("2026-06-14","04:28",73.6,66.9,76.7,77.6),
            ("2026-06-14","05:22",73.5,65.9,77.6,77.8),
            ("2026-06-14","06:02",73.0,64.0,71.0,72.0),
            ("2026-06-14","07:27",70.0,61.0,75.0,70.0),
            ("2026-06-14","08:24",76.0,68.0,77.0,77.0),
            ("2026-06-14","10:17",79.0,74.5,79.0,82.0),
            ("2026-06-14","11:26",79.8,75.8,82.7,81.4),
            ("2026-06-14","12:09",79.2,75.8,80.1,83.1),
            ("2026-06-14","13:20",79.8,73.5,82.3,82.5),
            ("2026-06-14","14:36",78.1,74.6,82.6,81.5),
            ("2026-06-14","16:16",73.2,75.2,80.0,82.4),
            ("2026-06-14","17:38",85.7,82.7,90.2,85.7),
            ("2026-06-14","19:35",94.3,90.7,98.0,86.4),
            ("2026-06-18","13:11",53.0,61.6,95.6,60.8),
            ("2026-06-18","14:21",60.3,70.3,101.0,92.3),
            ("2026-06-18","15:19",None,None,82.3,None),
            ("2026-06-18","16:03",None,None,82.2,None),
            ("2026-06-18","16:05",None,67.9,62.3,74.8),
            ("2026-06-18","17:37",73.6,67.2,66.3,75.6),
            ("2026-06-18","18:49",73.0,74.0,87.0,68.0),
            ("2026-06-18","19:21",73.0,74.1,82.1,68.2),
            ("2026-06-18","20:12",74.0,75.2,83.8,69.0),
            ("2026-06-18","21:05",74.7,68.7,86.5,75.3),
            ("2026-06-18","22:18",72.2,75.1,84.4,66.2),
            ("2026-06-18","23:06",72.2,75.2,84.7,65.2),
            ("2026-06-19","01:12",68.8,72.2,84.8,None),
            ("2026-06-19","02:46",73.3,73.4,84.6,65.4),
            ("2026-06-19","03:44",67.2,69.9,83.4,63.0),
            ("2026-06-19","04:54",59.4,66.9,82.4,59.4),
            ("2026-06-19","06:16",69.0,72.0,82.2,62.3),
            ("2026-06-19","06:48",63.0,69.1,82.1,61.1),
            ("2026-06-19","07:26",67.8,71.8,84.1,63.7),
            ("2026-06-19","08:02",62.6,67.3,81.7,62.4),
            ("2026-06-19","08:37",66.8,70.0,82.0,62.4),
            ("2026-06-19","09:21",62.9,68.7,84.4,61.2),
            ("2026-06-19","12:45",70.7,74.9,85.5,68.8),
            ("2026-06-19","13:33",73.1,None,None,68.7),
            ("2026-06-19","15:57",76.4,70.8,72.4,77.6),
            ("2026-06-19","17:01",76.6,71.4,71.4,74.8),
            ("2026-06-19","18:35",75.3,71.8,70.1,75.6),
            ("2026-06-19","20:51",63.6,66.9,64.2,68.1),
            ("2026-06-19","23:03",68.2,74.6,85.8,67.6),
        ]
        conn.executemany(
            "INSERT INTO registros (fecha, hora, temp_motor_1, temp_motor_2, temp_motor_3, temp_motor_4, activo) VALUES (?, ?, ?, ?, ?, ?, 1)",
            datos,
        )

    conn.commit()
    conn.close()


# --- CRUD ---

def insertar_registro(fecha: str, hora: str, t1, t2, t3, t4) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO registros (fecha, hora, temp_motor_1, temp_motor_2, temp_motor_3, temp_motor_4, activo) VALUES (?, ?, ?, ?, ?, ?, 1)",
        (fecha, hora, t1, t2, t3, t4),
    )
    conn.commit()
    conn.close()


def obtener_registros(solo_activos: bool = False) -> pd.DataFrame:
    conn = get_conn()
    where = " WHERE activo = 1" if solo_activos else ""
    df = pd.read_sql_query(
        f"SELECT id, fecha AS Fecha, hora AS Hora, "
        f"temp_motor_1 AS 'Temp Motor 1', temp_motor_2 AS 'Temp Motor 2', "
        f"temp_motor_3 AS 'Temp Motor 3', temp_motor_4 AS 'Temp Motor 4', activo "
        f"FROM registros{where} ORDER BY fecha DESC, hora DESC",
        conn,
    )
    conn.close()
    return df


def obtener_registros_grafica() -> pd.DataFrame:
    """Solo registros activos, ordenados cronológicamente para graficar."""
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT fecha AS Fecha, hora AS Hora, "
        "temp_motor_1 AS 'Temp Motor 1', temp_motor_2 AS 'Temp Motor 2', "
        "temp_motor_3 AS 'Temp Motor 3', temp_motor_4 AS 'Temp Motor 4' "
        "FROM registros WHERE activo = 1 ORDER BY fecha ASC, hora ASC",
        conn,
    )
    conn.close()
    return df


def actualizar_registro(reg_id: int, fecha: str, hora: str, t1, t2, t3, t4) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE registros SET fecha=?, hora=?, temp_motor_1=?, temp_motor_2=?, temp_motor_3=?, temp_motor_4=? WHERE id=?",
        (fecha, hora, t1, t2, t3, t4, reg_id),
    )
    conn.commit()
    conn.close()


def toggle_activo(reg_id: int, nuevo_estado: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE registros SET activo = ? WHERE id = ?", (nuevo_estado, reg_id))
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


def obtener_fechas_disponibles() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT fecha FROM registros WHERE activo = 1 ORDER BY fecha ASC").fetchall()
    conn.close()
    return [r[0] for r in rows]


# --- Admin ---

def verificar_login(usuario: str, password: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT password_hash FROM admin WHERE usuario = ?", (usuario,)).fetchone()
    conn.close()
    return bool(row and row[0] == hash_password(password))


def cambiar_credenciales(nuevo_usuario: str, nueva_password: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE admin SET usuario = ?, password_hash = ? WHERE id = 1", (nuevo_usuario, hash_password(nueva_password)))
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
    df_export = df.drop(columns=["id", "activo"], errors="ignore")
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Temperaturas")
        hoja = writer.sheets["Temperaturas"]
        for i, col in enumerate(df_export.columns, start=1):
            hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = max(len(str(col)) + 4, 14)
    return buffer.getvalue()


# ============================================================
# INICIALIZACIÓN
# ============================================================
init_db()

for key, default in [
    ("admin_logueado", False), ("vista", "principal"),
    ("confirmar_borrado_id", None), ("confirmar_borrado_todo", False),
    ("reg_counter", 0), ("pendiente_confirmar", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ============================================================
# BARRA SUPERIOR
# ============================================================

col_titulo, col_reloj, col_boton = st.columns([4, 1.5, 1])

with col_titulo:
    st.markdown('<p class="main-header">🌡️ Monitor de Temperaturas — Motores</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Registro y seguimiento de temperaturas operativas</p>', unsafe_allow_html=True)

with col_reloj:
    hora_col = ahora()
    st.markdown(
        f'<p class="clock-badge">🇨🇴 {hora_col.strftime("%Y-%m-%d  %H:%M")} COL<br>🔄 Auto-refresco: 10 min</p>',
        unsafe_allow_html=True,
    )

with col_boton:
    if st.session_state.admin_logueado:
        if st.session_state.vista == "admin":
            if st.button("📊 Vista principal", use_container_width=True):
                st.session_state.vista = "principal"
                st.rerun()
        else:
            if st.button("⚙️ Panel Admin", use_container_width=True):
                st.session_state.vista = "admin"
                st.rerun()
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            st.session_state.admin_logueado = False
            st.session_state.vista = "principal"
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
# VISTA: PANEL ADMIN
# ============================================================

if st.session_state.vista == "admin" and st.session_state.admin_logueado:
    st.divider()
    tab_datos, tab_crear, tab_config = st.tabs(["📋 Gestionar registros", "➕ Crear registro", "⚙️ Configuración"])

    # --- TAB 1: Gestionar registros ---
    with tab_datos:
        st.subheader("Registros en base de datos")
        df_admin = obtener_registros(solo_activos=False)

        if df_admin.empty:
            st.info("No hay registros.")
        else:
            # Tabla con indicador de estado
            df_display = df_admin.drop(columns=["id"]).copy()
            df_display["Estado"] = df_display["activo"].map({1: "✅ Activo", 0: "❌ Deshabilitado"})
            df_display = df_display.drop(columns=["activo"])
            st.dataframe(df_display, use_container_width=True, hide_index=False)

            st.divider()
            st.markdown("##### ✏️ Editar registro")

            opciones = {}
            for _, row in df_admin.iterrows():
                estado = "✅" if row["activo"] == 1 else "❌"
                opciones[f"{estado} #{row['id']} — {row['Fecha']} {row['Hora']}"] = row["id"]

            sel = st.selectbox("Selecciona un registro", list(opciones.keys()), key="sel_editar")
            id_sel = opciones[sel]
            reg = df_admin[df_admin["id"] == id_sel].iloc[0]

            st.info(
                f"📌 **Registro #{id_sel}** — Fecha: {reg['Fecha']} | Hora: {reg['Hora']} | "
                f"M1: {format_temp(reg['Temp Motor 1'])} | M2: {format_temp(reg['Temp Motor 2'])} | "
                f"M3: {format_temp(reg['Temp Motor 3'])} | M4: {format_temp(reg['Temp Motor 4'])} | "
                f"Estado: {'Activo' if reg['activo'] == 1 else 'Deshabilitado'}"
            )

            k = f"_{id_sel}"
            col_ef, col_eh = st.columns(2)
            with col_ef:
                try:
                    fecha_edit = st.date_input("Fecha", value=datetime.strptime(reg["Fecha"], "%Y-%m-%d").date(), key=f"ef{k}")
                except Exception:
                    fecha_edit = st.date_input("Fecha", value=ahora().date(), key=f"ef{k}")
            with col_eh:
                hora_edit = st.text_input("Hora (HH:MM)", value=reg["Hora"], max_chars=5, key=f"eh{k}")

            ce1, ce2, ce3, ce4 = st.columns(4)
            def _val_admin(v):
                if v is None or (isinstance(v, float) and (v == 0.0 or math.isnan(v))):
                    return ""
                return str(v)
            with ce1:
                t1_e = st.text_input("Motor 1 (°C)", value=_val_admin(reg["Temp Motor 1"]), key=f"et1{k}")
            with ce2:
                t2_e = st.text_input("Motor 2 (°C)", value=_val_admin(reg["Temp Motor 2"]), key=f"et2{k}")
            with ce3:
                t3_e = st.text_input("Motor 3 (°C)", value=_val_admin(reg["Temp Motor 3"]), key=f"et3{k}")
            with ce4:
                t4_e = st.text_input("Motor 4 (°C)", value=_val_admin(reg["Temp Motor 4"]), key=f"et4{k}")

            col_g, col_t, col_d = st.columns(3)
            with col_g:
                if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
                    if not re.match(r"^\d{1,2}:\d{2}$", hora_edit):
                        st.error("❌ Formato de hora inválido.")
                    else:
                        h, m = int(hora_edit.split(":")[0]), int(hora_edit.split(":")[1])
                        if h > 23 or m > 59:
                            st.error("❌ Hora fuera de rango.")
                        else:
                            actualizar_registro(
                                id_sel, fecha_edit.strftime("%Y-%m-%d"), f"{h:02d}:{m:02d}",
                                parse_temp(t1_e), parse_temp(t2_e), parse_temp(t3_e), parse_temp(t4_e),
                            )
                            st.success("✅ Registro actualizado.")
                            st.rerun()

            with col_t:
                label_toggle = "🔴 Deshabilitar" if reg["activo"] == 1 else "🟢 Habilitar"
                if st.button(label_toggle, use_container_width=True):
                    toggle_activo(id_sel, 0 if reg["activo"] == 1 else 1)
                    st.rerun()

            with col_d:
                if st.button("🗑️ Eliminar", type="secondary", use_container_width=True):
                    st.session_state.confirmar_borrado_id = id_sel

            if st.session_state.confirmar_borrado_id == id_sel:
                st.warning(f"¿Eliminar registro #{id_sel} permanentemente?")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Sí, eliminar", key="cdel"):
                        eliminar_registro(id_sel)
                        st.session_state.confirmar_borrado_id = None
                        st.rerun()
                with cc2:
                    if st.button("❌ Cancelar", key="ccan"):
                        st.session_state.confirmar_borrado_id = None
                        st.rerun()

            st.divider()
            st.markdown("##### 🗑️ Eliminar todos los registros")
            if st.button("Eliminar TODO", type="secondary"):
                st.session_state.confirmar_borrado_todo = True
            if st.session_state.confirmar_borrado_todo:
                st.error("⚠️ ¿Eliminar TODOS los registros permanentemente?")
                cd1, cd2 = st.columns(2)
                with cd1:
                    if st.button("✅ Confirmar", key="call"):
                        eliminar_todos()
                        st.session_state.confirmar_borrado_todo = False
                        st.rerun()
                with cd2:
                    if st.button("❌ Cancelar", key="ccall"):
                        st.session_state.confirmar_borrado_todo = False
                        st.rerun()

    # --- TAB 2: Crear registro (admin, con fecha/hora editable) ---
    with tab_crear:
        st.subheader("Crear nuevo registro")
        rc = st.session_state.reg_counter
        col_nf, col_nh = st.columns(2)
        with col_nf:
            nueva_fecha = st.date_input("Fecha", value=ahora().date(), key=f"nf_{rc}")
        with col_nh:
            nueva_hora = st.text_input("Hora (HH:MM)", value=ahora().strftime("%H:%M"), max_chars=5, key=f"nh_{rc}")

        cn1, cn2, cn3, cn4 = st.columns(4)
        with cn1:
            nt1 = st.text_input("Motor 1 (°C)", value="", key=f"nt1_{rc}")
        with cn2:
            nt2 = st.text_input("Motor 2 (°C)", value="", key=f"nt2_{rc}")
        with cn3:
            nt3 = st.text_input("Motor 3 (°C)", value="", key=f"nt3_{rc}")
        with cn4:
            nt4 = st.text_input("Motor 4 (°C)", value="", key=f"nt4_{rc}")

        if st.button("📥 Crear registro", type="primary", use_container_width=True, key="btn_crear"):
            if not re.match(r"^\d{1,2}:\d{2}$", nueva_hora):
                st.error("❌ Formato de hora inválido.")
            else:
                h, m = int(nueva_hora.split(":")[0]), int(nueva_hora.split(":")[1])
                if h > 23 or m > 59:
                    st.error("❌ Hora fuera de rango.")
                else:
                    v1, v2, v3, v4 = parse_temp(nt1), parse_temp(nt2), parse_temp(nt3), parse_temp(nt4)
                    insertar_registro(nueva_fecha.strftime("%Y-%m-%d"), f"{h:02d}:{m:02d}", v1, v2, v3, v4)
                    alertas = []
                    for nombre, valor in [("Motor 1", v1), ("Motor 2", v2), ("Motor 3", v3), ("Motor 4", v4)]:
                        if valor is not None and valor > 100:
                            alertas.append(f"**{nombre}**: {valor:.1f} °C")
                    if alertas:
                        st.warning(f"⚠️ Temperatura crítica: {', '.join(alertas)}")
                    st.success("✅ Registro creado.")
                    st.session_state.reg_counter += 1
                    st.rerun()

    # --- TAB 3: Configuración ---
    with tab_config:
        st.subheader("Cambiar credenciales de administrador")
        usuario_actual = obtener_usuario_admin()
        st.info(f"Usuario actual: **{usuario_actual}**")
        nuevo_usuario = st.text_input("Nuevo usuario", value=usuario_actual, key="cfg_user")
        nueva_pass = st.text_input("Nueva contraseña", type="password", key="cfg_pass1")
        confirmar_pass = st.text_input("Confirmar contraseña", type="password", key="cfg_pass2")
        if st.button("💾 Guardar credenciales", type="primary", key="btn_creds"):
            if not nuevo_usuario.strip():
                st.error("❌ El usuario no puede estar vacío.")
            elif not nueva_pass:
                st.error("❌ La contraseña no puede estar vacía.")
            elif len(nueva_pass) < 4:
                st.error("❌ Mínimo 4 caracteres.")
            elif nueva_pass != confirmar_pass:
                st.error("❌ Las contraseñas no coinciden.")
            else:
                cambiar_credenciales(nuevo_usuario.strip(), nueva_pass)
                st.success("✅ Credenciales actualizadas.")

    st.stop()


# ============================================================
# VISTA PRINCIPAL (Operario)
# ============================================================

# --- Formulario de captura (fecha/hora automáticas, NO editables) ---
with st.container():
    st.subheader("Registrar lecturas")
    rc = st.session_state.reg_counter

    col_fecha, col_hora = st.columns(2)
    with col_fecha:
        st.text_input("📅 Fecha (automática)", value=ahora().strftime("%Y-%m-%d"), disabled=True)
    with col_hora:
        st.text_input("🕐 Hora (automática)", value=ahora().strftime("%H:%M"), disabled=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        temp1_txt = st.text_input("Temperatura Motor 1 (°C)", value="", key=f"mt1_{rc}", placeholder="Ej: 72.5")
    with col2:
        temp2_txt = st.text_input("Temperatura Motor 2 (°C)", value="", key=f"mt2_{rc}", placeholder="Ej: 68.0")
    with col3:
        temp3_txt = st.text_input("Temperatura Motor 3 (°C)", value="", key=f"mt3_{rc}", placeholder="Ej: 81.3")
    with col4:
        temp4_txt = st.text_input("Temperatura Motor 4 (°C)", value="", key=f"mt4_{rc}", placeholder="Ej: 75.0")

    # --- Flujo de confirmación ---
    pendiente = st.session_state.pendiente_confirmar

    if st.button("📥 Registrar", type="primary", use_container_width=True):
        # Validar que los valores ingresados sean numéricos
        valores_txt = {"Motor 1": temp1_txt, "Motor 2": temp2_txt, "Motor 3": temp3_txt, "Motor 4": temp4_txt}
        error_formato = False
        for nombre, vtxt in valores_txt.items():
            vtxt_clean = vtxt.strip().replace(",", ".")
            if vtxt_clean != "":
                try:
                    float(vtxt_clean)
                except ValueError:
                    st.error(f"❌ Valor inválido en {nombre}: '{vtxt}'. Ingresa un número.")
                    error_formato = True

        if not error_formato:
            v1, v2, v3, v4 = parse_temp(temp1_txt), parse_temp(temp2_txt), parse_temp(temp3_txt), parse_temp(temp4_txt)
            momento = ahora()
            st.session_state.pendiente_confirmar = {
                "fecha": momento.strftime("%Y-%m-%d"),
                "hora": momento.strftime("%H:%M"),
                "t1": v1, "t2": v2, "t3": v3, "t4": v4,
            }
            st.rerun()

    if pendiente is not None:
        st.info(
            f"**¿Confirmar registro?**\n\n"
            f"📅 Fecha: **{pendiente['fecha']}** | 🕐 Hora: **{pendiente['hora']}**\n\n"
            f"🌡️ Motor 1: **{format_temp(pendiente['t1'])}** | "
            f"Motor 2: **{format_temp(pendiente['t2'])}** | "
            f"Motor 3: **{format_temp(pendiente['t3'])}** | "
            f"Motor 4: **{format_temp(pendiente['t4'])}**"
        )
        alertas = []
        for nombre, valor in [("Motor 1", pendiente["t1"]), ("Motor 2", pendiente["t2"]),
                              ("Motor 3", pendiente["t3"]), ("Motor 4", pendiente["t4"])]:
            if valor is not None and valor > 100:
                alertas.append(f"**{nombre}**: {valor:.1f} °C")
        if alertas:
            st.warning(f"⚠️ Temperatura crítica: {', '.join(alertas)}")

        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("✅ Confirmar y guardar", type="primary", use_container_width=True):
                p = pendiente
                insertar_registro(p["fecha"], p["hora"], p["t1"], p["t2"], p["t3"], p["t4"])
                st.session_state.pendiente_confirmar = None
                st.session_state.reg_counter += 1
                st.success("✅ Lectura registrada y guardada.")
                st.rerun()
        with cc2:
            if st.button("❌ Cancelar", use_container_width=True):
                st.session_state.pendiente_confirmar = None
                st.rerun()

st.divider()

# --- Datos activos ---
df = obtener_registros(solo_activos=True)

if df.empty:
    st.info("Aún no hay registros activos.")
else:
    # --- Fecha y hora del último registro + métricas ---
    ultimo = df.iloc[0]  # ya está ordenado desc
    st.markdown(
        f'<p class="fecha-ultimo">📌 Último registro: <strong>{ultimo["Fecha"]}</strong> a las <strong>{ultimo["Hora"]}</strong></p>',
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Motor 1", format_temp(ultimo["Temp Motor 1"]))
    m2.metric("Motor 2", format_temp(ultimo["Temp Motor 2"]))
    m3.metric("Motor 3", format_temp(ultimo["Temp Motor 3"]))
    m4.metric("Motor 4", format_temp(ultimo["Temp Motor 4"]))

    st.divider()

    # --- Historial (orden del último al primero) ---
    st.subheader("Historial de registros")

    df_tabla = df.drop(columns=["id", "activo"], errors="ignore")
    st.dataframe(df_tabla, use_container_width=True, hide_index=True)

    # --- Opción de deshabilitar registros (operario, NO borrar) ---
    st.markdown("##### 🔒 Deshabilitar un registro")
    opciones_deshab = {f"#{row['id']} — {row['Fecha']} {row['Hora']}": row["id"] for _, row in df.iterrows()}
    if opciones_deshab:
        sel_deshab = st.selectbox("Selecciona registro a deshabilitar", list(opciones_deshab.keys()), key="sel_deshab")
        id_deshab = opciones_deshab[sel_deshab]
        if st.button("🔴 Deshabilitar registro", use_container_width=False):
            toggle_activo(id_deshab, 0)
            st.success(f"Registro #{id_deshab} deshabilitado. Solo un administrador puede reactivarlo o eliminarlo.")
            st.rerun()

    st.divider()

    # --- Gráfica de temperaturas ---
    st.subheader("Gráfica de temperaturas")

    df_graf = obtener_registros_grafica()

    if df_graf.empty:
        st.info("No hay datos activos para graficar.")
    else:
        # Selector de rango de fechas
        fechas_disp = sorted(df_graf["Fecha"].unique())
        ultimo_dia = fechas_disp[-1]

        col_rango1, col_rango2 = st.columns(2)
        with col_rango1:
            fecha_inicio = st.date_input(
                "Desde", value=datetime.strptime(ultimo_dia, "%Y-%m-%d").date(),
                min_value=datetime.strptime(fechas_disp[0], "%Y-%m-%d").date(),
                max_value=datetime.strptime(fechas_disp[-1], "%Y-%m-%d").date(),
                key="graf_desde",
            )
        with col_rango2:
            fecha_fin = st.date_input(
                "Hasta", value=datetime.strptime(ultimo_dia, "%Y-%m-%d").date(),
                min_value=datetime.strptime(fechas_disp[0], "%Y-%m-%d").date(),
                max_value=datetime.strptime(fechas_disp[-1], "%Y-%m-%d").date(),
                key="graf_hasta",
            )

        # Filtrar por rango
        df_filtrado = df_graf[
            (df_graf["Fecha"] >= fecha_inicio.strftime("%Y-%m-%d")) &
            (df_graf["Fecha"] <= fecha_fin.strftime("%Y-%m-%d"))
        ].copy()

        columnas_motor = ["Temp Motor 1", "Temp Motor 2", "Temp Motor 3", "Temp Motor 4"]
        colores = {
            "Temp Motor 1": "#0d6efd", "Temp Motor 2": "#e63946",
            "Temp Motor 3": "#2a9d8f", "Temp Motor 4": "#f4a261",
        }

        seleccion = st.multiselect(
            "Motores a visualizar", options=columnas_motor,
            default=columnas_motor, help="Selecciona uno o más motores.",
        )

        if seleccion and not df_filtrado.empty:
            fig = go.Figure()
            etiquetas_x = df_filtrado["Fecha"] + " " + df_filtrado["Hora"]

            for motor in seleccion:
                # Reemplazar 0 y NaN con None para que no se grafiquen
                y_vals = df_filtrado[motor].copy()
                y_vals = y_vals.where((y_vals != 0) & y_vals.notna(), other=None)

                fig.add_trace(go.Scatter(
                    x=etiquetas_x, y=y_vals,
                    mode="lines+markers",
                    name=motor.replace("Temp ", ""),
                    line=dict(color=colores[motor], width=2),
                    marker=dict(size=6),
                    connectgaps=False,  # No conectar puntos donde hay None
                ))

            fig.update_layout(
                xaxis_title="Fecha y hora (COL)",
                yaxis_title="Temperatura (°C)",
                legend_title="Motor",
                template="plotly_white",
                height=450,
                margin=dict(l=40, r=20, t=30, b=40),
                hovermode="x unified",
                xaxis=dict(
                    rangeslider=dict(visible=True, thickness=0.08),
                    type="category",
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
        elif not df_filtrado.empty:
            st.warning("Selecciona al menos un motor.")
        else:
            st.info("No hay datos en el rango seleccionado.")

    st.divider()

    # --- Exportar ---
    st.subheader("Exportar datos")
    archivo_xlsx = generar_excel(df)
    nombre_archivo = f"temperaturas_{ahora().strftime('%Y%m%d_%H%M%S')}.xlsx"
    st.download_button(
        label="📊 Descargar Excel", data=archivo_xlsx,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.spreadsheet",
        type="primary",
    )