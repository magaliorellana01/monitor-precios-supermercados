"""Dashboard de precios de supermercados (Streamlit).

    streamlit run app/app.py

Lee la base chica que arma `python -m src.exportar` (data/dashboard/dashboard.duckdb). Si no está en la PC
(por ejemplo en Streamlit Cloud), la baja del Release `datos-dashboard` del repositorio y la renueva cada hora.
No calcula métricas: muestra las que ya calculó el modelo.
"""

from __future__ import annotations

import os
import tempfile
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

REPO = "magaliorellana01/monitor-precios-supermercados"
URL_BASE = f"https://github.com/{REPO}/releases/download/datos-dashboard/dashboard.duckdb"
RUTA_LOCAL = Path(os.environ.get("DASHBOARD_DB") or Path(__file__).resolve().parent.parent / "data" / "dashboard" / "dashboard.duckdb")

COLOR, RESALTADO, VERDE = "#4C78A8", "#E45756", "#2E9E5B"  # VERDE: la cadena más barata
ZONAS = {"TODAS": "CABA y GBA", "CABA": "CABA", "GBA": "GBA"}
MIN_CADENAS_MARCA = 5
MIN_FILAS_PROMO = 1000

st.set_page_config(page_title="Monitor de precios de supermercados", layout="wide")


# --------------------------------------------------------------------------- datos

@st.cache_resource(ttl=3600, show_spinner="Bajando los datos más recientes...")
def conexion() -> duckdb.DuckDBPyConnection:
    """Abre la base del dashboard: la local si existe, o la del Release (se vuelve a bajar cada hora)."""
    if RUTA_LOCAL.exists():
        return duckdb.connect(str(RUTA_LOCAL), read_only=True)
    destino = Path(tempfile.mkdtemp(prefix="dashboard_")) / "dashboard.duckdb"
    pedido = urllib.request.Request(URL_BASE, headers={"User-Agent": "monitor-precios-dashboard"})
    with urllib.request.urlopen(pedido, timeout=60) as r, destino.open("wb") as f:
        f.write(r.read())
    return duckdb.connect(str(destino), read_only=True)


@st.cache_data(ttl=3600)
def consulta(sql: str, parametros: tuple = ()) -> pd.DataFrame:
    return conexion().execute(sql, list(parametros)).df()


def peso(x: float) -> str:
    return "$ " + f"{x:,.0f}".replace(",", ".")


def pct(x: float, signo: bool = False) -> str:
    texto = f"{x:+.1f}" if signo else f"{x:.1f}"
    return texto.replace(".", ",") + " %"


# --------------------------------------------------------------------------- carga inicial

try:
    meta = consulta("select * from meta").iloc[0]
except Exception:  # noqa: BLE001 - sin datos no hay dashboard
    st.title("Monitor de precios de supermercados")
    st.error("Todavía no hay datos publicados. En la PC: `python -m src.modelo`, `python -m src.exportar` y "
             "`python -c \"from src import almacen; almacen.subir_dashboard()\"`.")
    st.stop()

fecha_desde, fecha_hasta, dias = meta["fecha_desde"], meta["fecha_hasta"], int(meta["dias"])

with st.sidebar:
    st.header("Filtros")
    zona = st.radio("Zona", list(ZONAS), format_func=ZONAS.get,
                    help="Las cadenas fijan casi el mismo precio en CABA y en GBA. La mediana se calcula entre las sucursales de la zona.")
    st.divider()
    st.caption(f"Datos del {fecha_desde:%d/%m/%Y} al {fecha_hasta:%d/%m/%Y} ({dias} días).")
    st.caption(f"Actualizado: {meta['generado_en']:%d/%m/%Y %H:%M}.")
    st.caption("Fuente: base SEPA (Precios Claros), precios informados por las cadenas.")

st.title("Monitor de precios de supermercados")
st.caption("Precios que los supermercados informan a SEPA en CABA y GBA. Medianas entre sucursales, canasta fija de 30 productos.")
if dias < 28:
    st.info(f"Hay {dias} días de historia. Las comparaciones entre cadenas ya se pueden leer; "
            "la evolución en el tiempo y la comparación con la inflación necesitan al menos un mes.")

ranking = consulta("select * from m_ranking_canasta_dia where zona = ? order by fecha, posicion", (zona,))
ultimo_ranking = ranking[ranking["fecha"] == ranking["fecha"].max()]

tab_resumen, tab_canasta, tab_productos, tab_marcas, tab_inflacion, tab_promos, tab_metodo = st.tabs(
    ["Resumen", "Canasta", "Productos", "Marcas", "Inflación", "Promociones", "Metodología"])


# --------------------------------------------------------------------------- resumen

with tab_resumen:
    if ultimo_ranking.empty:
        st.warning("No hay cadenas con la canasta completa en esta zona.")
    else:
        barata, cara = ultimo_ranking.iloc[0], ultimo_ranking.iloc[-1]
        diferencia = 100 * (cara["costo_canasta"] / barata["costo_canasta"] - 1)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Canasta más barata", barata["cadena"], peso(float(barata["costo_canasta"])), delta_color="off")
        c2.metric("Canasta más cara", cara["cadena"], peso(float(cara["costo_canasta"])), delta_color="off")
        c3.metric("Diferencia entre extremos", pct(diferencia), help="Cuánto más cuesta la canasta en la cadena más cara que en la más barata.")
        c4.metric("Cadenas comparadas", int(barata["n_cadenas"]))

        t = ultimo_ranking.sort_values("costo_canasta", ascending=False).copy()
        t["costo"] = t["costo_canasta"].astype(float)
        t["color"] = ["Más barata" if p == 1 else "Otras" for p in t["posicion"]]
        t["etiqueta"] = [peso(c) + ("" if p == 1 else f"  ({pct(s, True)})") for c, p, s in
                         zip(t["costo"], t["posicion"], t["sobre_la_mas_barata_pct"])]
        fig = px.bar(t, x="costo", y="cadena", orientation="h", color="color", text="etiqueta",
                     color_discrete_map={"Más barata": VERDE, "Otras": COLOR},
                     labels={"costo": "Costo de la canasta ($)", "cadena": "", "color": ""})
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(showlegend=False, height=420, margin=dict(l=0, r=40, t=10, b=0),
                          yaxis=dict(categoryorder="total ascending"))
        fig.update_xaxes(range=[0, t["costo"].max() * 1.25])
        st.subheader(f"Costo de la canasta al {ultimo_ranking['fecha'].max():%d/%m/%Y}")
        st.plotly_chart(fig, width="stretch")
        st.caption("Costo de comprar una unidad de cada uno de los 30 productos de la canasta, con el precio de lista mediano de cada cadena. "
                   "Entre paréntesis, cuánto más cuesta que en la más barata.")


# --------------------------------------------------------------------------- canasta

with tab_canasta:
    st.subheader("Costo de la canasta por cadena")
    if ranking["fecha"].nunique() < 2:
        st.info("Hace falta más de un día para ver la evolución.")
    else:
        r = ranking.copy()
        r["costo"] = r["costo_canasta"].astype(float)
        fig = px.line(r, x="fecha", y="costo", color="cadena", markers=True,
                      labels={"fecha": "", "costo": "Costo de la canasta ($)", "cadena": "Cadena"})
        fig.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Qué cadenas se comparan")
    ultimo_dia = consulta("select max(fecha) as f from m_canasta_dia").iloc[0, 0]
    cobertura = consulta(
        "select cadena, rubro, n_sucursales, n_productos_canasta, completa, comparable "
        "from m_canasta_dia where zona = ? and fecha = ? order by comparable desc, cadena", (zona, ultimo_dia))

    def motivo(f: pd.Series) -> str:
        if f["comparable"] and f["completa"]:
            return "Entra en el ranking"
        if f["rubro"] != "supermercado":
            return "No es un supermercado"
        if not f["comparable"]:
            return "Muy pocas sucursales en la zona"
        return f"Canasta incompleta ({int(f['n_productos_canasta'])} de 30 productos)"

    cobertura["Estado"] = cobertura.apply(motivo, axis=1)
    st.dataframe(cobertura[["cadena", "rubro", "n_sucursales", "Estado"]].rename(
        columns={"cadena": "Cadena", "rubro": "Rubro", "n_sucursales": "Sucursales en la zona"}),
        hide_index=True, width="stretch")
    st.caption("Una cadena entra en el ranking si es un supermercado con al menos 5 sucursales en la zona y tiene los 30 productos. "
               "Con menos casos, quedaría como la más barata o la más cara por azar.")


# --------------------------------------------------------------------------- productos

with tab_productos:
    st.subheader("¿Cuánto cambia el precio del mismo producto según la cadena?")
    disp = consulta(
        "select k.categoria, k.producto, k.clave_producto, "
        "       median(d.rango_pct) as rango_pct, median(d.precio_min) as precio_min, median(d.precio_max) as precio_max, "
        "       max(d.n_cadenas) as n_cadenas "
        "from m_dispersion_producto_dia d join dim_canasta k using (clave_producto) "
        "where d.zona = ? group by all order by rango_pct desc", (zona,))
    if disp.empty:
        st.info("No hay productos con suficientes cadenas para comparar.")
    else:
        categorias = ["Todas"] + sorted(disp["categoria"].unique())
        categoria = st.selectbox("Categoría", categorias)
        d = disp if categoria == "Todas" else disp[disp["categoria"] == categoria]
        fig = px.bar(d.sort_values("rango_pct"), x="rango_pct", y="producto", orientation="h",
                     labels={"rango_pct": "% más caro en la cadena más cara que en la más barata", "producto": ""},
                     color_discrete_sequence=[COLOR])
        fig.update_layout(height=max(300, 24 * len(d) + 80), margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

        st.subheader("Precio por cadena")
        eleccion = st.selectbox("Producto", d["producto"].tolist())
        clave = d.loc[d["producto"] == eleccion, "clave_producto"].iloc[0]
        precios = consulta(
            "select cadena, precio_mediana from precio_canasta_dia "
            "where clave_producto = ? and zona = ? and fecha = (select max(fecha) from precio_canasta_dia) "
            "order by precio_mediana", (clave, zona))
        precios["precio"] = precios["precio_mediana"].astype(float)
        fig = px.bar(precios, x="precio", y="cadena", orientation="h", text=precios["precio"].map(peso),
                     labels={"precio": "Precio mediano ($)", "cadena": ""}, color_discrete_sequence=[COLOR])
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(height=max(250, 36 * len(precios) + 60), margin=dict(l=0, r=40, t=10, b=0),
                          yaxis=dict(categoryorder="total descending"))
        fig.update_xaxes(range=[0, precios["precio"].max() * 1.2])
        st.plotly_chart(fig, width="stretch")


# --------------------------------------------------------------------------- marcas

with tab_marcas:
    st.subheader("¿Cuánto más se paga por la marca líder?")
    prima = consulta(
        "select categoria, median(prima_pct) as prima_mediana, min(prima_pct) as prima_min, max(prima_pct) as prima_max, "
        "       count(distinct cadena) as n_cadenas "
        "from m_prima_marca_dia where zona = ? group by categoria having count(distinct cadena) >= ? "
        "order by prima_mediana", (zona, MIN_CADENAS_MARCA))
    if prima.empty:
        st.info("No hay categorías con suficientes cadenas para comparar.")
    else:
        prima["signo"] = ["La líder es más barata" if v < 0 else "La líder es más cara" for v in prima["prima_mediana"]]
        fig = px.bar(prima, x="prima_mediana", y="categoria", orientation="h", color="signo",
                     color_discrete_map={"La líder es más cara": COLOR, "La líder es más barata": RESALTADO},
                     text=prima["prima_mediana"].map(lambda v: pct(v, True)),
                     labels={"prima_mediana": "Prima de la marca líder sobre la alternativa (%)", "categoria": "", "signo": ""})
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(height=380, margin=dict(l=0, r=40, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption("Prima = precio de la marca líder / precio de la alternativa − 1, dentro de la misma cadena y el mismo día; "
                   "mediana entre cadenas y días. El \"líder\" es la marca más conocida según mi criterio, porque SEPA no informa ventas: "
                   "por eso la prima puede dar negativa. Son seis pares y no incluyen marcas propias.")
        pares = consulta("select categoria, rol, marca, producto from dim_par_marca order by categoria, rol desc")
        with st.expander("Qué productos se comparan"):
            st.dataframe(pares.rename(columns={"categoria": "Categoría", "rol": "Rol", "marca": "Marca", "producto": "Producto"}),
                         hide_index=True, width="stretch")


# --------------------------------------------------------------------------- inflación

with tab_inflacion:
    st.subheader("Índice propio de la canasta frente a la inflación oficial")
    indice = consulta("select fecha, indice from m_indice_general_dia where zona = ? order by fecha", (zona,))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Índice de la canasta** (base 100 el primer día con todas las cadenas)")
        fig = px.line(indice, x="fecha", y="indice", markers=True, labels={"fecha": "", "indice": "Índice"},
                      color_discrete_sequence=[COLOR])
        fig.add_hline(y=100, line_dash="dash", line_color="#999")
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown("**IPC mensual del INDEC** (últimos 12 meses)")
        ipc = consulta("select fecha, variacion_mensual_pct from ipc order by fecha desc limit 12").sort_values("fecha")
        if ipc.empty:
            st.info("No hay datos de IPC.")
        else:
            ipc["mes"] = pd.to_datetime(ipc["fecha"]).dt.strftime("%m/%Y")
            fig = px.bar(ipc, x="mes", y="variacion_mensual_pct", labels={"mes": "", "variacion_mensual_pct": "Variación mensual (%)"},
                         color_discrete_sequence=[COLOR])
            fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, width="stretch")
    if dias < 28:
        st.warning("Todavía no se pueden comparar: el IPC es mensual y hay menos de un mes de datos propios. "
                   "Con 4 o 5 semanas se compara la variación del índice con el IPC del mes.")
    st.caption("El índice es la mediana de los índices de cada cadena (costo de la canasta / costo el día base × 100). "
               "Los precios de supermercado se actualizan en saltos, por eso una semana sin cambios no contradice una inflación mensual de 2 %.")


# --------------------------------------------------------------------------- promociones

with tab_promos:
    st.subheader("Promociones informadas")
    promos = consulta(
        "select cadena, filas_promo, pct_con_promo, descuento_mediano_pct from m_promo_cadena_dia "
        "where fecha = (select max(fecha) from m_promo_cadena_dia) and filas_promo >= ? order by pct_con_promo desc",
        (MIN_FILAS_PROMO,))
    if promos.empty:
        st.info("No hay cadenas con suficientes promociones informadas.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(promos, x="pct_con_promo", y="cadena", orientation="h", text=promos["pct_con_promo"].map(lambda v: pct(v)),
                         labels={"pct_con_promo": "% de los precios en promoción", "cadena": ""}, color_discrete_sequence=[COLOR])
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(height=320, margin=dict(l=0, r=40, t=30, b=0), title="Qué parte de los precios está en promoción",
                              yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig = px.bar(promos, x="descuento_mediano_pct", y="cadena", orientation="h",
                         text=promos["descuento_mediano_pct"].map(lambda v: pct(v)),
                         labels={"descuento_mediano_pct": "Descuento mediano (%)", "cadena": ""}, color_discrete_sequence=[RESALTADO])
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(height=320, margin=dict(l=0, r=40, t=30, b=0), title="De cuánto es el descuento",
                              yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig, width="stretch")
    st.caption("Solo informan promociones DIA, Carrefour, Coto, la Cooperativa Obrera y La Anónima; las demás cadenas no informan ninguna, "
               "así que no se pueden comparar. Se muestran las que tienen al menos 1.000 precios en promoción. "
               "Si las promociones son \"el precio de siempre\" necesita semanas de historia: ver el notebook de análisis.")


# --------------------------------------------------------------------------- metodología

with tab_metodo:
    st.subheader("Cómo se calcula")
    st.markdown(f"""
- **Fuente:** base SEPA (Precios Claros, datos.gob.ar). Son precios **informados por las cadenas**, no de tickets reales, y solo de las cadenas obligadas a informar.
- **Zona:** CABA y GBA. Las cadenas cobran casi lo mismo en las dos, así que elegir la cadena importa más que dónde se vive.
- **Mediana, no promedio:** el precio de un producto en una cadena es la mediana entre sus sucursales, para que un error de carga o una sucursal en un barrio caro no distorsione.
- **Canasta de 30 productos básicos de marca nacional, composición fija:** una unidad de cada uno. Así el costo y el índice miden cambios de precio y no cambios en los productos.
  No incluye marcas propias, que en cadenas como DIA son gran parte de lo que se vende.
- **Cadenas comparables:** supermercados con al menos 5 sucursales en la zona y los 30 productos. Si falta un producto uno o dos días, se usa su último precio (hasta 3 días).
- **Precio de lista:** las comparaciones usan el precio de lista, sin promociones, porque no todas las cadenas informan sus promociones.
- **No es el gasto de un hogar:** no se pondera por consumo.

Cada decisión, con las alternativas descartadas, está en el
[repositorio](https://github.com/{REPO}/blob/main/docs/decisiones.md).
""")
