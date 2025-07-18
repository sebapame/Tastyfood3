from flask import Flask, render_template, request, redirect
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text
import os
import math

app = Flask(__name__)

# Obtener URL de conexión desde variable de entorno
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

engine = create_engine(DATABASE_URL)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        patente = request.form["patente"].upper().strip()
        tipo = request.form["tipo"]
        transferencia = "Prepago"
        fecha_ingreso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO ingresos (patente, tipo, transferencia, fecha_ingreso) VALUES (:patente, :tipo, :transferencia, :fecha_ingreso)"),
                {"patente": patente, "tipo": tipo, "transferencia": transferencia, "fecha_ingreso": fecha_ingreso}
            )
        return redirect("/")

    with engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM ingresos ORDER BY id DESC", conn)

    # Aplicar estilo para resaltar última fila con salida
    df["resaltar"] = ""
    ultima_con_salida = df[df["fecha_salida"].notnull()].head(1)
    if not ultima_con_salida.empty:
        df.loc[ultima_con_salida.index[0], "resaltar"] = "background-color: yellow; font-weight: bold;"

    return render_template("index.html", tabla=df.to_dict(orient="records"))

@app.route("/salida/<int:registro_id>")
def salida(registro_id):
    fecha_salida = datetime.now()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT fecha_ingreso FROM ingresos WHERE id = :id"), {"id": registro_id}).fetchone()
        if result:
            fecha_ingreso = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
            tiempo = (fecha_salida - fecha_ingreso).total_seconds() / 60
            tiempo_extra = max(0, tiempo - 15)
            monto = 500 + (tiempo_extra * 24)
            monto = int(round(monto / 10.0) * 10)  # Redondear al múltiplo de 10 más cercano

            conn.execute(
                text("UPDATE ingresos SET fecha_salida = :salida, monto = :monto WHERE id = :id"),
                {"salida": fecha_salida.strftime("%Y-%m-%d %H:%M:%S"), "monto": monto, "id": registro_id}
            )
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)

