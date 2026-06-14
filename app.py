# ============================================================
# Monitor de Temperaturas - Motores Industriales
# ============================================================
# Dependencias: pip install streamlit pandas plotly openpyxl
# Ejecución:    streamlit run app.py
# ============================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sqlite3
import re
import os
from datetime import datetime
from io import BytesIO

# --- Ruta de la base de datos ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temperaturas.db")

# --- Configuración de página ---
st.set_page_config(
    page_title="Monitor de Temperaturas",
    page_icon="🌡️",
    layout="wide",
)

# --- Estilos personalizados ---
st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    div[data-testid="stMetric"] {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 12px 16px;
        border-left: 4px solid #0d6efd;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# CAPA DE BASE DE DATOS (SQLite)
# ============================================================

def init_db() -> None:
    """Crea la tabla de registros si no existe."""
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()


def insertar_registro(fecha: str, hora: str, t1: float, t2: float, t3: float, t4: float) -> None:
    """Inserta un nuevo registro con fecha y hora seleccionadas."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO registros (fecha, hora, temp_motor_1, temp_motor_2, temp_motor_3, temp_motor_4) VALUES (?, ?, ?, ?, ?, ?)",
        (fecha, hora, t1, t2, t3, t4),
    )
    conn.commit()
    conn.close()


def obtener_registros() -> pd.DataFrame:
    """Devuelve todos los registros como DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT fecha AS Fecha, hora AS Hora, temp_motor_1 AS 'Temp Motor 1', temp_motor_2 AS 'Temp Motor 2', temp_motor_3 AS 'Temp Motor 3', temp_motor_4 AS 'Temp Motor 4' FROM registros ORDER BY id ASC",
        conn,
    )
    conn.close()
    return df


def eliminar_registro(indice: int) -> None:
    """Elimina un registro por su posición (0-indexed) en la tabla ordenada."""
    conn = sqlite3.connect(DB_PATH)
    ids = conn.execute("SELECT id FROM registros ORDER BY id ASC").fetchall()
    if 0 <= indice < len(ids):
        conn.execute("DELETE FROM registros WHERE id = ?", (ids[indice][0],))
        conn.commit()
    conn.close()


def eliminar_todos() -> None:
    """Elimina todos los registros de la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM registros")
    conn.commit()
    conn.close()


def generar_excel(df: pd.DataFrame) -> bytes:
    """Genera un archivo Excel en memoria a partir del DataFrame."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Temperaturas")
        hoja = writer.sheets["Temperaturas"]
        for i, col in enumerate(df.columns, start=1):
            ancho = max(len(str(col)) + 4, 14)
            hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = ancho
    return buffer.getvalue()


# Inicializar la base de datos al arrancar
init_db()


# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

st.markdown('<p class="main-header">🌡️ Monitor de Temperaturas — Motores</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Registro y seguimiento de temperaturas operativas</p>', unsafe_allow_html=True)

# --- Formulario de captura ---
with st.container():
    st.subheader("Registrar lecturas")

    # Fecha seleccionable + Hora escrita manualmente
    col_fecha, col_hora = st.columns(2)
    with col_fecha:
        fecha_sel = st.date_input("📅 Fecha", value=datetime.now().date())
    with col_hora:
        hora_sel = st.text_input("🕐 Hora (HH:MM)", value=datetime.now().strftime("%H:%M"), max_chars=5)

    # Campos de temperatura
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
        # Validar formato de hora
        if not re.match(r"^\d{1,2}:\d{2}$", hora_sel):
            st.error("❌ Formato de hora inválido. Usa HH:MM (ejemplo: 08:30)")
        else:
            h, m = int(hora_sel.split(":")[0]), int(hora_sel.split(":")[1])
            if h > 23 or m > 59:
                st.error("❌ Hora fuera de rango. Horas: 0-23, Minutos: 0-59")
            else:
                hora_formateada = f"{h:02d}:{m:02d}"
                insertar_registro(fecha_sel.strftime("%Y-%m-%d"), hora_formateada, temp1, temp2, temp3, temp4)
                st.success("✅ Lectura registrada y guardada en base de datos.")

                # Advertencia si alguna temperatura supera 100 °C
                alertas = []
                for nombre, valor in [("Motor 1", temp1), ("Motor 2", temp2), ("Motor 3", temp3), ("Motor 4", temp4)]:
                    if valor > 100:
                        alertas.append(f"**{nombre}**: {valor:.1f} °C")
                if alertas:
                    st.warning(f"⚠️ Temperatura crítica detectada en: {', '.join(alertas)}")

st.divider()

# --- Leer datos persistidos ---
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

    # --- Tabla de registros ---
    st.subheader("Historial de registros")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # --- Gráfica de temperaturas ---
    st.subheader("Gráfica de temperaturas")

    columnas_motor = ["Temp Motor 1", "Temp Motor 2", "Temp Motor 3", "Temp Motor 4"]
    colores = {
        "Temp Motor 1": "#0d6efd",
        "Temp Motor 2": "#e63946",
        "Temp Motor 3": "#2a9d8f",
        "Temp Motor 4": "#f4a261",
    }

    seleccion = st.multiselect(
        "Motores a visualizar",
        options=columnas_motor,
        default=columnas_motor,
        help="Selecciona uno o más motores para graficar.",
    )

    if seleccion:
        fig = go.Figure()
        # Etiqueta combinada Fecha + Hora para el eje X
        etiquetas_x = df["Fecha"] + " " + df["Hora"]
        for motor in seleccion:
            fig.add_trace(go.Scatter(
                x=etiquetas_x,
                y=df[motor],
                mode="lines+markers",
                name=motor.replace("Temp ", ""),
                line=dict(color=colores[motor], width=2),
                marker=dict(size=6),
            ))

        fig.update_layout(
            xaxis_title="Fecha y hora del registro",
            yaxis_title="Temperatura (°C)",
            legend_title="Motor",
            template="plotly_white",
            height=420,
            margin=dict(l=40, r=20, t=30, b=40),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Selecciona al menos un motor para ver la gráfica.")

    st.divider()

    # --- Exportación y gestión ---
    col_export, col_delete = st.columns(2)

    with col_export:
        st.subheader("Exportar datos")
        archivo_xlsx = generar_excel(df)
        nombre_archivo = f"temperaturas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        st.download_button(
            label="📊 Descargar Excel",
            data=archivo_xlsx,
            file_name=nombre_archivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.spreadsheet",
            type="primary",
        )

    with col_delete:
        st.subheader("Gestión de datos")
        if st.button("🗑️ Eliminar todos los registros", type="secondary"):
            st.session_state.confirmar_borrado = True

        if st.session_state.get("confirmar_borrado"):
            st.warning("¿Estás seguro? Esta acción no se puede deshacer.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Sí, eliminar todo"):
                    eliminar_todos()
                    st.session_state.confirmar_borrado = False
                    st.rerun()
            with c2:
                if st.button("❌ Cancelar"):
                    st.session_state.confirmar_borrado = False
                    st.rerun()