from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text
import os

app = Flask(__name__)

# Obtener y corregir URL de base de datos
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Crear conexión SQLAlchemy
engine = create_engine(DATABASE_URL)

# Crear tabla si no existe
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ingresos (
            id SERIAL PRIMARY KEY,
            patente TEXT NOT NULL,
            hora_entrada TIMESTAMP NOT NULL,
            hora_salida TIMESTAMP,
            minutos INTEGER,
            monto INTEGER,
            medio_pago TEXT
        );
    """))

@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = ""
    mostrar_monto = False
    minutos = 0
    monto = 0
    filtro_fecha = request.args.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    now = datetime.now()

    if request.method == "POST":
        patente = request.form["patente"].upper()
        medio_pago = request.form.get("medio_pago", "")

        with engine.begin() as conn:
            result = conn.execute(text("SELECT * FROM ingresos WHERE patente = :patente AND hora_salida IS NULL"), {"patente": patente})
            registro = result.fetchone()

            if registro:
                hora_entrada = registro["hora_entrada"]
                hora_salida = now
                minutos_totales = int((hora_salida - hora_entrada).total_seconds() / 60)
                minutos_extra = max(0, minutos_totales - 15)
                monto = 500 + minutos_extra * 24

                # Redondear a la decena más cercana
                unidad = monto % 10
                if unidad < 5:
                    monto -= unidad
                else:
                    monto += (10 - unidad)

                if medio_pago:
                    conn.execute(text("""
                        UPDATE ingresos
                        SET hora_salida = :salida, minutos = :min, monto = :monto, medio_pago = :pago
                        WHERE id = :id
                    """), {
                        "salida": hora_salida,
                        "min": minutos_totales,
                        "monto": monto,
                        "pago": medio_pago,
                        "id": registro["id"]
                    })
                    return redirect(url_for("index", fecha=filtro_fecha))
                else:
                    mostrar_monto = True
                    minutos = minutos_totales
            else:
                conn.execute(text("INSERT INTO ingresos (patente, hora_entrada) VALUES (:patente, :entrada)"), {
                    "patente": patente,
                    "entrada": now
                })
                return redirect(url_for("index", fecha=filtro_fecha))

    # Mostrar registros del día filtrado
    with engine.begin() as conn:
        df = pd.read_sql("SELECT * FROM ingresos ORDER BY id DESC", conn)
        df["fecha"] = df["hora_entrada"].dt.strftime("%Y-%m-%d")
        registros = df[df["fecha"] == filtro_fecha].to_dict(orient="records")

        # Última salida con hora_salida NO NULL
        salida = df[(df["fecha"] == filtro_fecha) & (df["hora_salida"].notnull())]
        ultima_salida_id = salida["id"].max() if not salida.empty else None

        pagos = df[(df["fecha"] == filtro_fecha) & (df["monto"].notnull())]
        totales = pagos.groupby("medio_pago")["monto"].sum().to_dict()
        total_general = pagos["monto"].sum()

    return render_template("index.html", registros=registros, mensaje=mensaje,
                           mostrar_monto=mostrar_monto, minutos=minutos, monto=monto,
                           fecha=filtro_fecha, totales=totales, total_general=total_general,
                           ultima_salida_id=ultima_salida_id)

if __name__ == "__main__":
    app.run(debug=True)


